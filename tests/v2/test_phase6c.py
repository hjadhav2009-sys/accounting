from __future__ import annotations

import ast
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from v2.backend.app.phase6c.comparison import compare_documents, compare_excel, compare_xml
from v2.backend.app.phase6c.coordinator import IndependentParityCoordinator
from v2.backend.app.phase6c.modes import ExecutionMode
from v2.backend.app.phase6c.sqlite_migration import ExistingDataMigration
from v2.backend.app.infrastructure.shadow_migration import file_sha256, stable_legacy_uuid
from tests.v2.rls_support import set_tenant


ROOT = Path(__file__).resolve().parents[2]


def create_source(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE companies(name TEXT PRIMARY KEY,tally_company_name TEXT,gstin TEXT,state TEXT,suspense_ledger TEXT,cgst_ledger TEXT,sgst_ledger TEXT,igst_ledger TEXT);
        CREATE TABLE bank_accounts(id INTEGER PRIMARY KEY,company_name TEXT,account_hint TEXT,bank_ledger TEXT,notes TEXT);
        CREATE TABLE party_ledgers(id INTEGER PRIMARY KEY,company_name TEXT,platform TEXT,party_ledger TEXT,party_gstin TEXT,state TEXT);
        CREATE TABLE ledger_mappings(id INTEGER PRIMARY KEY,company_name TEXT,tool TEXT,platform TEXT,pattern TEXT,voucher_type TEXT,ledger TEXT,match_type TEXT,enabled INTEGER,notes TEXT);
        CREATE TABLE voucher_rules(id INTEGER PRIMARY KEY,company_name TEXT,platform TEXT,pdf_doc_type TEXT,tally_voucher_type TEXT,sign_mode TEXT);
        INSERT INTO companies VALUES('Company A','Company A','','','Suspense','CGST','SGST','IGST');
        INSERT INTO companies VALUES('Company B','Company B','','','Suspense','CGST','SGST','IGST');
        INSERT INTO bank_accounts VALUES(1,'Company A','1111','Bank A','A');
        INSERT INTO bank_accounts VALUES(2,'Company B','2222','Bank B','B');
        INSERT INTO party_ledgers VALUES(1,'Company A','market','Party A','','');
        INSERT INTO party_ledgers VALUES(2,'Company B','market','Party B','','');
        INSERT INTO ledger_mappings VALUES(1,'Company A','marketplace','market','Same Pattern','','Ledger A','contains',1,'A');
        INSERT INTO ledger_mappings VALUES(2,'Company B','marketplace','market','Same Pattern','','Ledger B','contains',1,'B');
        INSERT INTO voucher_rules VALUES(1,'Company A','market','Tax Invoice','Purchase','charge');
        INSERT INTO voucher_rules VALUES(2,'Company B','market','Tax Invoice','Purchase','charge');
    """)
    connection.commit(); connection.close()


class _Cursor:
    description = []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, query, _params=()): self.query = query
    def fetchone(self): return None


class _PreviewConnection:
    def cursor(self): return _Cursor()


class IndependentExecutionBoundaryTests(unittest.TestCase):
    def test_native_module_has_no_reference_parser_import_or_dynamic_import(self):
        path = ROOT / "v2/backend/app/phase6c/v2_native.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imports.extend(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom): imports.append(node.module or "")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"eval", "exec", "__import__"})
        joined = " ".join(imports).casefold()
        self.assertNotIn("legacy", joined)
        self.assertNotIn("reference_engine", joined)
        self.assertNotIn("services.accounting_exports", joined)

    def test_compare_does_not_pass_reference_result_as_native_hint(self):
        calls = []
        class Native:
            def process(self, content, filename): calls.append(("native", content, filename)); return {"status":"BLOCKED","reason":"NO_APPROVED_V2_TEMPLATE","canonical":{}}
        class Reference:
            def process(self, content, filename): calls.append(("reference", content, filename)); return {"status":"REFERENCE_READY","canonical":{"invoice_total":"10"}}
        result = IndependentParityCoordinator(Native(), Reference()).execute(ExecutionMode.COMPARE, b"pdf", "a.pdf")
        self.assertEqual(calls, [("reference", b"pdf", "a.pdf"), ("native", b"pdf", "a.pdf")])
        self.assertEqual(result["comparison"]["status"], "BLOCKED")

    def test_modes_are_explicit_and_complete(self):
        self.assertEqual({item.value for item in ExecutionMode}, {"LEGACY_REFERENCE", "V2_NATIVE", "COMPARE"})


class SemanticParityTests(unittest.TestCase):
    def test_document_comparison_normalizes_whitespace_case_and_numeric_format(self):
        left={"canonical":{"invoice_number":" INV-1\n","invoice_total":"1,180.00","row_count":2}}
        right={"status":"VERIFIED","canonical":{"invoice_number":"inv-1","invoice_total":"1180","row_count":2}}
        report=compare_documents(left,right)
        selected={item["field"]:item["status"] for item in report["fields"]}
        self.assertEqual(selected["invoice_number"],"MATCH");self.assertEqual(selected["invoice_total"],"MATCH")

    def test_excel_compares_schema_and_values(self):
        self.assertEqual(compare_excel([{"A":"1.00","B":" X "}],[{"A":1,"B":"x"}])["status"],"MATCH")
        self.assertEqual(compare_excel([{"A":1}],[{"B":1}])["status"],"DIFFERENCE")

    def test_xml_comparison_ignores_formatting_and_voucher_order(self):
        first=b"<ENVELOPE><VOUCHER VCHTYPE='Purchase'><DATE>20260101</DATE><LEDGERNAME>A</LEDGERNAME><AMOUNT>-10</AMOUNT></VOUCHER><VOUCHER VCHTYPE='Debit Note'><DATE>20260102</DATE></VOUCHER></ENVELOPE>"
        second=b"<ENVELOPE>\n<VOUCHER VCHTYPE='Debit Note'><DATE>20260102</DATE></VOUCHER><VOUCHER VCHTYPE='Purchase'><AMOUNT>-10.00</AMOUNT><LEDGERNAME>A</LEDGERNAME><DATE>20260101</DATE></VOUCHER></ENVELOPE>"
        self.assertEqual(compare_xml(first,second)["status"],"MATCH")


class MigrationPreviewSafetyTests(unittest.TestCase):
    def test_preview_is_read_only_company_scoped_and_hash_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"source.db";create_source(source);before=source.read_bytes();digest=file_sha256(source)
            report=ExistingDataMigration(_PreviewConnection(),uuid4(),source,digest).preview()
            self.assertEqual(source.read_bytes(),before);self.assertEqual(report["source_sha256"],report["source_sha256_after"])
        self.assertTrue(report["apply_allowed"]);self.assertEqual(report["totals"]["companies"],2)
        self.assertEqual(report["company_counts"]["Company A"]["ledger_mappings"],1)
        self.assertEqual(report["company_counts"]["Company B"]["ledger_mappings"],1)

    def test_stable_identity_is_same_on_second_run_and_tenant_specific(self):
        first,other=uuid4(),uuid4()
        self.assertEqual(stable_legacy_uuid("ledger_mappings","7",first),stable_legacy_uuid("ledger_mappings","7",first))
        self.assertNotEqual(stable_legacy_uuid("ledger_mappings","7",first),stable_legacy_uuid("ledger_mappings","7",other))

    def test_phase6c_schema_has_modes_preview_status_and_forced_rls(self):
        sql=(ROOT/"v2/backend/migrations/018_phase6c_independent_parity.sql").read_text(encoding="utf-8").upper()
        for token in ("LEGACY_REFERENCE","V2_NATIVE","COMPARE","SQLITE_MIGRATION_PREVIEWS","FORCE ROW LEVEL SECURITY"):
            self.assertIn(token,sql)
        correction=(ROOT/"v2/backend/migrations/019_phase6c_company_rls_correction.sql").read_text(encoding="utf-8").upper()
        self.assertIn("COLUMN_NAME IN ('ORGANIZATION_ID','COMPANY_ID')",correction)
        self.assertIn("AND COMPANY_ID =",correction)
        scheduler=(ROOT/"v2/backend/migrations/020_phase6c_worker_schedule_boundary.sql").read_text(encoding="utf-8").upper()
        self.assertIn("DURABLE_JOB_SCHEDULE ENABLE ROW LEVEL SECURITY",scheduler)
        self.assertIn("DURABLE_JOB_SCHEDULE FORCE ROW LEVEL SECURITY",scheduler)
        self.assertIn("DURABLE_DOCUMENT_JOBS MUST RETAIN FORCED RLS",scheduler)

    def test_ui_exposes_preview_confirm_and_reference_call_evidence(self):
        migration=(ROOT/"v2/frontend/components/DataMigrationWorkspace.tsx").read_text(encoding="utf-8")
        parity=(ROOT/"v2/frontend/components/ParityWorkspace.tsx").read_text(encoding="utf-8")
        self.assertIn("Run validation preview",migration);self.assertIn("Confirm migration",migration)
        self.assertIn("Reference calls from V2_NATIVE",parity);self.assertIn("Run independent comparison",parity)
        repository=(ROOT/"v2/backend/app/phase6c/repository.py").read_text(encoding="utf-8")
        self.assertIn("ensure_v2_draft",repository);self.assertIn("human_approval_required",repository)


@unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL"), "development PostgreSQL is not available")
class Phase6CPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from v2.backend.app.infrastructure.postgres_migrations import apply_migrations
        cls.url=os.environ["POSTGRES_TEST_DATABASE_URL"]
        connection=psycopg.connect(cls.url);apply_migrations(connection);connection.close()

    def test_two_consecutive_imports_create_no_duplicates_and_isolate_same_pattern(self):
        import psycopg
        from v2.backend.app.infrastructure.postgres import PostgresRepositories
        from tests.v2.rls_support import tenant_factory
        organization=uuid4()
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"source.db";create_source(source);digest=file_sha256(source)
            connection=psycopg.connect(self.url)
            with connection.cursor() as cursor:cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(organization,f"Stable {organization}"))
            connection.commit();migration=ExistingDataMigration(connection,organization,source,digest)
            first=migration.apply("Importer must not rename this organization");second=migration.apply("Importer must not rename this organization");connection.close()
        self.assertTrue(all(item["inserted"]==2 for item in first["tables"].values()))
        self.assertTrue(all(item["duplicates"]==0 for item in second["tables"].values()))
        company_a=stable_legacy_uuid("companies","Company A",organization);company_b=stable_legacy_uuid("companies","Company B",organization)
        repo_a=PostgresRepositories(tenant_factory(self.url,organization,company_a),organization)
        repo_b=PostgresRepositories(tenant_factory(self.url,organization,company_b),organization)
        args=("marketplace","market","prefix Same Pattern suffix","")
        self.assertEqual(repo_a.map_ledger("Company A",*args)[0],"Ledger A")
        self.assertEqual(repo_b.map_ledger("Company B",*args)[0],"Ledger B")
        connection=psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM organizations WHERE id=%s",(organization,));self.assertEqual(cursor.fetchone()[0],f"Stable {organization}")
            for company in (company_a,company_b):
                set_tenant(cursor,organization,company);cursor.execute("SELECT count(*) FROM ledger_mappings WHERE pattern='Same Pattern'");self.assertEqual(cursor.fetchone()[0],1)
        connection.rollback();connection.close()

    def test_new_fingerprint_creates_one_unapproved_v2_draft_and_sample(self):
        import psycopg
        from v2.backend.app.phase6c.repository import Phase6CRepository
        from tests.v2.rls_support import tenant_factory
        organization,company,user,document=(uuid4() for _ in range(4));signature="c"*64
        connection=psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(organization,f"Draft {organization}"))
            set_tenant(cursor,organization,company)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Draft Co','Draft Co')",(company,organization))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Draft User','ACTIVE')",(user,organization,f"{user}@example.invalid"))
            cursor.execute("INSERT INTO roles(id,organization_id,code) VALUES(%s,%s,'OWNER')",(uuid4(),organization))
            cursor.execute("""INSERT INTO documents(id,organization_id,company_id,filename,mime_type,byte_size,storage_key,status,created_by)
                VALUES(%s,%s,%s,'draft.pdf','application/pdf',1,'draft','REVIEW',%s)""",(document,organization,company,user))
            cursor.execute("INSERT INTO format_fingerprints(id,organization_id,document_id,signature,features) VALUES(%s,%s,%s,%s,'{}'::jsonb)",(uuid4(),organization,document,signature))
        connection.commit();connection.close()
        repository=Phase6CRepository(tenant_factory(self.url,organization,company,user))
        first=repository.ensure_v2_draft(organization,company,document,user,signature)
        second=repository.ensure_v2_draft(organization,company,document,user,signature)
        self.assertEqual(first["template_version_id"],second["template_version_id"]);self.assertEqual(first["status"],"DRAFT")
        self.assertEqual(repository.grant_imported_company_access(organization,user,[company],"OWNER"),1)
        self.assertEqual(repository.grant_imported_company_access(organization,user,[company],"OWNER"),0)
        connection=psycopg.connect(self.url)
        with connection.cursor() as cursor:
            set_tenant(cursor,organization,company)
            cursor.execute("SELECT count(*) FROM template_samples WHERE template_version_id=%s",(first["template_version_id"],));self.assertEqual(cursor.fetchone()[0],1)
            cursor.execute("SELECT status,engine,approved_at FROM template_versions WHERE id=%s",(first["template_version_id"],));self.assertEqual(cursor.fetchone(),("DRAFT","VISUAL_RULES",None))
            cursor.execute("SELECT count(*) FROM user_company_access WHERE user_id=%s AND company_id=%s",(user,company));self.assertEqual(cursor.fetchone()[0],1)
        connection.rollback();connection.close()

    def test_preview_blocks_existing_natural_key_with_different_uuid(self):
        import psycopg
        organization,existing_company=uuid4(),uuid4()
        connection=psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(organization,f"Conflict {organization}"))
            set_tenant(cursor,organization,existing_company)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Company A','Existing A')",(existing_company,organization))
        connection.commit();connection.close()
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"source.db";create_source(source);digest=file_sha256(source)
            connection=psycopg.connect(self.url)
            try:report=ExistingDataMigration(connection,organization,source,digest).preview()
            finally:connection.rollback();connection.close()
        self.assertFalse(report["apply_allowed"]);self.assertGreaterEqual(report["categories"]["companies"]["conflicts"],1)
        self.assertIn("TARGET_NATURAL_KEY_CONFLICTS",report["blocking_reasons"])


if __name__ == "__main__": unittest.main()
