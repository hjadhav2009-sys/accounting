from __future__ import annotations

import io
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from uuid import uuid4

from v2.backend.app.document_intelligence.models import BoundingBox, ExtractionMethod, IntakeContext
from v2.backend.app.document_intelligence.native_pdf import NativePdfExtractor
from v2.backend.app.document_intelligence.ocr import (
    OcrEmptyError, OcrPageResult, OcrProcessError, OcrTimeoutError, OcrToken,
    TesseractOcrService, confidence_tier, normalize_ocr_token,
)
from v2.backend.app.document_intelligence.pipeline import DocumentIntakeService
from v2.backend.app.document_intelligence.repository import DocumentRepository
from v2.backend.app.document_intelligence.models import SourceReference
from v2.backend.app.services.storage import LocalFilesystemStorage
from tests.v2.rls_support import set_tenant, tenant_factory


OCR_TEXT = """Tax Invoice
Invoice No. : 2600000999
Date : 01-08-2026
Supplier : Synthetic Supplier
Taxable amount
Item Name
HSN
Quantity
Unit
Unit Price
GST
Amount
1
Synthetic low-rate item
7113
400
PCS
10
120 (3%)
4120
2
Synthetic standard-rate item
7326
20
PCS
20
72 (18%)
472
Total
Numeric Samples 0 1 5 8 1,593 21,494.00 644.82 4,350.00 783.00 27,272.00 -0.28 18% 3%
"""


def scanned_pdf(text: str = OCR_TEXT, *, poor: bool = False, rotate: int = 0) -> bytes:
    import pymupdf
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    lines = text.splitlines(); image = Image.new("RGB", (1800, max(1400, len(lines) * 54 + 100)), "white")
    draw = ImageDraw.Draw(image); font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 32)
    for index, line in enumerate(lines): draw.text((70, 55 + index * 51), line, fill="#303030" if poor else "black", font=font)
    if poor: image = image.filter(ImageFilter.GaussianBlur(0.7))
    if rotate: image = image.rotate(rotate, expand=True, fillcolor="white")
    stream = io.BytesIO(); image.save(stream, format="JPEG", quality=65 if poor else 94)
    document = pymupdf.open(); page = document.new_page(width=900, height=image.height * 900 / image.width)
    page.insert_image(page.rect, stream=stream.getvalue()); content = document.tobytes(); document.close(); return content


def native_table_pdf() -> bytes:
    import pymupdf
    document = pymupdf.open(); page = document.new_page(width=600, height=400)
    xs, ys = [40, 180, 300, 420, 560], [40, 90, 140, 190]
    for x in xs: page.draw_line((x, ys[0]), (x, ys[-1]))
    for y in ys: page.draw_line((xs[0], y), (xs[-1], y))
    rows = [["HSN", "Quantity", "GST", "Amount"], ["7113", "400", "3%", "4120"], ["7326", "20", "18%", "472"]]
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row): page.insert_text((xs[column_index] + 8, ys[row_index] + 30), value, fontsize=11)
    content = document.tobytes(); document.close(); return content


class TesseractRuntimeTests(unittest.TestCase):
    executable = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")

    @unittest.skipUnless(executable.exists(), "Tesseract runtime not installed")
    def test_runtime_numeric_provenance_and_local_languages(self):
        service = TesseractOcrService(self.executable)
        self.assertTrue(service.available); self.assertIn("5.4.0", service.version)
        result = service.extract_page(scanned_pdf(), 1)
        for token in ("0", "1", "5", "8", "1,593", "21,494.00", "644.82", "4,350.00", "783.00", "27,272.00", "-0.28", "18%", "3%"):
            self.assertIn(token, result.text)
        numeric = next(item for item in result.tokens if item.text == "21,494.00")
        self.assertEqual(normalize_ocr_token(numeric.text), "21494.00")
        self.assertEqual(numeric.source.original_token, "21,494.00")
        self.assertIsNotNone(numeric.source.bounding_box)
        self.assertIn(confidence_tier(numeric.confidence, True).value, {"HIGH", "MEDIUM", "LOW"})

    @unittest.skipUnless(executable.exists(), "Tesseract runtime not installed")
    def test_poor_scan_executes_without_external_service(self):
        result = TesseractOcrService(self.executable).extract_page(scanned_pdf(poor=True), 1)
        self.assertEqual(result.engine, "tesseract"); self.assertTrue(result.tokens)

    def test_invalid_explicit_path_is_unavailable(self):
        self.assertFalse(TesseractOcrService("C:/synthetic-missing/tesseract.exe").available)


class NativeTableFixtureTests(unittest.TestCase):
    def test_table_rows_columns_coordinates_and_order(self):
        page = NativePdfExtractor().extract(native_table_pdf())[0]
        self.assertEqual(len(page.tables), 1); table = page.tables[0]
        self.assertEqual(len(table.rows), 3); self.assertTrue(all(len(row.cells) == 4 for row in table.rows))
        self.assertEqual([[cell.text for cell in row.cells] for row in table.rows], [
            ["HSN", "Quantity", "GST", "Amount"], ["7113", "400", "3%", "4120"], ["7326", "20", "18%", "472"]])
        self.assertEqual(table.bounding_box.normalized, (40/600, 40/400, 560/600, 190/400))


@unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL"), "development PostgreSQL is not available")
class Phase3BRuntimeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from v2.backend.app.infrastructure.postgres_migrations import apply_migrations
        cls.psycopg = psycopg; cls.url = os.environ["POSTGRES_TEST_DATABASE_URL"]
        connection = psycopg.connect(cls.url); apply_migrations(connection); connection.close()

    def setUp(self):
        self.organization_id, self.company_id, self.user_id = uuid4(), uuid4(), uuid4()
        connection = self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)", (self.organization_id, f"Phase3B {self.organization_id}"))
            set_tenant(cursor,self.organization_id,self.company_id)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Synthetic 3B','Synthetic 3B')", (self.company_id, self.organization_id))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Phase3B','ACTIVE')", (self.user_id, self.organization_id, f"{self.user_id}@example.invalid"))
        connection.commit(); connection.close(); self.temp = tempfile.TemporaryDirectory()
        self.repo = DocumentRepository(tenant_factory(self.url,self.organization_id,self.company_id,self.user_id)); self.context = IntakeContext(self.organization_id, self.company_id, self.user_id)

    def tearDown(self): self.temp.cleanup()

    def test_native_pdf_skips_ocr(self):
        from tests.v2.test_phase3 import pdf_with_text, SUJAL_TEXT
        class FailIfCalled:
            available = True
            def extract_page(self, *_args): raise AssertionError("healthy native PDF invoked OCR")
        result = DocumentIntakeService(self.repo, LocalFilesystemStorage(self.temp.name), FailIfCalled()).process(
            self.context, "native.pdf", "application/pdf", pdf_with_text(SUJAL_TEXT))
        self.assertEqual(result["status"], "VERIFIED")

    @unittest.skipUnless(Path("C:/Program Files/Tesseract-OCR/tesseract.exe").exists(), "Tesseract runtime not installed")
    def test_scanned_invoice_uses_real_ocr_and_preserves_numeric_candidates(self):
        service = DocumentIntakeService(self.repo, LocalFilesystemStorage(self.temp.name),
            TesseractOcrService("C:/Program Files/Tesseract-OCR/tesseract.exe"))
        processed = service.process(self.context, "scanned-tax-invoice.pdf", "application/pdf", scanned_pdf())
        self.assertIn(processed["status"], {"VERIFIED", "REVIEW"})
        record = self.repo.get(self.organization_id, self.company_id, processed["document_id"])
        self.assertEqual(record["extraction_method"], "LOCAL_OCR")
        extraction = self.repo.extraction(self.organization_id, self.company_id, processed["document_id"])["normalized_result"]
        self.assertEqual({str(bucket["rate"]) for bucket in extraction["tax_buckets"]}, {"3", "18"})
        numeric = [field for field in extraction["fields"] if field["original_token"] == "21,494.00"]
        self.assertEqual(numeric[0]["value"], "21494.00")
        self.assertIsNotNone(numeric[0]["source"]["bounding_box"])
        validation = self.repo.validation(self.organization_id, self.company_id, processed["document_id"])
        self.assertEqual(validation["status"], "VERIFIED")

    def test_mixed_document_invokes_only_scanned_page(self):
        import pymupdf
        from tests.v2.test_phase3 import SUJAL_TEXT
        document = pymupdf.open(); first = document.new_page(); first.insert_textbox(first.rect + (30,30,-30,-30), SUJAL_TEXT, fontsize=8)
        second = document.new_page(); content = document.tobytes(); document.close(); calls = []
        class SpyOcr:
            available = True
            def extract_page(self, _content, page_number):
                calls.append(page_number); box = BoundingBox(1,1,20,10,100,100)
                return OcrPageResult(page_number, "Synthetic supplement", (OcrToken("Synthetic", .99, SourceReference(page_number, ExtractionMethod.LOCAL_OCR, box, original_token="Synthetic")),), "fake", "1", .01)
        DocumentIntakeService(self.repo, LocalFilesystemStorage(self.temp.name), SpyOcr()).process(self.context, "mixed.pdf", "application/pdf", content)
        self.assertEqual(calls, [2])

    def _ocr_candidate_service(self, text: str, confidence: float):
        class CandidateOcr:
            available = True
            def extract_page(self, _content, page_number):
                box = BoundingBox(10, 10, 110, 40, 900, 700)
                token = OcrToken("21,494.00", confidence, SourceReference(page_number, ExtractionMethod.LOCAL_OCR, box, original_token="21,494.00"))
                return OcrPageResult(page_number, text, (token,), "synthetic-provider", "1", .01)
        return DocumentIntakeService(self.repo, LocalFilesystemStorage(self.temp.name), CandidateOcr())

    def test_low_confidence_critical_ocr_requires_review_even_when_balanced(self):
        processed = self._ocr_candidate_service(OCR_TEXT, .50).process(
            self.context, "low-confidence.pdf", "application/pdf", scanned_pdf(""))
        self.assertEqual(processed["status"], "REVIEW")
        reviews = self.repo.reviews(self.organization_id, self.company_id, reason="OCR_LOW_CONFIDENCE")
        self.assertEqual(len(reviews), 1)

    def test_ocr_accounting_mismatch_blocks_without_repair(self):
        mismatched = OCR_TEXT.replace("120 (3%)", "121 (3%)")
        processed = self._ocr_candidate_service(mismatched, .99).process(
            self.context, "mismatch.pdf", "application/pdf", scanned_pdf(""))
        self.assertEqual(processed["status"], "BLOCKED")
        validation = self.repo.validation(self.organization_id, self.company_id, processed["document_id"])
        self.assertTrue(any(issue["code"] in {"GST_MISMATCH", "INVOICE_TOTAL_MISMATCH"} for issue in validation["issues"]))

    def _assert_ocr_failure(self, exception, expected_code):
        class FailingOcr:
            available = True
            def extract_page(self, *_args): raise exception
        result = DocumentIntakeService(self.repo, LocalFilesystemStorage(self.temp.name), FailingOcr()).process(
            self.context, f"{expected_code.lower()}.pdf", "application/pdf", scanned_pdf(""))
        self.assertEqual(result["status"], "REVIEW")
        record = self.repo.get(self.organization_id, self.company_id, result["document_id"])
        self.assertEqual(record["error_code"], expected_code)

    def test_ocr_timeout_is_structured_review(self):
        self._assert_ocr_failure(OcrTimeoutError("synthetic timeout"), "OCR_TIMEOUT")

    def test_ocr_process_failure_is_structured_review(self):
        self._assert_ocr_failure(OcrProcessError("synthetic process failure"), "OCR_FAILED")

    def test_ocr_empty_is_structured_review(self):
        self._assert_ocr_failure(OcrEmptyError("synthetic empty"), "OCR_EMPTY")

    def test_durable_batch_progress_survives_repository_recreation(self):
        batch_id = self.repo.create_batch(self.organization_id, self.company_id, self.user_id, 2)
        self.repo.start_batch(self.organization_id, self.company_id, batch_id); self.repo.batch_document_started(self.organization_id, self.company_id, batch_id)
        self.repo.batch_document_finished(self.organization_id, self.company_id, batch_id, "VERIFIED")
        recreated = DocumentRepository(tenant_factory(self.url,self.organization_id,self.company_id,self.user_id)); status = recreated.get_batch(self.organization_id, self.company_id, batch_id)
        self.assertEqual((status["processed"], status["verified"], status["queued"]), (1, 1, 1))
        self.assertIsNone(recreated.get_batch(uuid4(), self.company_id, batch_id))
        recreated.batch_document_started(self.organization_id, self.company_id, batch_id); recreated.batch_document_finished(self.organization_id, self.company_id, batch_id, "FAILED")
        recreated.finish_batch(self.organization_id, self.company_id, batch_id)
        self.assertEqual(recreated.get_batch(self.organization_id, self.company_id, batch_id)["status"], "COMPLETED_WITH_ERRORS")

    def test_filters_reports_and_new_api_surface_are_tenant_scoped(self):
        report = self.repo.unified_report(self.organization_id, self.company_id)
        self.assertIn("invoices", report); self.assertIn("bank", report); self.assertEqual(report["documents"]["total"], 0)
        from v2.backend.app.main import app
        paths = app.openapi()["paths"]
        for path in ("/api/v2/batches/{batch_id}", "/api/v2/batches/{batch_id}/documents",
                     "/api/v2/reports/unified", "/api/v2/reports/format-health",
                     "/api/v2/documents/{document_id}/pages/{page_number}/image"):
            self.assertIn(path, paths)

    def test_background_batch_api_persists_progress_and_independent_failure(self):
        from fastapi.testclient import TestClient
        from tests.v2.test_phase3 import SUJAL_TEXT, pdf_with_text
        from v2.backend.app.config.settings import get_settings
        from v2.backend.app.main import app
        headers = {"X-Organization-ID": str(self.organization_id), "X-Company-ID": str(self.company_id),
                   "X-User-ID": str(self.user_id)}
        with patch.dict(os.environ, {"POSTGRES_URL": self.url, "DATABASE_URL": "", "STORAGE_ROOT": self.temp.name}, clear=False):
            get_settings.cache_clear()
            try:
                with TestClient(app) as client:
                    response = client.post("/api/v2/documents/batch", headers=headers, files=[
                        ("files", ("valid.pdf", pdf_with_text(SUJAL_TEXT), "application/pdf")),
                        ("files", ("invalid.pdf", b"not a pdf", "application/pdf")),
                    ])
                    self.assertEqual(response.status_code, 202); batch_id = response.json()["batch_id"]
                    status = client.get(f"/api/v2/batches/{batch_id}", headers=headers).json()
                    deadline=time.monotonic()+15
                    while status["status"] in {"QUEUED","RUNNING"} and time.monotonic()<deadline:
                        time.sleep(.1);status=client.get(f"/api/v2/batches/{batch_id}",headers=headers).json()
                    self.assertEqual(status["status"], "COMPLETED_WITH_ERRORS")
                    self.assertEqual((status["processed"], status["verified"], status["failed"]), (2, 1, 1))
                    documents = client.get(f"/api/v2/batches/{batch_id}/documents", headers=headers).json()["items"]
                    self.assertEqual(len(documents), 1)
            finally:
                get_settings.cache_clear()


if __name__ == "__main__": unittest.main()
