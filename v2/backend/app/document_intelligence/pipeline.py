from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from ..services.storage import DocumentStorage
from .fingerprint import create_format_fingerprint
from .legacy_adapter import normalize_legacy_pdf
from .models import (
    DocumentRecord, DocumentStatus, ErrorCode, ExtractionMethod, ExtractionQuality,
    IntakeContext, NormalizedExtractionResult, ReviewReason,
)
from .native_pdf import ExtractionQualityAssessor, NativePdfExtractor
from .ocr import (
    OcrEmptyError, OcrProcessError, OcrService, OcrTimeoutError, OcrUnavailableError,
    confidence_tier, detect_digit_confusions, normalize_ocr_token,
)
from .repository import DocumentRepository
from .routing import KnownFormatRouter
from .security import DocumentSecurityError, ResourceLimits, validate_pdf_upload
from .status_machine import DocumentStatusMachine
from .validation import AccountingValidationEngine, RequiredFieldValidator


class DocumentIntakeService:
    def __init__(self, repository: DocumentRepository, storage: DocumentStorage,
                 ocr: OcrService | None = None, limits: ResourceLimits = ResourceLimits()) -> None:
        self.repository, self.storage, self.ocr, self.limits = repository, storage, ocr, limits
        self.native = NativePdfExtractor()
        self.quality = ExtractionQualityAssessor()
        self.router = KnownFormatRouter()
        self.machine = DocumentStatusMachine()

    def _move(self, record: DocumentRecord, target: DocumentStatus, **values) -> DocumentRecord:
        self.machine.transition(record.status, target)
        self.repository.transition(record.organization_id, record.company_id, record.document_id,
                                   record.status, target, **values)
        return replace(record, status=target, **values)

    def process(self, context: IntakeContext, filename: str, mime_type: str, content: bytes,
                batch_id=None) -> dict:
        started = perf_counter()
        safe_name = validate_pdf_upload(content, filename, mime_type, self.limits)
        digest = hashlib.sha256(content).hexdigest()
        duplicate_id = self.repository.exact_duplicate(context.organization_id, context.company_id, digest)
        if duplicate_id:
            return {"document_id": duplicate_id, "sha256": digest, "duplicate": True,
                    "status": DocumentStatus.DUPLICATE.value}
        document_id = uuid4()
        stored = self.storage.put(context.organization_id, context.company_id, document_id, safe_name, content)
        record = DocumentRecord(document_id, context.organization_id, context.company_id, filename, safe_name,
                                mime_type, stored.size, stored.sha256, stored.storage_key, 0,
                                DocumentStatus.UPLOADED, context.user_id, batch_id=batch_id)
        self.repository.create(record)
        record = self._move(record, DocumentStatus.REGISTERED)
        try:
            record = self._move(record, DocumentStatus.EXTRACTING)
            native_started = perf_counter()
            pages = self.native.extract(content, self.limits)
            native_duration_ms = round((perf_counter() - native_started) * 1000)
            assessment = self.quality.assess(pages)
            fingerprint = create_format_fingerprint(pages)
            text = "\n".join(page.text for page in pages)
            route = self.router.route(text, filename, assessment.status, fingerprint)
            self.repository.save_pages(document_id, pages)
            self.repository.save_fingerprint(context.organization_id, document_id, fingerprint)
            ocr_page_numbers = tuple(page.page_number for page in pages
                                     if self.quality.assess((page,)).status is ExtractionQuality.OCR_REQUIRED)
            self.repository.save_metric(replace(record, page_count=len(pages)), "NATIVE_EXTRACTION",
                                        native_duration_ms, assessment.status.value, format_route=route.route)
            low_confidence_critical = False
            if ocr_page_numbers:
                record = self._move(record, DocumentStatus.OCR_REQUIRED, page_count=len(pages),
                                    quality_status=assessment.status)
                if not self.ocr or not self.ocr.available:
                    record = self._move(record, DocumentStatus.REVIEW, error_code=ErrorCode.OCR_UNAVAILABLE)
                    self.repository.create_review(record, ReviewReason.OCR_UNAVAILABLE.value,
                                                  detail={"quality_signals": assessment.signals})
                    return self._result(record, digest, started)
                if len(ocr_page_numbers) > self.limits.ocr_max_pages:
                    record = self._move(record, DocumentStatus.REVIEW, error_code=ErrorCode.OCR_FAILED)
                    self.repository.create_review(record, ReviewReason.OCR_FAILED.value,
                                                  detail={"requested_pages": len(ocr_page_numbers),
                                                          "maximum_pages": self.limits.ocr_max_pages})
                    return self._result(record, digest, started)
                ocr_started = perf_counter()
                try:
                    ocr_pages = tuple(self.ocr.extract_page(content, page_number)
                                      for page_number in ocr_page_numbers)
                except OcrUnavailableError:
                    record = self._move(record, DocumentStatus.REVIEW, error_code=ErrorCode.OCR_UNAVAILABLE)
                    self.repository.create_review(record, ReviewReason.OCR_UNAVAILABLE.value)
                    return self._result(record, digest, started)
                except OcrTimeoutError:
                    record = self._move(record, DocumentStatus.REVIEW, error_code=ErrorCode.OCR_TIMEOUT)
                    self.repository.create_review(record, ReviewReason.OCR_TIMEOUT.value)
                    return self._result(record, digest, started)
                except OcrEmptyError:
                    record = self._move(record, DocumentStatus.REVIEW, error_code=ErrorCode.OCR_EMPTY)
                    self.repository.create_review(record, ReviewReason.OCR_EMPTY.value)
                    return self._result(record, digest, started)
                except OcrProcessError:
                    record = self._move(record, DocumentStatus.REVIEW, error_code=ErrorCode.OCR_FAILED)
                    self.repository.create_review(record, ReviewReason.OCR_FAILED.value)
                    return self._result(record, digest, started)
                from .models import DetectedField
                ocr_fields = tuple(DetectedField(
                    f"ocr_token_{page.page_number}_{index}", normalize_ocr_token(token.text), token.source,
                    ExtractionMethod.LOCAL_OCR, Decimal(str(token.confidence)), token.text,
                    "AMBIGUOUS_DIGITS_RETAINED" if detect_digit_confusions(token.text)
                    else ("SAFE_FORMAT_NORMALIZATION" if normalize_ocr_token(token.text) != token.text else "")
                ) for page in ocr_pages for index, token in enumerate(page.tokens))
                ambiguity_count = sum(bool(detect_digit_confusions(token.text)) for page in ocr_pages for token in page.tokens)
                low_confidence_critical = any(
                    any(character.isdigit() for character in token.text)
                    and confidence_tier(token.confidence, critical_numeric=True).value == "LOW"
                    for page in ocr_pages for token in page.tokens
                )
                ocr_by_page = {page.page_number: page for page in ocr_pages}
                combined_pages = tuple(replace(page, text=ocr_by_page[page.page_number].text)
                                       if page.page_number in ocr_by_page else page for page in pages)
                combined_text = "\n".join(page.text for page in combined_pages)
                combined_assessment = self.quality.assess(combined_pages)
                fingerprint = create_format_fingerprint(combined_pages)
                self.repository.save_fingerprint(context.organization_id, document_id, fingerprint)
                route = self.router.route(combined_text, filename, combined_assessment.status, fingerprint)
                warnings = (f"OCR processed pages {','.join(map(str, ocr_page_numbers))} and produced {len(ocr_fields)} tokens",
                            f"{ambiguity_count} tokens contain possible digit/letter ambiguity; originals were retained")
                if route.route.startswith("legacy_pdf:"):
                    template = route.route.split(":", 1)[1]
                    parsed = normalize_legacy_pdf(document_id, template, combined_text, safe_name,
                                                  combined_pages, combined_assessment, fingerprint)
                    result = replace(parsed, method=ExtractionMethod.LOCAL_OCR, fields=ocr_fields,
                                     warnings=warnings + parsed.warnings)
                else:
                    result = NormalizedExtractionResult(document_id, ExtractionMethod.LOCAL_OCR, combined_pages,
                        fields=ocr_fields, warnings=warnings + (route.reason,),
                        quality=combined_assessment, fingerprint=fingerprint)
                self.repository.save_metric(replace(record, extraction_method=ExtractionMethod.LOCAL_OCR),
                                            "OCR", round((perf_counter() - ocr_started) * 1000),
                                            "COMPLETED", ocr_pages=len(ocr_page_numbers), format_route=route.route)
            elif route.route.startswith("legacy_pdf:"):
                template = route.route.split(":", 1)[1]
                result = normalize_legacy_pdf(document_id, template, text, safe_name, pages, assessment, fingerprint)
            else:
                result = NormalizedExtractionResult(document_id, ExtractionMethod.NATIVE_TEXT, pages,
                    quality=assessment, fingerprint=fingerprint,
                    warnings=(route.reason,))
            invoice_total = result.totals.get("invoice_total")
            record = self._move(record, DocumentStatus.EXTRACTED, page_count=len(pages),
                                extraction_method=result.method, quality_status=assessment.status,
                                document_type=result.document_type, supplier=result.supplier,
                                invoice_number=result.invoice_number, invoice_date=result.invoice_date,
                                total_amount=invoice_total)
            if route.known:
                family_id, template_id = self.repository.resolve_known_format(record, route.route)
                result = replace(result, format_family_id=family_id, template_version_id=template_id)
            extraction_id = self.repository.save_extraction(record, result, "phase3-foundation-v1")
            if not route.known:
                record = self._move(record, DocumentStatus.REVIEW, error_code=ErrorCode.FORMAT_UNKNOWN)
                self.repository.create_review(record, ReviewReason.UNKNOWN_FORMAT.value,
                                              detail={"route": route.route, "fingerprint": fingerprint.signature})
                return self._result(record, digest, started)
            business_values = (record.supplier, record.document_type, record.invoice_number,
                               record.invoice_date, record.total_amount)
            if all(value not in (None, "") for value in business_values):
                normalized = [" ".join(str(value).split()).casefold() for value in (record.company_id, *business_values)]
                business_signature = hashlib.sha256(json.dumps(normalized, separators=(",", ":")).encode()).hexdigest()
                matching = self.repository.business_duplicate(record.organization_id, record.company_id, business_signature)
                if matching:
                    record = self._move(record, DocumentStatus.REVIEW)
                    self.repository.create_review(record, ReviewReason.POSSIBLE_DUPLICATE.value,
                                                  detail={"matching_document_id": str(matching)})
                    return self._result(record, digest, started)
                self.repository.save_business_signature(record, business_signature)
            record = self._move(record, DocumentStatus.VALIDATING)
            validation_started = perf_counter()
            payload = {
                "document_type": result.document_type, "supplier": result.supplier,
                "invoice_number": result.invoice_number, "invoice_date": result.invoice_date,
                "items": result.items, "tax_buckets": result.tax_buckets,
                **result.totals,
            }
            engine = AccountingValidationEngine((RequiredFieldValidator(
                ("document_type", "supplier", "invoice_number", "invoice_date")),
                *AccountingValidationEngine().validators))
            report = engine.validate(payload)
            self.repository.save_metric(record, "VALIDATION", round((perf_counter() - validation_started) * 1000),
                                        report.status, format_route=route.route, validation_status=report.status)
            self.repository.save_validation(record, extraction_id, report)
            target = DocumentStatus.REVIEW if low_confidence_critical and report.status == "VERIFIED" else DocumentStatus(report.status)
            record = self._move(record, target)
            if low_confidence_critical:
                self.repository.create_review(record, ReviewReason.OCR_LOW_CONFIDENCE.value,
                                              detail={"policy": "critical numeric OCR token below MEDIUM tier"})
            if target in {DocumentStatus.REVIEW, DocumentStatus.BLOCKED}:
                for finding in report.findings:
                    if finding.status in {"REVIEW", "BLOCKED"}:
                        self.repository.create_review(record, (finding.error_code.value if finding.error_code else finding.validator),
                                                      finding.severity.value, {"message": finding.message})
            return self._result(record, digest, started)
        except DocumentSecurityError as exc:
            if record.status not in {DocumentStatus.FAILED, DocumentStatus.REVIEW}:
                record = self._move(record, DocumentStatus.FAILED, error_code=exc.code)
            return self._result(record, digest, started)
        except Exception:
            if record.status in {DocumentStatus.REGISTERED, DocumentStatus.EXTRACTING, DocumentStatus.OCR_REQUIRED,
                                 DocumentStatus.EXTRACTED, DocumentStatus.VALIDATING}:
                record = self._move(record, DocumentStatus.FAILED)
            raise

    def _result(self, record: DocumentRecord, digest: str, started: float) -> dict:
        duration_ms = round((perf_counter() - started) * 1000)
        self.repository.save_metric(record, "TOTAL", duration_ms, record.status.value)
        return {"document_id": record.document_id, "sha256": digest, "duplicate": False,
                "status": record.status.value, "duration_ms": duration_ms}
