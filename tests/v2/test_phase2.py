import os
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from v2.backend.app.config import Settings
from v2.backend.app.domain import CompanyAccess, Job, JobStatus, Money, Permission, Role, TaxBucket
from v2.backend.app.domain.mapping import mapping_matches,normalize_platform,normalize_text
from v2.backend.app.infrastructure.migration_verifier import inspect_sqlite
from v2.backend.app.infrastructure.shadow_migration import stable_legacy_uuid
from v2.backend.app.jobs import InvalidJobTransition, PersistentJobManager
from v2.backend.app.repositories.factory import build_repositories
from v2.backend.app.security import AuthorizationService, TenantAccessService
from v2.backend.app.services.parity import ParityRecorder, ParityStatus, ShadowRepositories, classify
from tests.v2.rls_support import set_tenant, tenant_factory


ROOT = Path(__file__).resolve().parents[2]


class Phase2PublicSafetyTests(unittest.TestCase):
    def test_legacy_account_shaped_seed_is_absent_from_public_source(self):
        source = (ROOT / "shared" / "database.py").read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC-ACCOUNT", source)

    def test_private_fixture_directory_is_ignored_except_instructions(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("tests/private_fixtures/*", ignore)
        self.assertIn("!tests/private_fixtures/README.example.md", ignore)


class LegacyIdentityAndMigrationTests(unittest.TestCase):
    def test_legacy_identity_is_deterministic_and_tenant_specific(self):
        org_a, org_b = uuid4(), uuid4()
        self.assertEqual(stable_legacy_uuid("companies", "1", org_a), stable_legacy_uuid("companies", "1", org_a))
        self.assertNotEqual(stable_legacy_uuid("companies", "1", org_a), stable_legacy_uuid("companies", "1", org_b))

    def test_phase2_schema_has_precision_identity_tax_and_candidate_rls(self):
        sql = (ROOT / "v2" / "backend" / "migrations" / "002_phase2_shadow.sql").read_text(encoding="utf-8").upper()
        self.assertIn("CREATE TABLE LEGACY_IDENTITY_MAP", sql)
        self.assertIn("CREATE TABLE INVOICE_TAX_BUCKETS", sql)
        self.assertIn("NUMERIC(18,2)", sql)
        self.assertIn("CREATE POLICY", sql)
        self.assertNotIn("ENABLE ROW LEVEL SECURITY", sql)

    def test_dry_run_reports_hash_and_never_writes(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.db"
            connection = sqlite3.connect(path)
            for table in ("companies", "bank_accounts", "party_ledgers", "ledger_mappings", "voucher_rules"):
                connection.execute(f"CREATE TABLE {table}(id TEXT)")
                connection.execute(f"INSERT INTO {table} VALUES('synthetic')")
            connection.commit()
            connection.close()
            before = path.read_bytes()
            report = inspect_sqlite(path)
            self.assertEqual(before, path.read_bytes())
        self.assertEqual(report["sha256_before"], report["sha256_after"])
        self.assertEqual(report["mode"], "dry-run")


class ShadowParityTests(unittest.TestCase):
    class Repository:
        def __init__(self, value=None, error=False):
            self.value, self.error = value, error

        def lookup(self, *_args):
            if self.error:
                raise RuntimeError("synthetic shadow outage")
            return self.value

    def test_parity_statuses(self):
        self.assertEqual(classify("Ledger", "Ledger"), ParityStatus.MATCH)
        self.assertEqual(classify("Ledger", None), ParityStatus.MISSING_IN_POSTGRES)
        self.assertEqual(classify(None, "Ledger"), ParityStatus.EXTRA_IN_POSTGRES)
        self.assertEqual(classify(" Ledger ", "ledger"), ParityStatus.NORMALIZATION_DIFFERENCE)
        self.assertEqual(classify("A", "B"), ParityStatus.MISMATCH)

    def test_shadow_always_returns_sqlite_even_on_postgres_failure(self):
        recorder = ParityRecorder()
        shadow = ShadowRepositories(self.Repository("AUTHORITATIVE"), self.Repository(error=True), recorder)
        self.assertEqual(shadow.lookup("synthetic"), "AUTHORITATIVE")
        self.assertEqual(recorder.summary()["counts"]["SHADOW_ERROR"], 1)


class TenantAndAuthorizationTests(unittest.TestCase):
    def test_shared_mapping_matcher_supports_all_five_modes(self):
        cases=(("Service Fee ABC","fee","contains"),("Service-Fee ABC","service fee","smart_contains"),
               ("  Exact Value  ","exact value","equals"),("Prefix value","prefix","starts_with"),
               ("Invoice 42","Invoice\\s+\\d+","regex"))
        for text,pattern,mode in cases:
            with self.subTest(mode=mode):self.assertTrue(mapping_matches(text,pattern,mode))
        self.assertFalse(mapping_matches("anything","[broken","regex"));self.assertFalse(mapping_matches("anything","","contains"))
        self.assertEqual(normalize_platform("  Amazon Marketplace  "),"amazonmarketplace")
        self.assertEqual(normalize_text("  Ledger\n Name  "),"Ledger Name")
    def test_identical_patterns_do_not_grant_cross_tenant_access(self):
        org_a, org_b, company_a1, company_a2 = uuid4(), uuid4(), uuid4(), uuid4()
        access = CompanyAccess(org_a, company_a1, uuid4(), frozenset({"ACCOUNTANT"}))
        service = TenantAccessService()
        service.require_company(access, org_a, company_a1)
        with self.assertRaises(PermissionError):
            service.require_company(access, org_a, company_a2)
        with self.assertRaises(PermissionError):
            service.require_company(access, org_b, company_a1)

    def test_all_roles_use_centralized_permissions(self):
        auth = AuthorizationService()
        self.assertTrue(auth.is_allowed({Role.OWNER}, Permission.USER_ADMIN))
        self.assertTrue(auth.is_allowed({Role.ADMIN}, Permission.COMPANY_ADMIN))
        self.assertTrue(auth.is_allowed({Role.ACCOUNTANT}, Permission.XML_EXPORT))
        self.assertTrue(auth.is_allowed({Role.OPERATOR}, Permission.DOCUMENT_UPLOAD))
        self.assertTrue(auth.is_allowed({Role.REVIEWER}, Permission.DOCUMENT_REVIEW))
        self.assertEqual(auth.is_allowed({Role.VIEWER}, Permission.MAPPING_EDIT), False)


class PrecisionAndPersistenceContractTests(unittest.TestCase):
    def test_money_precision_cases(self):
        self.assertEqual(Money("0.005").amount, Decimal("0.01"))
        self.assertEqual(Money("9999999999.99").amount, Decimal("9999999999.99"))
        self.assertEqual(Money("-1.005").amount, Decimal("-1.01"))
        self.assertEqual((Money("21494.00").amount * Decimal("0.03")).quantize(Decimal("0.01")), Decimal("644.82"))
        self.assertEqual((Money("4350.00").amount * Decimal("0.18")).quantize(Decimal("0.01")), Decimal("783.00"))

    def test_multiple_gst_buckets_remain_independent(self):
        buckets = (
            TaxBucket("IGST", "3", Money("21494.00"), Money("644.82")),
            TaxBucket("IGST", "18", Money("4350.00"), Money("783.00")),
        )
        self.assertEqual([(b.rate, b.taxable.amount, b.tax.amount) for b in buckets], [
            (Decimal("3"), Decimal("21494.00"), Decimal("644.82")),
            (Decimal("18"), Decimal("4350.00"), Decimal("783.00")),
        ])

    def test_document_hash_uniqueness_is_company_and_tenant_scoped(self):
        sql = (ROOT / "v2" / "backend" / "migrations" / "001_v2_foundation.sql").read_text(encoding="utf-8")
        self.assertIn("UNIQUE (organization_id, company_id, sha256)", sql)

    def test_persistent_job_transitions_and_safe_error_code(self):
        class Repository:
            def __init__(self): self.items = {}
            def save(self, job): self.items[job.job_id] = job
            def get(self, job_id): return self.items.get(job_id)
        repo = Repository()
        manager = PersistentJobManager(repo)
        job = Job("synthetic", uuid4(), uuid4(), uuid4())
        manager.save(job)
        manager.transition(job.job_id, JobStatus.RUNNING, 10)
        manager.transition(job.job_id, JobStatus.FAILED, 10, "E" * 200)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(len(job.error_code), 80)
        with self.assertRaises(InvalidJobTransition):
            manager.transition(job.job_id, JobStatus.RUNNING)


class ConfigurationSafetyTests(unittest.TestCase):
    def test_no_postgres_authoritative_mode_exists(self):
        with self.assertRaises(ValueError):
            build_repositories(Settings(database_adapter_mode="POSTGRES_AUTHORITATIVE"), uuid4())

    def test_production_does_not_enable_dev_endpoints_from_default(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            settings = Settings.from_environment()
        self.assertEqual(settings.environment, "production")
        self.assertFalse(settings.dev_endpoints_enabled)
        self.assertFalse(settings.postgres_shadow_enabled)


@unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL"), "development PostgreSQL is not available")
class PostgreSQLRuntimeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from v2.backend.app.infrastructure.postgres_migrations import apply_migrations
        cls.url = os.environ["POSTGRES_TEST_DATABASE_URL"]
        if not any(marker in cls.url.lower() for marker in ("_test", "test")):
            raise RuntimeError("integration tests require a visibly named test database")
        connection = psycopg.connect(cls.url)
        apply_migrations(connection)
        connection.close()

    def test_migrations_execute(self):
        import psycopg
        connection = psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM schema_migrations")
            self.assertGreaterEqual(cursor.fetchone()[0], 2)
        connection.close()

    def test_shadow_import_is_idempotent_and_parity_matches(self):
        import psycopg
        import sqlite3
        from v2.backend.app.infrastructure.postgres import PostgresRepositories
        from v2.backend.app.infrastructure.shadow_migration import ShadowImporter
        organization_id = uuid4()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "shadow.db"
            db = sqlite3.connect(source)
            db.executescript("""
                CREATE TABLE companies(name TEXT PRIMARY KEY,tally_company_name TEXT,gstin TEXT,state TEXT,suspense_ledger TEXT,cgst_ledger TEXT,sgst_ledger TEXT,igst_ledger TEXT);
                CREATE TABLE bank_accounts(id INTEGER PRIMARY KEY,company_name TEXT,account_hint TEXT,bank_ledger TEXT,notes TEXT);
                CREATE TABLE party_ledgers(id INTEGER PRIMARY KEY,company_name TEXT,platform TEXT,party_ledger TEXT,party_gstin TEXT,state TEXT);
                CREATE TABLE ledger_mappings(id INTEGER PRIMARY KEY,company_name TEXT,tool TEXT,platform TEXT,pattern TEXT,voucher_type TEXT,ledger TEXT,match_type TEXT,enabled INTEGER,notes TEXT);
                CREATE TABLE voucher_rules(id INTEGER PRIMARY KEY,company_name TEXT,platform TEXT,pdf_doc_type TEXT,tally_voucher_type TEXT,sign_mode TEXT);
                INSERT INTO companies VALUES('Synthetic Co','Synthetic Co','','','Suspense','CGST','SGST','IGST');
                INSERT INTO bank_accounts VALUES(1,'Synthetic Co','SYNTHETIC','Synthetic Bank','');
                INSERT INTO party_ledgers VALUES(1,'Synthetic Co','market','Synthetic Party','','');
                INSERT INTO ledger_mappings VALUES(1,'Synthetic Co','marketplace','market','Collection Fee','','Ledger A','contains',1,'');
                INSERT INTO voucher_rules VALUES(1,'Synthetic Co','market','Tax Invoice','Purchase','charge');
            """)
            db.commit()
            db.close()
            connection = psycopg.connect(self.url)
            importer = ShadowImporter(connection, organization_id, f"Synthetic Organization {organization_id}")
            first = importer.import_sqlite(source)
            second = importer.import_sqlite(source)
            connection.close()
        self.assertTrue(all(item["inserted"] == 1 for item in first["tables"].values()))
        self.assertTrue(all(item["updated"] == 1 for item in second["tables"].values()))
        imported_company=stable_legacy_uuid("companies","Synthetic Co",organization_id)
        repository = PostgresRepositories(tenant_factory(self.url,organization_id,imported_company), organization_id)
        self.assertEqual(repository.party_ledger("Synthetic Co", " market\n"), "Synthetic Party")
        self.assertEqual(repository.map_ledger("Synthetic Co", "marketplace", "market", "A Collection Fee charged"), ("Ledger A", "Collection Fee"))

    def test_identical_mapping_is_tenant_isolated(self):
        import psycopg
        from v2.backend.app.infrastructure.postgres import PostgresRepositories
        org_a, org_b = uuid4(), uuid4()
        company_a, company_b = uuid4(), uuid4()
        connection = psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s),(%s,%s)", (org_a, f"Org {org_a}", org_b, f"Org {org_b}"))
            set_tenant(cursor,org_a,company_a)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Company','Company')", (company_a, org_a))
            cursor.execute("""INSERT INTO ledger_mappings(id,organization_id,company_id,tool,platform,pattern,ledger,match_type)
                            VALUES(%s,%s,%s,'marketplace','market','Collection Fee','Ledger A','contains')""",(uuid4(), org_a, company_a))
            set_tenant(cursor,org_b,company_b)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Company','Company')", (company_b, org_b))
            cursor.execute("""INSERT INTO ledger_mappings(id,organization_id,company_id,tool,platform,pattern,ledger,match_type)
                            VALUES(%s,%s,%s,'marketplace','market','Collection Fee','Ledger B','contains')""",(uuid4(), org_b, company_b))
        connection.commit()
        connection.close()
        repo_a = PostgresRepositories(tenant_factory(self.url,org_a,company_a), org_a)
        repo_b = PostgresRepositories(tenant_factory(self.url,org_b,company_b), org_b)
        self.assertEqual(repo_a.map_ledger("Company", "marketplace", "market", "Collection Fee")[0], "Ledger A")
        self.assertEqual(repo_b.map_ledger("Company", "marketplace", "market", "Collection Fee")[0], "Ledger B")

    def test_multi_gst_document_job_audit_and_reporting_persist(self):
        import psycopg
        from v2.backend.app.domain import AuditEvent, DocumentIdentity
        from v2.backend.app.infrastructure.postgres import PostgresRepositories
        from v2.backend.app.services.reporting import PostgresReportingService
        org, company, user, document, invoice = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
        connection = psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)", (org, f"Org {org}"))
            set_tenant(cursor,org,company)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Synthetic','Synthetic')", (company, org))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Synthetic','ACTIVE')", (user, org, f"{user}@example.invalid"))
            cursor.execute("INSERT INTO invoices(id,organization_id,company_id,invoice_number,supplier,document_type,total) VALUES(%s,%s,%s,'INV-X','Synthetic','Tax Invoice',27271.82)", (invoice, org, company))
            cursor.execute("""INSERT INTO invoice_tax_buckets(id,invoice_id,tax_type,rate,taxable,tax) VALUES
                            (%s,%s,'IGST',3,21494.00,644.82),(%s,%s,'IGST',18,4350.00,783.00)""",
                           (uuid4(), invoice, uuid4(), invoice))
        connection.commit()
        connection.close()
        repo = PostgresRepositories(tenant_factory(self.url,org,company,user), org)
        identity = DocumentIdentity(document, org, company, "a" * 64, "synthetic.pdf", "application/pdf", 9, datetime.now(timezone.utc), user)
        self.assertTrue(repo.save_document(identity, f"{org}/{company}/{document}"))
        self.assertFalse(repo.save_document(identity, f"{org}/{company}/{document}"))
        job = Job("synthetic", org, company, user)
        repo.save(job)
        repo.append(AuditEvent("MIGRATION_SHADOW_IMPORTED", org, company, user, "job", job.job_id))
        summary = PostgresReportingService(tenant_factory(self.url,org,company,user), org).invoice_summary(company)
        self.assertEqual(summary["igst"], Decimal("1427.82"))

    def test_numeric_precision_and_tenant_scoped_duplicates(self):
        import psycopg
        from v2.backend.app.domain import DocumentIdentity
        from v2.backend.app.infrastructure.postgres import PostgresRepositories
        values = [Decimal("0.01"), Decimal("0.03"), Decimal("0.18"), Decimal("0.005"), Decimal("-0.005"), Decimal("9" * 16 + ".99")]
        connection = psycopg.connect(self.url)
        with connection.cursor() as cursor:
            for value in values:
                cursor.execute("SELECT %s::numeric", (value,))
                self.assertEqual(cursor.fetchone()[0], value)
        connection.close()

        org_a, org_b, company_a, company_b, user_a, user_b = (uuid4() for _ in range(6))
        connection = psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s),(%s,%s)", (org_a, f"Org {org_a}", org_b, f"Org {org_b}"))
            set_tenant(cursor,org_a,company_a)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'A','A')", (company_a, org_a))
            set_tenant(cursor,org_b,company_b)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'B','B')", (company_b, org_b))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'A','ACTIVE'),(%s,%s,%s,'B','ACTIVE')",
                           (user_a, org_a, f"{user_a}@example.invalid", user_b, org_b, f"{user_b}@example.invalid"))
        connection.commit()
        connection.close()
        digest = "b" * 64
        repo_a = PostgresRepositories(tenant_factory(self.url,org_a,company_a,user_a), org_a)
        repo_b = PostgresRepositories(tenant_factory(self.url,org_b,company_b,user_b), org_b)
        doc_a = DocumentIdentity(uuid4(), org_a, company_a, digest, "a.pdf", "application/pdf", 1, datetime.now(timezone.utc), user_a)
        doc_b = DocumentIdentity(uuid4(), org_b, company_b, digest, "b.pdf", "application/pdf", 1, datetime.now(timezone.utc), user_b)
        self.assertTrue(repo_a.save_document(doc_a, f"{org_a}/{doc_a.document_id}"))
        self.assertFalse(repo_a.save_document(doc_a, f"{org_a}/{doc_a.document_id}"))
        self.assertTrue(repo_b.save_document(doc_b, f"{org_b}/{doc_b.document_id}"))

    def test_jobs_and_audit_survive_repository_recreation(self):
        import psycopg
        from v2.backend.app.domain import AuditEvent
        from v2.backend.app.infrastructure.postgres import PostgresAuditRepository, PostgresJobRepository
        org, company, user = uuid4(), uuid4(), uuid4()
        connection = psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)", (org, f"Org {org}"))
            set_tenant(cursor,org,company)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Jobs','Jobs')", (company, org))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Jobs','ACTIVE')", (user, org, f"{user}@example.invalid"))
        connection.commit()
        connection.close()

        def manager():
            return PersistentJobManager(PostgresJobRepository(tenant_factory(self.url,org,company,user), org))

        completed = Job("completed", org, company, user)
        manager().save(completed)
        manager().transition(completed.job_id, JobStatus.RUNNING, 25)
        manager().transition(completed.job_id, JobStatus.COMPLETED, 100)
        self.assertEqual(manager().get(completed.job_id).status, JobStatus.COMPLETED)
        review = Job("review", org, company, user)
        manager().save(review)
        manager().transition(review.job_id, JobStatus.RUNNING)
        manager().transition(review.job_id, JobStatus.REVIEW, 60)
        self.assertEqual(manager().get(review.job_id).status, JobStatus.REVIEW)
        failed = Job("failed", org, company, user)
        manager().save(failed)
        manager().transition(failed.job_id, JobStatus.RUNNING)
        manager().transition(failed.job_id, JobStatus.FAILED, 40, "SYNTHETIC_ERROR")
        with self.assertRaises(InvalidJobTransition):
            manager().transition(failed.job_id, JobStatus.RUNNING)

        audit = PostgresAuditRepository(tenant_factory(self.url,org,company,user), org)
        first = AuditEvent("MIGRATION_SHADOW_IMPORTED", org, company, user, "job", completed.job_id)
        second = AuditEvent("PARITY_MISMATCH_DETECTED", org, company, user, "job", review.job_id, reason="synthetic reference only")
        audit.append(first)
        PostgresAuditRepository(tenant_factory(self.url,org,company,user), org).append(second)
        events = PostgresAuditRepository(tenant_factory(self.url,org,company,user), org).list_events()
        self.assertEqual([event.event_id for event in events], [first.event_id, second.event_id])
        self.assertNotIn("postgresql://", repr(events).lower())

    def test_reporting_queries_and_rls_candidate_policy(self):
        import psycopg
        from v2.backend.app.services.reporting import PostgresReportingService
        org_a, org_b, company_a, company_b, user_a, document = (uuid4() for _ in range(6))
        bank_account = uuid4()
        connection = psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s),(%s,%s)", (org_a, f"Org {org_a}", org_b, f"Org {org_b}"))
            set_tenant(cursor,org_a,company_a)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Report A','Report A')", (company_a, org_a))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Report','ACTIVE')", (user_a, org_a, f"{user_a}@example.invalid"))
            cursor.execute("""INSERT INTO documents(id,organization_id,company_id,filename,mime_type,byte_size,storage_key,status,created_by)
                            VALUES(%s,%s,%s,'synthetic.pdf','application/pdf',1,'synthetic','VERIFIED',%s)""", (document, org_a, company_a, user_a))
            cursor.execute("INSERT INTO bank_accounts(id,organization_id,company_id,account_hint_token,bank_ledger) VALUES(%s,%s,%s,'SYNTHETIC','Synthetic Bank')", (bank_account, org_a, company_a))
            cursor.execute("""INSERT INTO bank_transactions(id,organization_id,company_id,bank_account_id,transaction_date,narration,debit,credit)
                            VALUES(%s,%s,%s,%s,current_date,'Synthetic debit',125.25,0),(%s,%s,%s,%s,current_date,'Synthetic credit',0,500.50)""",
                           (uuid4(), org_a, company_a, bank_account, uuid4(), org_a, company_a, bank_account))
            cursor.execute("""INSERT INTO marketplace_documents(id,organization_id,company_id,document_id,platform,supplier,document_type,invoice_number,voucher_type,total_amount)
                            VALUES(%s,%s,%s,%s,'synthetic-market','Synthetic','Tax Invoice','SYN-1','Purchase',625.75)""",
                           (uuid4(), org_a, company_a, document))
            cursor.execute("""INSERT INTO ledger_mappings(id,organization_id,company_id,tool,platform,pattern,ledger,match_type)
                            VALUES(%s,%s,%s,'marketplace','market','RLS Pattern','Ledger A','contains')""",
                           (uuid4(), org_a, company_a))
            set_tenant(cursor,org_b,company_b)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Report B','Report B')", (company_b, org_b))
            cursor.execute("""INSERT INTO ledger_mappings(id,organization_id,company_id,tool,platform,pattern,ledger,match_type)
                            VALUES(%s,%s,%s,'marketplace','market','RLS Pattern','Ledger B','contains')""",
                           (uuid4(), org_b, company_b))
        connection.commit()
        connection.close()

        reporting = PostgresReportingService(tenant_factory(self.url,org_a,company_a,user_a), org_a)
        self.assertEqual(reporting.document_summary(company_a)["verified"], 1)
        self.assertEqual(reporting.bank_summary(company_a), {"credits": Decimal("500.50"), "debits": Decimal("125.25")})
        self.assertEqual(reporting.marketplace_summary(company_a)["platforms"][0]["total"], Decimal("625.75"))

        connection = psycopg.connect(self.url)
        try:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE ledger_mappings ENABLE ROW LEVEL SECURITY")
                cursor.execute("ALTER TABLE ledger_mappings FORCE ROW LEVEL SECURITY")
                cursor.execute("SELECT set_config('app.organization_id',%s,true)", (str(org_a),))
                cursor.execute("SELECT set_config('app.company_id',%s,true)", (str(company_a),))
                cursor.execute("SELECT count(*) FROM ledger_mappings WHERE pattern='RLS Pattern'")
                self.assertEqual(cursor.fetchone()[0], 1)
            connection.rollback()
        finally:
            connection.close()

    def test_default_company_is_not_read_across_forced_rls_boundary(self):
        import psycopg
        from v2.backend.app.infrastructure.postgres import PostgresRepositories
        org,current,default,user=uuid4(),uuid4(),uuid4(),uuid4();connection=psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(org,f"RLS default {org}"))
            set_tenant(cursor,org,current);cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Current','Current')",(current,org))
            set_tenant(cursor,org,default);cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Default Company','Default Company')",(default,org))
            cursor.execute("INSERT INTO ledger_mappings(id,organization_id,company_id,tool,platform,pattern,ledger,match_type) VALUES(%s,%s,%s,'bank','','Inherited only','Default Ledger','contains')",(uuid4(),org,default))
        connection.commit();connection.close();repository=PostgresRepositories(tenant_factory(self.url,org,current,user),org)
        self.assertEqual(repository.map_ledger("Current","bank","","Inherited only"),("Suspense","UNMATCHED_TO_SUSPENSE"))


if __name__ == "__main__":
    unittest.main()
