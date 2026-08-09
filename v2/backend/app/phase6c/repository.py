from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Callable
from uuid import UUID, uuid4

from ..document_intelligence.models import to_jsonable
from ..template_studio.schema import empty_definition


class Phase6CRepository:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self.connection_factory = connection_factory

    @contextmanager
    def _cursor(self):
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor: yield cursor
            connection.commit()
        except Exception:
            connection.rollback(); raise
        finally: connection.close()

    def approved_template(self, organization_id: UUID, company_id: UUID, signature: str) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute("""SELECT tv.id,tv.version,tv.status,tv.engine,tv.definition,f.name AS family_name,
                tv.approved_by,tv.approved_at,tv.approval_evidence
                FROM format_fingerprints fp JOIN document_format_families f ON f.id=fp.family_id
                JOIN template_versions tv ON tv.family_id=f.id
                WHERE fp.organization_id=%s AND fp.signature=%s AND f.organization_id=%s AND f.company_id=%s
                  AND tv.status='APPROVED' AND tv.engine='VISUAL_RULES'
                ORDER BY tv.version DESC LIMIT 1""", (organization_id, signature, organization_id, company_id))
            row = cursor.fetchone()
            if not row: return None
            columns = [item.name for item in cursor.description]
            return dict(zip(columns, row))

    def ensure_v2_draft(self, organization_id: UUID, company_id: UUID, document_id: UUID,
                        actor_id: UUID, signature: str) -> dict[str, Any]:
        """Create one deterministic Studio draft shell per native fingerprint; never approve it."""
        definition = empty_definition("INVOICE")
        definition["metadata"] = {"assistant": "available_in_template_studio", "source": "phase6c-native-fingerprint",
                                  "fingerprint": signature, "human_approval_required": True}
        with self._cursor() as cursor:
            cursor.execute("""SELECT id,name FROM document_format_families WHERE organization_id=%s AND company_id=%s
                AND metadata->>'phase6c_fingerprint'=%s FOR UPDATE""", (organization_id, company_id, signature))
            family = cursor.fetchone()
            if family: family_id, family_name = family
            else:
                family_id = uuid4(); family_name = f"V2 Native {signature[:12]}"
                cursor.execute("""INSERT INTO document_format_families(id,organization_id,company_id,name,document_type,
                    description,metadata,created_by) VALUES(%s,%s,%s,%s,'Tax Invoice',%s,%s::jsonb,%s)""",
                    (family_id, organization_id, company_id, family_name,
                     "Independent V2 draft created from a native document fingerprint; requires Studio testing and approval.",
                     json.dumps({"phase6c_fingerprint": signature, "engine": "V2_NATIVE"}), actor_id))
            cursor.execute("""SELECT id,version,status FROM template_versions WHERE family_id=%s
                AND status IN ('DRAFT','TESTING') AND engine='VISUAL_RULES' ORDER BY version DESC LIMIT 1""", (family_id,))
            version = cursor.fetchone()
            if version: version_id, version_number, status = version
            else:
                cursor.execute("SELECT coalesce(max(version),0)+1 FROM template_versions WHERE family_id=%s", (family_id,))
                version_number = cursor.fetchone()[0]; version_id = uuid4(); status = "DRAFT"
                cursor.execute("""INSERT INTO template_versions(id,family_id,version,status,definition,created_by,
                    validation_profile,engine,change_summary,updated_by) VALUES(%s,%s,%s,'DRAFT',%s::jsonb,%s,
                    'INVOICE','VISUAL_RULES','Phase 6C new native format draft',%s)""",
                    (version_id, family_id, version_number, json.dumps(definition), actor_id, actor_id))
            cursor.execute("UPDATE format_fingerprints SET family_id=%s WHERE organization_id=%s AND document_id=%s",
                           (family_id, organization_id, document_id))
            cursor.execute("""INSERT INTO template_samples(template_version_id,document_id,expected_result,notes,added_by)
                VALUES(%s,%s,'{}'::jsonb,'Independent V2 sample; reference output is intentionally not copied.',%s)
                ON CONFLICT(template_version_id,document_id) DO UPDATE SET status='ACTIVE'""",
                (version_id, document_id, actor_id))
        return {"family_id": family_id, "family_name": family_name, "template_version_id": version_id,
                "template_version": version_number, "status": status, "engine": "VISUAL_RULES",
                "human_approval_required": True, "ai_actions_available_in_template_studio": True}

    def save_parity(self, organization_id: UUID, company_id: UUID, document_id: UUID, actor_id: UUID,
                    mode: str, payload: dict[str, Any]) -> UUID:
        run_id = uuid4(); comparison = payload.get("comparison", {})
        status = comparison.get("status") or payload.get("v2", {}).get("status") or payload.get("reference", {}).get("status")
        if status not in {"MATCH", "DIFFERENCE", "MISSING_LEGACY", "MISSING_V2", "BLOCKED"}: status = "BLOCKED"
        reference, native = payload.get("reference", {}), payload.get("v2", {})
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO document_parity_runs(id,organization_id,company_id,document_id,mode,status,
                legacy_template,v2_template_version_id,legacy_result,v2_result,summary,created_by)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)""",
                (run_id, organization_id, company_id, document_id, mode, status, reference.get("template"),
                 native.get("template_version_id"), json.dumps(to_jsonable(reference)), json.dumps(to_jsonable(native)),
                 json.dumps(to_jsonable(comparison)), actor_id))
            for item in comparison.get("fields", []):
                cursor.execute("""INSERT INTO document_parity_fields(id,parity_run_id,field_path,status,legacy_value,v2_value)
                    VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb)""", (uuid4(), run_id, item["field"], item["status"],
                    json.dumps(to_jsonable(item.get("legacy"))), json.dumps(to_jsonable(item.get("v2")))))
        return run_id

    def parity_runs(self, organization_id: UUID, company_id: UUID) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute("""SELECT r.id,r.document_id,d.filename,r.mode,r.status,r.legacy_template,
                r.v2_template_version_id,r.summary,r.created_at FROM document_parity_runs r
                JOIN documents d ON d.id=r.document_id WHERE r.organization_id=%s AND r.company_id=%s
                ORDER BY r.created_at DESC LIMIT 200""", (organization_id, company_id))
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def parity_run(self, organization_id: UUID, company_id: UUID, run_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute("""SELECT r.*,d.filename FROM document_parity_runs r JOIN documents d ON d.id=r.document_id
                WHERE r.id=%s AND r.organization_id=%s AND r.company_id=%s""", (run_id, organization_id, company_id))
            row = cursor.fetchone()
            if not row: return None
            result = dict(zip([item.name for item in cursor.description], row))
            cursor.execute("SELECT field_path,status,legacy_value,v2_value FROM document_parity_fields WHERE parity_run_id=%s ORDER BY field_path", (run_id,))
            result["fields"] = [dict(zip([item.name for item in cursor.description], item)) for item in cursor.fetchall()]
            return result

    def save_migration_preview(self, organization_id: UUID, actor_id: UUID, source_file: str,
                               source_hash: str, expected_hash: str, report: dict[str, Any]) -> UUID:
        preview_id = uuid4()
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO sqlite_migration_previews(id,organization_id,source_file,source_sha256,
                expected_sha256,status,report,created_by) VALUES(%s,%s,%s,%s,%s,'PREVIEW',%s::jsonb,%s)""",
                (preview_id, organization_id, source_file, source_hash, expected_hash,
                 json.dumps(to_jsonable(report)), actor_id))
        return preview_id

    def migration_preview(self, organization_id: UUID, preview_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM sqlite_migration_previews WHERE id=%s AND organization_id=%s", (preview_id, organization_id))
            row = cursor.fetchone()
            return dict(zip([item.name for item in cursor.description], row)) if row else None

    def mark_migration_applied(self, organization_id: UUID, preview_id: UUID, report: dict[str, Any]) -> None:
        with self._cursor() as cursor:
            cursor.execute("""UPDATE sqlite_migration_previews SET status='APPLIED',applied_at=now(),
                report=report || %s::jsonb WHERE id=%s AND organization_id=%s AND status='PREVIEW'""",
                (json.dumps(to_jsonable({"apply": report})), preview_id, organization_id))
            if cursor.rowcount != 1: raise ValueError("migration preview is stale or already applied")

    def migration_previews(self, organization_id: UUID) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute("""SELECT id,source_file,source_sha256,status,report,created_at,applied_at
                FROM sqlite_migration_previews WHERE organization_id=%s ORDER BY created_at DESC LIMIT 20""", (organization_id,))
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def grant_imported_company_access(self, organization_id: UUID, actor_id: UUID,
                                      company_ids: list[UUID], role_code: str) -> int:
        if role_code not in {"OWNER", "ADMIN"}: raise ValueError("migration access requires OWNER or ADMIN")
        granted=0
        with self._cursor() as cursor:
            cursor.execute("SELECT id FROM roles WHERE organization_id=%s AND code=%s",(organization_id,role_code));row=cursor.fetchone()
            if not row: raise ValueError(f"{role_code} role is not configured")
            role_id=row[0]
            for company_id in company_ids:
                cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(organization_id),))
                cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company_id),))
                cursor.execute("SELECT 1 FROM companies WHERE id=%s AND organization_id=%s",(company_id,organization_id))
                if not cursor.fetchone(): raise ValueError("imported company does not belong to the organization")
                cursor.execute("""INSERT INTO user_company_access(user_id,company_id,role_id) VALUES(%s,%s,%s)
                    ON CONFLICT(user_id,company_id,role_id) DO NOTHING""",(actor_id,company_id,role_id))
                inserted=cursor.rowcount;granted+=inserted
                if inserted:
                    cursor.execute("""INSERT INTO audit_logs(id,organization_id,company_id,actor_id,action,entity_type,entity_id,reason,source_context)
                        VALUES(%s,%s,%s,%s,'MIGRATION_COMPANY_ACCESS_GRANTED','user',%s,'Phase 6C imported company access',
                        jsonb_build_object('role',%s::text))""",(uuid4(),organization_id,company_id,actor_id,str(actor_id),role_code))
        return granted
