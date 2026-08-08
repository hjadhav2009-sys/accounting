import gc
import sqlite3
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from shared import database as legacy_db
from tests.parsers.test_pdf_to_excel_parsers import SUJAL_SYNTHETIC_TEXT
from v2.backend.app.api.routes import health, system_info
from v2.backend.app.audit import InMemoryAuditRepository
from v2.backend.app.config import Settings
from v2.backend.app.domain import (
    AuditEvent,
    ExtractionResult,
    InvoiceHeader,
    InvoiceLine,
    Job,
    JobStatus,
    Money,
    Permission,
    Role,
    TaxBucket,
)
from v2.backend.app.infrastructure.migration_verifier import inspect_sqlite
from v2.backend.app.infrastructure.sqlite_repositories import LegacySQLiteRepositories
from v2.backend.app.jobs import InMemoryJobManager, InvalidJobTransition
from v2.backend.app.main import app
from v2.backend.app.security import AuthorizationService
from v2.backend.app.services.fingerprints import accounting_duplicate_signature, sha256_bytes
from v2.backend.app.services.legacy import LegacyPdfToExcelService
from v2.backend.app.services.storage import LocalFilesystemStorage


class DomainFoundationTests(unittest.TestCase):
    def test_money_uses_decimal_and_half_up_currency_rounding(self):
        self.assertEqual(Money(Decimal("10.125")).amount, Decimal("10.13"))
        self.assertEqual(Money("1.10") + Money("2.20"), Money("3.30"))

    def test_one_invoice_supports_multiple_tax_buckets(self):
        three = TaxBucket("IGST", Decimal("3"), Money("100"), Money("3"), "7113")
        eighteen = TaxBucket("IGST", Decimal("18"), Money("200"), Money("36"), "7326")
        result = ExtractionResult(
            document_id=uuid4(),
            header=InvoiceHeader("SYN-1", date(2026, 8, 7), "Synthetic Supplier", "Tax Invoice"),
            lines=(InvoiceLine("Item", Decimal("1"), Money("300"), Money("300"), tax_buckets=(three, eighteen)),),
            tax_buckets=(three, eighteen),
        )
        self.assertEqual([bucket.rate for bucket in result.tax_buckets], [Decimal("3"), Decimal("18")])

    def test_money_rejects_cross_currency_addition(self):
        with self.assertRaises(ValueError):
            _ = Money("1", "INR") + Money("1", "USD")


class FingerprintAndStorageTests(unittest.TestCase):
    def test_document_sha256_is_stable_and_sensitive_to_bytes(self):
        self.assertEqual(sha256_bytes(b"same"), sha256_bytes(b"same"))
        self.assertNotEqual(sha256_bytes(b"same"), sha256_bytes(b"different"))

    def test_accounting_signature_normalizes_identity_fields(self):
        left = accounting_duplicate_signature(" ACME ", "Supplier\nOne", "Tax Invoice", "INV-1", "2026-08-07", "100.00")
        right = accounting_duplicate_signature("acme", "supplier one", "tax invoice", "inv-1", "2026-08-07", "100.00")
        self.assertEqual(left, right)

    def test_local_storage_round_trip_and_path_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalFilesystemStorage(tmp)
            stored = storage.put(uuid4(), uuid4(), uuid4(), "synthetic.pdf", b"synthetic document")
            self.assertEqual(storage.read(stored.storage_key), b"synthetic document")
            self.assertEqual(stored.sha256, sha256_bytes(b"synthetic document"))
            with self.assertRaises(ValueError):
                storage.read("../../outside")


class JobAuthorizationAuditTests(unittest.TestCase):
    def test_job_transitions_and_terminal_protection(self):
        job = Job("document.extraction", uuid4(), uuid4(), uuid4())
        manager = InMemoryJobManager()
        manager.save(job)
        manager.transition(job.job_id, JobStatus.RUNNING, 25)
        manager.transition(job.job_id, JobStatus.COMPLETED, 100)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        with self.assertRaises(InvalidJobTransition):
            manager.transition(job.job_id, JobStatus.RUNNING)

    def test_permissions_are_centralized_by_role(self):
        auth = AuthorizationService()
        self.assertTrue(auth.is_allowed({Role.ACCOUNTANT}, Permission.XML_EXPORT))
        self.assertFalse(auth.is_allowed({Role.VIEWER}, Permission.MAPPING_EDIT))

    def test_audit_repository_is_append_oriented(self):
        repository = InMemoryAuditRepository()
        event = AuditEvent("XML_EXPORTED", uuid4(), uuid4(), uuid4(), "xml_export", uuid4(), reason="synthetic test")
        repository.append(event)
        self.assertEqual(repository.list_events(), (event,))


class ApiAndConfigurationTests(unittest.TestCase):
    def test_fastapi_health_and_system_info_are_non_sensitive(self):
        self.assertEqual(health().status, "ok")
        info = system_info().model_dump()
        self.assertEqual(info["postgres_cutover"], "disabled")
        self.assertEqual(info["ai_inference"], "disabled")
        self.assertNotIn("cloudflare_api_token", info)
        self.assertIn("/health", app.openapi()["paths"])

    def test_configuration_starts_without_secrets(self):
        settings = Settings()
        self.assertEqual(settings.cloudflare_api_token, "")
        self.assertEqual(settings.postgres_url, "")


class AdapterAndMigrationTests(unittest.TestCase):
    def test_fresh_database_uses_only_synthetic_public_bank_seed(self):
        old_path = legacy_db.DB_PATH
        temp = tempfile.TemporaryDirectory()
        try:
            legacy_db.DB_PATH = Path(temp.name) / "fresh.db"
            legacy_db.reset_db_cache()
            legacy_db.init_db(force=True)
            connection = sqlite3.connect(legacy_db.DB_PATH)
            connection.row_factory = sqlite3.Row
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM bank_accounts WHERE company_name='Default Company'"
            )]
            connection.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["account_hint"], "SYNTHETIC-ACCOUNT")
            self.assertIn("SYNTHETIC", rows[0]["bank_ledger"])
        finally:
            legacy_db.DB_PATH = old_path
            legacy_db.reset_db_cache()
            gc.collect()
            temp.cleanup()

    def test_existing_database_bank_account_is_never_reseeded(self):
        old_path = legacy_db.DB_PATH
        temp = tempfile.TemporaryDirectory()
        try:
            path = Path(temp.name) / "existing.db"
            legacy_db.DB_PATH = path
            legacy_db.reset_db_cache()
            legacy_db.init_db(force=True)
            connection = sqlite3.connect(path)
            connection.execute("DELETE FROM bank_accounts")
            connection.execute(
                "INSERT INTO bank_accounts(company_name,account_hint,bank_ledger,notes) VALUES(?,?,?,?)",
                ("Default Company", "LOCAL-EXISTING", "LOCAL BANK", "local"),
            )
            connection.commit()
            connection.close()
            legacy_db.reset_db_cache()
            legacy_db.init_db(force=True)
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM bank_accounts WHERE company_name='Default Company'"
            )]
            connection.close()
            self.assertEqual([row["account_hint"] for row in rows], ["LOCAL-EXISTING"])
        finally:
            legacy_db.DB_PATH = old_path
            legacy_db.reset_db_cache()
            gc.collect()
            temp.cleanup()

    def test_legacy_pdf_adapter_calls_certified_parser(self):
        gst_rows, item_rows = LegacyPdfToExcelService().parse_text(
            "sujal_tax_invoice", SUJAL_SYNTHETIC_TEXT, "synthetic.txt"
        )
        self.assertEqual(sum(row["QTY"] for row in gst_rows), 420)
        self.assertEqual({row["RATE"] for row in gst_rows}, {"3", "18"})
        self.assertEqual(len(item_rows), 2)

    def test_sqlite_compatibility_adapter_uses_legacy_behavior(self):
        old_path = legacy_db.DB_PATH
        temp = tempfile.TemporaryDirectory()
        try:
            legacy_db.DB_PATH = Path(temp.name) / "adapter.db"
            legacy_db.reset_db_cache()
            legacy_db.init_db(force=True)
            adapter = LegacySQLiteRepositories()
            self.assertEqual(adapter.get_company(" Default   Company ")["name"], "Default Company")
            self.assertNotEqual(adapter.party_ledger("Default Company", " AMAZON\n").lower(), "suspense")
        finally:
            legacy_db.DB_PATH = old_path
            legacy_db.reset_db_cache()
            gc.collect()
            temp.cleanup()

    def test_postgres_migration_verifier_is_read_only_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.db"
            connection = sqlite3.connect(path)
            for table in ("companies", "bank_accounts", "party_ledgers", "ledger_mappings", "voucher_rules"):
                connection.execute(f"CREATE TABLE {table}(id TEXT)")
                connection.execute(f"INSERT INTO {table}(id) VALUES ('synthetic')")
            connection.commit()
            connection.close()
            report = inspect_sqlite(path)
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(report["target"], "postgresql-disabled")
        self.assertTrue(all(item["source_count"] == 1 for item in report["tables"].values()))

    def test_postgres_foundation_migration_has_no_cutover_statements(self):
        sql = (Path(__file__).resolve().parents[2] / "v2" / "backend" / "migrations" / "001_v2_foundation.sql").read_text(encoding="utf-8")
        upper = sql.upper()
        self.assertIn("CREATE TABLE ORGANIZATIONS", upper)
        self.assertIn("CREATE TABLE AUDIT_LOGS", upper)
        self.assertNotIn("DROP TABLE", upper)
        self.assertNotIn("INSERT INTO", upper)


if __name__ == "__main__":
    unittest.main()
