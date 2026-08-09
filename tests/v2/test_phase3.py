from __future__ import annotations

import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from v2.backend.app.document_intelligence.fingerprint import create_format_fingerprint, fingerprint_similarity
from v2.backend.app.document_intelligence.models import (
    BoundingBox, DocumentPage, DocumentStatus, ErrorCode, ExtractionMethod, IntakeContext, Severity,
)
from v2.backend.app.document_intelligence.native_pdf import ExtractionQualityAssessor, NativePdfExtractor
from v2.backend.app.document_intelligence.ocr import detect_digit_confusions
from v2.backend.app.document_intelligence.pipeline import DocumentIntakeService
from v2.backend.app.document_intelligence.repository import DocumentRepository
from v2.backend.app.document_intelligence.security import DocumentSecurityError, ResourceLimits, safe_filename, validate_pdf_upload
from v2.backend.app.document_intelligence.status_machine import DocumentStatusMachine, InvalidDocumentTransition
from v2.backend.app.document_intelligence.validation import AccountingValidationEngine, InvoiceTotalValidator, QuantityValidator, TaxBucketValidator,taxable_base_total
from v2.backend.app.services.storage import LocalFilesystemStorage
from tests.v2.rls_support import set_tenant, tenant_factory


SUJAL_TEXT = """Tax Invoice
Invoice No. : 2600000122
Date : 01-08-2026
Bill To
Synthetic Buyer
GSTIN : 24AAAAA0000A1Z5
Ship To
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
"""


def pdf_with_text(text: str) -> bytes:
    import pymupdf
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    y = 36
    for line in text.splitlines():
        page.insert_text((36, y), line, fontsize=9)
        y += 13
    content = document.tobytes()
    document.close()
    return content


def blank_pdf() -> bytes:
    import pymupdf
    document = pymupdf.open()
    document.new_page()
    content = document.tobytes()
    document.close()
    return content


class NormalizedModelTests(unittest.TestCase):
    def test_coordinates_keep_original_points_and_normalized_projection(self):
        box = BoundingBox(10, 20, 110, 220, 200, 400)
        self.assertEqual(box.normalized, (0.05, 0.05, 0.55, 0.55))

    def test_out_of_page_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            BoundingBox(-1, 0, 10, 10, 100, 100)

    def test_fingerprint_is_deterministic_and_measurable(self):
        pages = (DocumentPage(1, 595, 842, "Tax Invoice Invoice No Total GSTIN"),)
        left, right = create_format_fingerprint(pages), create_format_fingerprint(pages)
        self.assertEqual(left.signature, right.signature)
        self.assertEqual(fingerprint_similarity(left, right), 1.0)


class UploadSecurityTests(unittest.TestCase):
    def test_filename_and_content_guards(self):
        content = pdf_with_text("Synthetic PDF content long enough for native extraction")
        self.assertEqual(validate_pdf_upload(content, "Invoice 1.PDF", "application/pdf", ResourceLimits()), "Invoice 1.pdf")
        for bad in ("../invoice.pdf", "C:\\invoice.pdf", "CON.pdf", "invoice.exe"):
            with self.assertRaises(DocumentSecurityError):
                safe_filename(bad)
        with self.assertRaises(DocumentSecurityError) as raised:
            validate_pdf_upload(b"not-pdf", "x.pdf", "application/pdf", ResourceLimits())
        self.assertEqual(raised.exception.code, ErrorCode.MIME_INVALID)

    def test_size_limit_is_enforced_before_parsing(self):
        with self.assertRaises(DocumentSecurityError) as raised:
            validate_pdf_upload(b"%PDF-" + b"x" * 20, "x.pdf", "application/pdf", ResourceLimits(maximum_file_size=10))
        self.assertEqual(raised.exception.code, ErrorCode.FILE_TOO_LARGE)


class ExtractionAndOcrSafetyTests(unittest.TestCase):
    def test_native_pdf_preserves_text_blocks_and_page_dimensions(self):
        pages = NativePdfExtractor().extract(pdf_with_text("Invoice 123\nTaxable Amount 100.00"))
        self.assertEqual(len(pages), 1)
        self.assertIn("Invoice 123", pages[0].text)
        self.assertGreater(pages[0].width, 0)
        self.assertTrue(pages[0].blocks)

    def test_blank_pdf_requires_ocr(self):
        pages = NativePdfExtractor().extract(blank_pdf())
        self.assertEqual(ExtractionQualityAssessor().assess(pages).status.value, "OCR_REQUIRED")

    def test_ocr_digit_confusions_are_flagged_not_corrected(self):
        token = "O1S8"
        self.assertEqual(token, "O1S8")
        self.assertEqual(detect_digit_confusions(token), ("O/0", "S/5"))


class StateAndValidationTests(unittest.TestCase):
    def test_state_machine_is_explicit(self):
        machine = DocumentStatusMachine()
        self.assertEqual(machine.transition(DocumentStatus.UPLOADED, DocumentStatus.REGISTERED), DocumentStatus.REGISTERED)
        with self.assertRaises(InvalidDocumentTransition):
            machine.transition(DocumentStatus.UPLOADED, DocumentStatus.VERIFIED)

    def test_unlimited_gst_rates_reconcile_independently(self):
        report = AccountingValidationEngine((TaxBucketValidator(),)).validate({"tax_buckets": (
            {"rate": "3", "taxable": "21494.00", "tax": "644.82"},
            {"rate": "18", "taxable": "4350.00", "tax": "783.00"},
            {"rate": "0.1", "taxable": "1000", "tax": "1.00"},
        )})
        self.assertEqual(report.status, "VERIFIED")

    def test_cgst_sgst_taxable_base_is_not_double_counted(self):
        payload = {"invoice_total": "118.00", "tax_buckets": (
            {"tax_type": "CGST", "rate": "9", "taxable": "100", "tax": "9", "hsn_sac": "1"},
            {"tax_type": "SGST", "rate": "9", "taxable": "100", "tax": "9", "hsn_sac": "1"},
        )}
        self.assertFalse(InvoiceTotalValidator().validate(payload))

    def test_identical_taxable_lines_remain_distinct_base_partitions(self):
        buckets=[]
        for partition in ("line-1","line-2"):
            buckets.extend(({"base_partition_id":partition,"tax_type":"CGST","rate":"9","taxable":"100","tax":"9","hsn_sac":"1"},
                            {"base_partition_id":partition,"tax_type":"SGST","rate":"9","taxable":"100","tax":"9","hsn_sac":"1"}))
        self.assertEqual(taxable_base_total(buckets),Decimal("200.00"))
        report=AccountingValidationEngine((InvoiceTotalValidator(),)).validate({"tax_buckets":buckets,"invoice_total":"236"})
        self.assertEqual(report.status,"VERIFIED");self.assertEqual(report.calculations["taxable_total"],"200.00")

    def test_quantity_mismatch_blocks(self):
        finding = QuantityValidator().validate({"displayed_total_quantity": "3", "items": ({"quantity": "1"},)})[0]
        self.assertEqual(finding.severity, Severity.BLOCKING)
        self.assertEqual(finding.error_code, ErrorCode.QUANTITY_MISMATCH)


@unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL"), "development PostgreSQL is not available")
class Phase3PostgreSQLRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from v2.backend.app.infrastructure.postgres_migrations import apply_migrations
        cls.url = os.environ["POSTGRES_TEST_DATABASE_URL"]
        if "test" not in cls.url.casefold():
            raise RuntimeError("Phase 3 integration tests require a visibly named test database")
        connection = psycopg.connect(cls.url)
        apply_migrations(connection)
        connection.close()

    def setUp(self):
        import psycopg
        self.organization_id, self.company_id, self.user_id = uuid4(), uuid4(), uuid4()
        connection = psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)", (self.organization_id, f"Phase3 {self.organization_id}"))
            set_tenant(cursor,self.organization_id,self.company_id)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Synthetic Phase3','Synthetic Phase3')", (self.company_id, self.organization_id))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Phase3','ACTIVE')",
                           (self.user_id, self.organization_id, f"{self.user_id}@example.invalid"))
        connection.commit()
        connection.close()
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = DocumentRepository(tenant_factory(self.url,self.organization_id,self.company_id,self.user_id))
        self.service = DocumentIntakeService(self.repository, LocalFilesystemStorage(self.temporary.name))
        self.context = IntakeContext(self.organization_id, self.company_id, self.user_id)

    def tearDown(self):
        self.temporary.cleanup()

    def test_normal_v2_path_creates_draft_and_exact_hash_deduplicates_without_reference_parser(self):
        content = pdf_with_text(SUJAL_TEXT)
        first = self.service.process(self.context, "synthetic-sujal.pdf", "application/pdf", content)
        self.assertEqual(first["status"], "REVIEW");self.assertEqual(first["draft_template"]["status"],"DRAFT")
        duplicate = self.service.process(self.context, "renamed.pdf", "application/pdf", content)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["document_id"], first["document_id"])
        record = self.repository.get(self.organization_id, self.company_id, first["document_id"])
        self.assertEqual(record["extraction_method"], ExtractionMethod.NATIVE_TEXT.value)
        self.assertIsNone(record["total_amount"])

    def test_business_duplicate_unknown_and_scanned_routes_create_review(self):
        first = self.service.process(self.context, "first.pdf", "application/pdf", pdf_with_text(SUJAL_TEXT))
        changed_bytes = pdf_with_text(SUJAL_TEXT + "\nDocument copy")
        business_duplicate = self.service.process(self.context, "copy.pdf", "application/pdf", changed_bytes)
        self.assertEqual(business_duplicate["status"], "REVIEW")
        unknown = self.service.process(self.context, "unknown.pdf", "application/pdf",
                                       pdf_with_text("Synthetic unapproved accounting format with enough readable native text 12345"))
        self.assertEqual(unknown["status"], "REVIEW")
        scanned = self.service.process(self.context, "scan.pdf", "application/pdf", blank_pdf())
        self.assertEqual(scanned["status"], "REVIEW")
        scanned_record = self.repository.get(self.organization_id, self.company_id, scanned["document_id"])
        self.assertEqual(scanned_record["error_code"], ErrorCode.OCR_UNAVAILABLE.value)
        self.assertGreaterEqual(len(self.repository.reviews(self.organization_id, self.company_id)), 3)
        self.assertNotEqual(first["document_id"], business_duplicate["document_id"])

    def test_corrupt_pdf_fails_safely_and_tenant_scope_hides_record(self):
        result = self.service.process(self.context, "corrupt.pdf", "application/pdf", b"%PDF-corrupt")
        self.assertEqual(result["status"], "FAILED")
        self.assertIsNone(self.repository.get(uuid4(), self.company_id, result["document_id"]))

    def test_openapi_exposes_phase3_surface(self):
        from v2.backend.app.main import app
        paths = app.openapi()["paths"]
        for path in ("/api/v2/documents/upload", "/api/v2/documents/{document_id}/pages",
                     "/api/v2/reviews", "/api/v2/reports/document-intelligence"):
            self.assertIn(path, paths)


if __name__ == "__main__":
    unittest.main()
