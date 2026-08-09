from __future__ import annotations

import os
import tempfile
import unittest
import asyncio
import io
from unittest.mock import patch
from datetime import date,datetime, timezone
from decimal import Decimal
from uuid import uuid4

from v2.backend.app.security.passwords import PasswordPolicyError, dummy_verify, hash_password, verify_password
from v2.backend.app.security.sessions import AuthenticationFailed, SessionRepository
from v2.backend.app.infrastructure.postgres_migrations import apply_migrations
from v2.backend.app.jobs.durable import DurableJobRepository
from v2.backend.app.services.storage import LocalFilesystemStorage
from v2.backend.app.security.user_admin import UserAdminRepository
from v2.backend.app.security.bootstrap import bootstrap_admin
from v2.backend.app.infrastructure.backup import create_backup,restore_backup,verify_backup
from v2.backend.app.infrastructure.service_health import collect_health
from v2.backend.app.config.settings import Settings
from v2.backend.app.infrastructure.postgres import psycopg_connection_factory,psycopg_tenant_connection_factory
from v2.backend.app.services.accounting_exports import excel_preview,export_excel,safe_export_filename
from v2.backend.app.services.accounting_workflows import MoneyParseError,_money,bank_xml,marketplace_xml,reconcile_bank_rows
from v2.backend.app.security.masters import MasterRepository
from v2.backend.app.document_intelligence.repository import DocumentRepository
from v2.backend.app.document_intelligence.models import DocumentStatus
from fastapi import HTTPException
from v2.backend.app.api.document_routes import (MAX_UPLOAD_BYTES,ROUTE_PERMISSION_MATRIX,RequestContext,
    bank_document_preview,document_content,document_excel,document_excel_preview,marketplace_document_preview,
    permission_dependency,read_bounded_upload,request_context)
from v2.backend.app.api.admin_routes import disable_user
from v2.backend.app.infrastructure.logging_config import SafeJsonFormatter
from v2.backend.app.infrastructure.retention import apply_temporary_cleanup,retention_policy,temporary_cleanup_plan
from v2.backend.app.domain.enums import Permission,Role
from tests.v2.rls_support import tenant_factory
from tests.v2.rls_support import set_tenant


class PasswordSecurityTests(unittest.TestCase):
    def test_argon2id_hash_is_salted_and_verifiable(self):
        first=hash_password("Correct-Horse-9-Battery!")
        second=hash_password("Correct-Horse-9-Battery!")
        self.assertTrue(first.startswith("$argon2id$"));self.assertNotEqual(first,second)
        self.assertEqual(verify_password(first,"Correct-Horse-9-Battery!")[0],True)
        self.assertEqual(verify_password(first,"wrong-password")[0],False)

    def test_password_policy_rejects_short_and_common_values(self):
        for value in ("Short1!","password123"):
            with self.subTest(value=value),self.assertRaises(PasswordPolicyError): hash_password(value)

    def test_unknown_user_dummy_hash_is_precomputed(self):
        import inspect
        source=inspect.getsource(dummy_verify)
        self.assertNotIn("_HASHER.hash",source)
        dummy_verify("attacker-controlled")

    def test_non_development_runtime_fails_closed_without_secure_auth(self):
        with self.assertRaisesRegex(RuntimeError,"PRODUCTION_AUTH_ENABLED"):
            Settings(environment="production").validate_runtime_security()
        Settings(environment="production",production_auth_enabled=True,session_cookie_secure=True,
                 database_url="postgresql://configured").validate_runtime_security()

    def test_permission_dependency_denies_viewer_upload_and_review(self):
        viewer=RequestContext(uuid4(),uuid4(),uuid4(),frozenset({Role.VIEWER}))
        for permission in (Permission.DOCUMENT_UPLOAD,Permission.DOCUMENT_REVIEW,Permission.TEMPLATE_CREATE):
            with self.subTest(permission=permission),self.assertRaises(HTTPException) as raised:
                permission_dependency(permission)(viewer)
            self.assertEqual(raised.exception.status_code,403)
        self.assertEqual(ROUTE_PERMISSION_MATRIX[("POST","/api/v2/documents/upload")],Permission.DOCUMENT_UPLOAD)
        self.assertEqual(ROUTE_PERMISSION_MATRIX[("POST","/api/v2/reviews/{review_id}/resolve")],Permission.DOCUMENT_REVIEW)

    def test_upload_reader_rejects_before_unbounded_body_read(self):
        from starlette.datastructures import UploadFile
        upload=UploadFile(io.BytesIO(b"x"*(MAX_UPLOAD_BYTES+1)),filename="large.pdf")
        with self.assertRaises(HTTPException) as raised:asyncio.run(read_bounded_upload(upload))
        self.assertEqual(raised.exception.status_code,413)

    def test_next_document_has_security_headers(self):
        config=(__import__('pathlib').Path(__file__).parents[2]/"v2/frontend/next.config.ts").read_text(encoding="utf-8")
        for header in ("Content-Security-Policy","X-Content-Type-Options","X-Frame-Options","Permissions-Policy"):
            self.assertIn(header,config)

    def test_document_and_ai_route_permission_matrices_are_exhaustive(self):
        from v2.backend.app.api.document_routes import router as document_router
        from v2.backend.app.api.ai_routes import AI_ROUTE_PERMISSION_MATRIX,router as ai_router
        from v2.backend.app.api.permission_matrix import API_PERMISSION_MATRIX
        from v2.backend.app.main import app
        document_paths={(method,path.path) for path in document_router.routes for method in path.methods}
        ai_paths={(method,path.path) for path in ai_router.routes for method in path.methods}
        self.assertEqual(document_paths,set(ROUTE_PERMISSION_MATRIX));self.assertEqual(ai_paths,set(AI_ROUTE_PERMISSION_MATRIX))
        public_prefixes=("/api/v2/auth/","/api/v2/dev/");public_paths={"/health","/api/v2/system/info"}
        protected={(method.upper(),path) for path,operations in app.openapi()["paths"].items()
                   for method in operations if path.startswith("/api/v2/") and path not in public_paths
                   and not path.startswith(public_prefixes)}
        catalogued=set(ROUTE_PERMISSION_MATRIX)|set(AI_ROUTE_PERMISSION_MATRIX)|set(API_PERMISSION_MATRIX)
        self.assertEqual(protected,catalogued-{("POST","/api/v2/documents")})

    def test_launcher_uses_certified_health_and_strict_pid_ownership(self):
        from pathlib import Path
        start=Path("runtime/Start-BusinessAutomation.ps1").read_text(encoding="utf-8")
        stop=Path("runtime/Stop-BusinessAutomation.ps1").read_text(encoding="utf-8")
        for token in ("--api-key","LLAMA_CONTEXT_SIZE","LLAMA_THREADS","LLAMA_GPU_LAYERS","--no-webui","Wait-Healthy"):
            self.assertIn(token,start)
        for token in ("creation_time","command_hash","project_marker","ownedCommand -and $ownedExecutable -and $sameCreation -and $sameCommand"):
            self.assertIn(token,stop)

    def test_normal_v2_product_path_has_no_reference_service_import(self):
        from pathlib import Path
        for name in ("document_intelligence/pipeline.py","document_intelligence/routing.py",
                     "services/accounting_exports.py","services/accounting_workflows.py","api/document_routes.py"):
            source=Path("v2/backend/app",name).read_text(encoding="utf-8")
            self.assertNotIn("services.legacy",source);self.assertNotIn("from .legacy",source)

    def test_frontend_has_typed_error_client_and_no_mojibake(self):
        from pathlib import Path
        source=Path("v2/frontend/lib/api.ts").read_text(encoding="utf-8")
        for token in ("class ApiError","apiRequest<T>","X-Request-ID","X-CSRF-Token","PERMISSION_DENIED"):
            self.assertIn(token,source)
        for path in Path("v2/frontend").rglob("*.tsx"):
            text=path.read_text(encoding="utf-8");self.assertNotRegex(text,r"[ÃÂ]|â[€“€¦]")

    def test_backup_is_encrypted_and_integrity_verified(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            root=os.path.join(directory,"storage");os.makedirs(root);Path(root,"source.pdf").write_bytes(b"private source")
            destination=os.path.join(directory,"certified.bapbackup")
            def fake_dump(command,**_kwargs):
                output=command[command.index("--file")+1];Path(output).write_bytes(b"synthetic postgres custom dump")
                return subprocess.CompletedProcess(command,0,b"",b"")
            result=create_backup("dbname=synthetic",__import__('pathlib').Path(root),__import__('pathlib').Path(destination),"Backup-Secure!8",runner=fake_dump)
            self.assertTrue(result["encrypted"]);self.assertNotIn(b"private source",Path(destination).read_bytes())
            manifest=verify_backup(__import__('pathlib').Path(destination),"Backup-Secure!8")
            self.assertEqual(manifest["source_count"],1)

    def test_health_contract_has_no_secrets(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            result=collect_health(Settings(storage_root=Path(directory),cloudflare_api_token="never-return-this"))
        self.assertFalse(result["secrets_exposed"]);self.assertNotIn("never-return-this",str(result))
        self.assertTrue({"frontend","backend","postgresql","storage","job_worker","legacy_compatibility"}.issubset(result["components"]))

    def test_certified_pdf_to_excel_preview_and_workbook(self):
        from pathlib import Path
        normalized={"invoice_number":"INV-1","invoice_date":"2026-08-01","supplier":"Synthetic",
            "items":[{"description":"Item","hsn_sac":"6109","quantity":"2","unit_rate":"50","taxable":"100","total":"118"}],
            "tax_buckets":[{"base_partition_id":"line-1","rate":"18","taxable":"100","hsn_sac":"6109"}]}
        preview=excel_preview(b"not-read-by-v2-export","synthetic-invoice.pdf",normalized)
        self.assertEqual(preview["template"],"V2_NATIVE");self.assertEqual(preview["summary"]["rows"],1)
        self.assertEqual(safe_export_filename("../unsafe invoice.pdf"),"unsafe_invoice.xlsx")
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory,"verified.xlsx");export_excel(preview["rows"],preview["item_rows"],output)
            self.assertTrue(output.read_bytes().startswith(b"PK"))

    def test_marketplace_purchase_and_credit_note_xml_semantics(self):
        profile={"tally_company_name":"Test Books","gst_ledgers":{"CGST":"INPUT CGST","SGST":"INPUT SGST","IGST":"INPUT IGST"}}
        base={"Source PDF":"synthetic.pdf","Platform":"amazon","Mapped Ledger":"Marketplace Expense","Party Ledger":"Amazon Party",
              "Invoice No":"INV-1","Date":"20260801","Taxable":"100.00","CGST":"9.00","SGST":"9.00","IGST":"0.00","Status":"OK"}
        purchase={**base,"PDF Doc Type":"Tax Invoice","Tally Voucher Type":"Purchase","Sign Mode":"charge"}
        xml=marketplace_xml({"export_allowed":True,"profile":profile,"rows":[purchase]}).decode()
        self.assertIn("<VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>",xml);self.assertIn("<AMOUNT>118.00</AMOUNT>",xml);self.assertIn("<AMOUNT>-100.00</AMOUNT>",xml)
        credit={**base,"PDF Doc Type":"Credit Note","Tally Voucher Type":"Debit Note","Sign Mode":"reverse","Invoice No":"CN-1"}
        xml=marketplace_xml({"export_allowed":True,"profile":profile,"rows":[credit]}).decode()
        self.assertIn("<VOUCHERTYPENAME>Debit Note</VOUCHERTYPENAME>",xml);self.assertIn("<AMOUNT>-118.00</AMOUNT>",xml);self.assertIn("<AMOUNT>100.00</AMOUNT>",xml)

    def test_bank_reconciliation_blocks_mismatch_and_verified_xml_balances(self):
        rows=[{"Txn Date":"01/08/2026","Description":"Synthetic receipt","Deposit":"100.00","Withdrawal":"0","Balance":"1100.00","Mapped Ledger":"Sales","Status":"OK"},
              {"Txn Date":"02/08/2026","Description":"Synthetic payment","Deposit":"0","Withdrawal":"40.00","Balance":"1060.00","Mapped Ledger":"Expense","Status":"OK"}]
        reconciliation=reconcile_bank_rows(rows);self.assertEqual(reconciliation["status"],"VERIFIED");self.assertEqual(reconciliation["difference"],"0.00")
        broken=[*rows[:-1],{**rows[-1],"Balance":"1061.00"}];self.assertEqual(reconcile_bank_rows(broken)["status"],"BLOCKED")
        continuity=[rows[0],{**rows[1],"Balance":"1105.00","Deposit":"10.00","Withdrawal":"5.00"}]
        self.assertEqual(reconcile_bank_rows(continuity)["status"],"REVIEW")
        blank=[rows[0],{**rows[1],"Description":""}];self.assertEqual(reconcile_bank_rows(blank)["status"],"REVIEW")
        content=bank_xml({"export_allowed":True,"bank_account":{"bank_ledger":"Test Bank"},"rows":rows}).decode()
        self.assertIn("<VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>",content);self.assertIn("<VOUCHERTYPENAME>Payment</VOUCHERTYPENAME>",content)

    def test_malformed_nonblank_accounting_amount_never_becomes_zero(self):
        with self.assertRaises(MoneyParseError) as raised:_money("INR-not-a-number","Taxable")
        self.assertEqual(raised.exception.field,"Taxable");self.assertEqual(raised.exception.raw,"INR-not-a-number")
        self.assertEqual(_money("","Taxable"),Decimal("0.00"))

    def test_structured_logging_redacts_secrets_and_retention_never_selects_originals(self):
        import json,logging,time
        record=logging.LogRecord("v2.test",logging.ERROR,"",0,"password=private-value token:abc123",(),None);record.document_text="never include"
        payload=json.loads(SafeJsonFormatter().format(record));self.assertNotIn("private-value",str(payload));self.assertNotIn("abc123",str(payload));self.assertNotIn("document_text",payload)
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            root=Path(directory);queue=root/"_queue";queue.mkdir();temporary=queue/"old.bin";active=queue/"active.bin";original=root/"tenant"/"original.pdf";original.parent.mkdir();
            for path in (temporary,active,original):path.write_bytes(b"content");os.utime(path,(time.time()-10*86400,time.time()-10*86400))
            plan=temporary_cleanup_plan(root,["_queue/active.bin"],7);self.assertEqual(plan,[temporary.resolve()]);self.assertEqual(apply_temporary_cleanup(root,plan),1);self.assertTrue(active.exists());self.assertTrue(original.exists())
        policy=retention_policy(Settings());self.assertFalse(policy["source_documents"]["automatic_delete"]);self.assertFalse(policy["accounting_audit"]["automatic_delete"])


@unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL") and os.getenv("POSTGRES_RESTORE_ADMIN_URL"),
                     "isolated restore administrator is not configured")
class BackupRestorePostgresTests(unittest.TestCase):
    def test_encrypted_postgres_backup_restores_into_isolated_database(self):
        import psycopg
        from pathlib import Path
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict,make_conninfo
        source=os.environ["POSTGRES_TEST_DATABASE_URL"];values=conninfo_to_dict(os.environ["POSTGRES_RESTORE_ADMIN_URL"])
        restore_name=f"phase6_restore_{uuid4().hex}";admin_values=dict(values);admin_values["dbname"]="postgres"
        target_values=dict(values);target_values["dbname"]=restore_name
        admin=psycopg.connect(make_conninfo(**admin_values),autocommit=True)
        try:
            with admin.cursor() as cursor:cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restore_name)))
            with tempfile.TemporaryDirectory() as directory:
                backup=Path(directory,"roundtrip.bapbackup");source_storage=Path(directory,"source");source_storage.mkdir();Path(source_storage,"proof.bin").write_bytes(b"restore proof")
                create_backup(source,source_storage,backup,"Restore-Test!92")
                restored_storage=Path(directory,"restored")
                result=restore_backup(backup,"Restore-Test!92",make_conninfo(**target_values),restored_storage)
                self.assertTrue(result["restored"]);self.assertEqual(Path(restored_storage,"proof.bin").read_bytes(),b"restore proof")
                restored=psycopg.connect(make_conninfo(**target_values))
                try:
                    with restored.cursor() as cursor:cursor.execute("SELECT count(*) FROM schema_migrations");self.assertGreaterEqual(cursor.fetchone()[0],13)
                finally:restored.close()
        finally:
            with admin.cursor() as cursor:
                cursor.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()",(restore_name,))
                cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(restore_name)))
            admin.close()


@unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL"),"development PostgreSQL is not available")
class AuthenticationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg;cls.url=os.environ["POSTGRES_TEST_DATABASE_URL"]
        connection=psycopg.connect(cls.url);apply_migrations(connection);connection.close()

    def create_identity(self):
        org,company,user,role=uuid4(),uuid4(),uuid4(),uuid4()
        connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(org,f"Phase6 {org}"))
            cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(org),))
            cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company),))
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Phase6','Phase6')",(company,org))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Phase6 User','ACTIVE')",(user,org,f"{user}@example.invalid"))
            cursor.execute("INSERT INTO roles(id,organization_id,code) VALUES(%s,%s,'ACCOUNTANT')",(role,org))
            cursor.execute("INSERT INTO user_company_access(user_id,company_id,role_id) VALUES(%s,%s,%s)",(user,company,role))
            cursor.execute("INSERT INTO user_credentials(user_id,password_hash) VALUES(%s,%s)",(user,hash_password("Phase6-Secure-Password!9")))
        connection.commit();connection.close()
        return org,company,user,f"Phase6 {org}"

    def test_login_session_company_scope_csrf_and_revocation(self):
        org,company,user,organization=self.create_identity();repo=SessionRepository(lambda:self.psycopg.connect(self.url))
        issued=repo.authenticate(f"{user}@example.invalid","Phase6-Secure-Password!9",company,"synthetic-agent","127.0.0.1",organization_name=organization)
        self.assertEqual((issued.identity.organization_id,issued.identity.company_id),(org,company))
        self.assertFalse(repo.resolve(issued.token,company).csrf_token_valid)
        self.assertTrue(repo.resolve(issued.token,company,issued.csrf_token).csrf_token_valid)
        self.assertIsNone(repo.resolve(issued.token,uuid4()))
        self.assertTrue(repo.revoke(issued.token,user));self.assertIsNone(repo.resolve(issued.token,company))

    def test_same_email_is_scoped_by_organization_and_company_list_is_authorized(self):
        shared="shared.phase6@example.invalid";password="Phase6-Secure-Password!9";identities=[]
        for label in ("One","Two"):
            org,company,user=uuid4(),uuid4(),uuid4();role=uuid4();connection=self.psycopg.connect(self.url)
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(org,f"Phase6 Realm {label} {org}"))
                set_tenant(cursor,org,company)
                cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,%s,%s)",(company,org,label,label))
                cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,%s,'ACTIVE')",(user,org,shared,label))
                cursor.execute("INSERT INTO roles(id,organization_id,code) VALUES(%s,%s,'VIEWER')",(role,org))
                cursor.execute("INSERT INTO user_company_access(user_id,company_id,role_id) VALUES(%s,%s,%s)",(user,company,role))
                cursor.execute("INSERT INTO user_credentials(user_id,password_hash) VALUES(%s,%s)",(user,hash_password(password)))
            connection.commit();connection.close();identities.append((org,company,user,f"Phase6 Realm {label} {org}"))
        repo=SessionRepository(lambda:self.psycopg.connect(self.url));target=identities[1]
        issued=repo.authenticate(shared,password,target[1],organization_name=target[3])
        self.assertEqual(issued.identity.user_id,target[2])
        self.assertEqual([item["id"] for item in repo.authorized_companies(issued.token)],[target[1]])

    def test_first_owner_bootstrap_is_login_ready(self):
        connection=self.psycopg.connect(self.url);organization=f"Bootstrap {uuid4()}"
        result=bootstrap_admin(connection,organization,"Primary Company",f"owner-{uuid4()}@example.invalid","Owner User","Bootstrap-Secure!7")
        connection.close();self.assertEqual(len(result["organization_id"]),36)

    def test_failed_login_is_generic_and_counted(self):
        _org,company,user,organization=self.create_identity();repo=SessionRepository(lambda:self.psycopg.connect(self.url))
        with self.assertRaisesRegex(AuthenticationFailed,"invalid credentials"):
            repo.authenticate(f"{user}@example.invalid","incorrect",company,organization_name=organization)
        connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("SELECT failed_login_count,last_login_at FROM users WHERE id=%s",(user,));row=cursor.fetchone()
        connection.close();self.assertEqual(row[0],1);self.assertIsNone(row[1])

    def test_unknown_login_is_persistently_throttled_without_storing_identifier(self):
        repo=SessionRepository(lambda:self.psycopg.connect(self.url));realm=f"Missing {uuid4()}"
        for _ in range(10):
            with self.assertRaisesRegex(AuthenticationFailed,"invalid credentials"):
                repo.authenticate("missing@example.invalid","incorrect",None,remote_address="192.0.2.10",organization_name=realm)
        connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("SELECT min(length(key_sha256)),max(length(key_sha256)) FROM auth_login_throttles");lengths=cursor.fetchone()
        connection.close();self.assertEqual(lengths,(64,64))

    def test_connection_pool_returns_connections_and_clears_tenant_transaction_state(self):
        org,company,user,_organization=self.create_identity();tenant=psycopg_tenant_connection_factory(self.url,org,company,user)
        connection=tenant()
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.organization_id',true),current_setting('app.company_id',true)");self.assertEqual(cursor.fetchone(),(str(org),str(company)))
        connection.close();plain=psycopg_connection_factory(self.url)()
        with plain.cursor() as cursor:
            cursor.execute("SELECT coalesce(current_setting('app.organization_id',true),''),coalesce(current_setting('app.company_id',true),'')");self.assertEqual(cursor.fetchone(),("",""))
        plain.close()


@unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL"),"development PostgreSQL is not available")
class RlsPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg;cls.url=os.environ["POSTGRES_TEST_DATABASE_URL"]
        connection=psycopg.connect(cls.url);apply_migrations(connection);connection.close()

    def test_rls_fails_closed_for_wrong_organization_and_company(self):
        org_a,org_b,company_a,company_b,user=uuid4(),uuid4(),uuid4(),uuid4(),uuid4()
        connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s),(%s,%s)",(org_a,f"RLS A {org_a}",org_b,f"RLS B {org_b}"))
            cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(org_a),))
            cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company_a),))
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'A','A')",(company_a,org_a))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'RLS','ACTIVE')",(user,org_a,f"{user}@example.invalid"))
            cursor.execute("""INSERT INTO documents(id,organization_id,company_id,filename,mime_type,byte_size,storage_key,status,created_by)
                VALUES(%s,%s,%s,'a.pdf','application/pdf',1,'a','UPLOADED',%s)""",
                (uuid4(),org_a,company_a,user))
            cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(org_b),))
            cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company_b),))
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'B','B')",(company_b,org_b))
            cursor.execute("""INSERT INTO documents(id,organization_id,company_id,filename,mime_type,byte_size,storage_key,status,created_by)
                VALUES(%s,%s,%s,'b.pdf','application/pdf',1,'b','UPLOADED',%s)""",
                (uuid4(),org_b,company_b,user))
        connection.commit();connection.close()
        connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(org_a),))
            cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company_a),))
            cursor.execute("SELECT filename FROM documents ORDER BY filename")
            self.assertEqual(cursor.fetchall(),[("a.pdf",)])
            cursor.execute("SELECT count(*) FROM documents WHERE organization_id=%s",(org_b,))
            self.assertEqual(cursor.fetchone()[0],0)
        connection.rollback();connection.close()

    def test_financial_year_uses_document_date_and_filters_reporting(self):
        org,company,user=uuid4(),uuid4(),uuid4();document=uuid4();connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(org,f"FY {org}"));set_tenant(cursor,org,company)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'FY','FY')",(company,org))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'FY User','ACTIVE')",(user,org,f"{user}@example.invalid"))
            cursor.execute("""INSERT INTO documents(id,organization_id,company_id,filename,mime_type,byte_size,storage_key,status,created_by)
                VALUES(%s,%s,%s,'fy.pdf','application/pdf',1,'fy','EXTRACTED',%s)""",(document,org,company,user))
        connection.commit();connection.close();repository=DocumentRepository(tenant_factory(self.url,org,company,user))
        repository.transition(org,company,document,DocumentStatus.EXTRACTED,DocumentStatus.VALIDATING,invoice_date=date(2026,3,31))
        years=repository.financial_years(org,company);self.assertEqual(years[0]["label"],"2025-26")
        self.assertEqual(repository.financial_year(org,company,years[0]["id"])["starts_on"],date(2025,4,1))
        self.assertIn("users",repository.unified_report(org,company,"2025-04-01","2026-03-31"))

    def test_download_and_admin_idor_attempts_fail_before_storage_or_export(self):
        org_a,org_b,company_a,company_b,user_a,user_b,document_b=[uuid4() for _ in range(7)];connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s),(%s,%s)",(org_a,f"IDOR A {org_a}",org_b,f"IDOR B {org_b}"))
            set_tenant(cursor,org_a,company_a);cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'A','A')",(company_a,org_a));cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'A','ACTIVE')",(user_a,org_a,f"{user_a}@example.invalid"))
            set_tenant(cursor,org_b,company_b);cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'B','B')",(company_b,org_b));cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'B','ACTIVE')",(user_b,org_b,f"{user_b}@example.invalid"));cursor.execute("""INSERT INTO documents(id,organization_id,company_id,filename,original_filename,safe_filename,mime_type,byte_size,storage_key,status,created_by)
                VALUES(%s,%s,%s,'private.pdf','private.pdf','private.pdf','application/pdf',1,'private/path','VERIFIED',%s)""",(document_b,org_b,company_b,user_b))
        connection.commit();connection.close();context=RequestContext(org_a,company_a,user_a,frozenset({Role.ADMIN,Role.ACCOUNTANT}))
        settings=Settings(database_url=self.url,storage_root=__import__('pathlib').Path(tempfile.gettempdir()))
        with patch("v2.backend.app.api.document_routes.get_settings",return_value=settings):
            for endpoint in (document_content,document_excel_preview,marketplace_document_preview,bank_document_preview,document_excel):
                with self.subTest(endpoint=endpoint.__name__),self.assertRaises(HTTPException) as raised:endpoint(document_b,context)
                self.assertEqual(raised.exception.status_code,404)
        with patch("v2.backend.app.api.admin_routes.get_settings",return_value=settings):
            with self.assertRaises(HTTPException) as raised:disable_user(user_b,context)
            self.assertEqual(raised.exception.status_code,404)
        viewer=RequestContext(org_a,company_a,user_a,frozenset({Role.VIEWER}))
        with self.assertRaises(HTTPException) as raised:document_excel(document_b,viewer)
        self.assertEqual(raised.exception.status_code,403)


@unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL"),"development PostgreSQL is not available")
class DurableJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg;cls.url=os.environ["POSTGRES_TEST_DATABASE_URL"]
        connection=psycopg.connect(cls.url);apply_migrations(connection);connection.close()

    def identity(self):
        org,company,user=uuid4(),uuid4(),uuid4();connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(org,f"Jobs {org}"))
            set_tenant(cursor,org,company)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Jobs','Jobs')",(company,org))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Jobs','ACTIVE')",(user,org,f"{user}@example.invalid"))
        connection.commit();connection.close();return org,company,user

    def test_source_is_durable_and_job_is_claimed_once(self):
        org,company,user=self.identity();repo=DurableJobRepository(lambda:self.psycopg.connect(self.url))
        with tempfile.TemporaryDirectory() as directory:
            storage=LocalFilesystemStorage(directory);job_id=uuid4();batch_id=uuid4()
            connection=self.psycopg.connect(self.url)
            with connection.cursor() as cursor:
                set_tenant(cursor,org,company)
                cursor.execute("""INSERT INTO document_batches(id,organization_id,company_id,created_by,total,queued,status)
                    VALUES(%s,%s,%s,%s,1,1,'QUEUED')""",(batch_id,org,company,user))
            connection.commit();connection.close()
            stored=storage.put_pending(org,company,job_id,"synthetic.pdf",b"synthetic queued bytes")
            self.assertEqual(LocalFilesystemStorage(directory).read(stored.storage_key),b"synthetic queued bytes")
            queued=repo.enqueue(org,company,batch_id,user,stored.storage_key,"synthetic.pdf","application/pdf",stored.sha256)
            claimed=repo.claim("worker-a",batch_id);self.assertEqual(claimed.id,queued)
            self.assertIsNone(repo.claim("worker-b",batch_id))
            document_id=uuid4();connection=self.psycopg.connect(self.url)
            with connection.cursor() as cursor:
                set_tenant(cursor,org,company)
                cursor.execute("""INSERT INTO documents(id,organization_id,company_id,filename,mime_type,byte_size,storage_key,status,created_by)
                    VALUES(%s,%s,%s,'synthetic.pdf','application/pdf',1,'synthetic','UPLOADED',%s)""",
                    (document_id,org,company,user))
            connection.commit();connection.close()
            repo.heartbeat(claimed,50);self.assertEqual(repo.finish(claimed,document_id),"COMPLETED")

    def test_queued_job_can_be_cancelled_before_claim(self):
        org,company,user=self.identity();repo=DurableJobRepository(lambda:self.psycopg.connect(self.url))
        queued=repo.enqueue(org,company,None,user,"_queue/synthetic","synthetic.pdf","application/pdf","a"*64)
        self.assertTrue(repo.cancel(org,company,queued));self.assertEqual(repo.status(queued),"CANCELLED")

    def test_rls_has_no_cross_tenant_fallback_when_context_missing(self):
        connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM documents")
            self.assertEqual(cursor.fetchone()[0],0)
        connection.rollback();connection.close()


@unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL"),"development PostgreSQL is not available")
class UserAdministrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg;cls.url=os.environ["POSTGRES_TEST_DATABASE_URL"]
        connection=psycopg.connect(cls.url);apply_migrations(connection);connection.close()

    def test_admin_create_list_disable_and_reset_never_exposes_hash(self):
        org,company,actor=uuid4(),uuid4(),uuid4();connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(org,f"Admin {org}"));set_tenant(cursor,org,company)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Admin','Admin')",(company,org))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Actor','ACTIVE')",(actor,org,f"{actor}@example.invalid"))
        connection.commit();connection.close()
        repository=UserAdminRepository(tenant_factory(self.url,org,company,actor))
        created=repository.create_user(org,actor,"new.user@example.invalid","New User","Temporary-Secure!9",[(company,Role.ACCOUNTANT)])
        listed=repository.list_users(org);item=next(row for row in listed if row["id"]==created["id"])
        self.assertNotIn("password_hash",item);self.assertEqual(item["companies"][0]["role"],"ACCOUNTANT")
        self.assertTrue(repository.reset_password(org,actor,created["id"],"Replacement-Secure!8"))
        self.assertTrue(repository.set_status(org,actor,created["id"],"DISABLED"))
        self.assertEqual(next(row for row in repository.list_users(org) if row["id"]==created["id"])["status"],"DISABLED")

    def test_company_masters_are_tenant_scoped_masked_and_audited(self):
        org,company,actor=uuid4(),uuid4(),uuid4();connection=self.psycopg.connect(self.url)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(org,f"Masters {org}"));set_tenant(cursor,org,company)
            cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Masters','Masters Books')",(company,org))
            cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Master Admin','ACTIVE')",(actor,org,f"{actor}@example.invalid"))
        connection.commit();connection.close();repository=MasterRepository(tenant_factory(self.url,org,company,actor))
        repository.save_bank(org,company,actor,"7890","Test Bank");repository.save_party(org,company,actor,"amazon","Amazon Party")
        repository.save_gst(org,company,actor,"CGST","INPUT CGST");repository.save_voucher(org,company,actor,"amazon","Tax Invoice","Purchase","charge")
        snapshot=repository.snapshot(org,company);self.assertEqual(snapshot["bank_accounts"][0]["account_hint"],"••••7890")
        self.assertNotIn("account_hint_token",snapshot["bank_accounts"][0]);self.assertEqual(snapshot["party_ledgers"][0]["party_ledger"],"Amazon Party")
        import io
        from openpyxl import load_workbook
        workbook=load_workbook(io.BytesIO(repository.mapping_workbook(org,company)));sheet=workbook["Ledger Mappings"]
        sheet.append(["marketplace","amazon","Synthetic fee","Tax Invoice","Expense Ledger","contains",10,True]);stream=io.BytesIO();workbook.save(stream)
        preview=repository.preview_mapping_workbook(org,company,actor,stream.getvalue());self.assertEqual(preview["summary"]["inserted"],1);self.assertTrue(preview["apply_allowed"])
        applied=repository.apply_mapping_preview(org,company,actor,preview["preview_id"]);self.assertEqual(applied["status"],"APPLIED")
        snapshot=repository.snapshot(org,company);self.assertEqual(snapshot["ledger_mappings"][0]["ledger"],"Expense Ledger")


if __name__=="__main__": unittest.main()
