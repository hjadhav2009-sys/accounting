from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Callable
from uuid import UUID, uuid4

from .models import TemplateConflict, TemplateImmutable


class TemplateRepository:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @contextmanager
    def _cursor(self):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()
        except Exception:
            connection.rollback(); raise
        finally:
            connection.close()

    @staticmethod
    def _record(cursor, row) -> dict[str, Any] | None:
        if row is None: return None
        names = [column.name if hasattr(column, "name") else column[0] for column in cursor.description]
        return dict(zip(names, row))

    def _records(self, cursor) -> list[dict[str, Any]]:
        return [self._record(cursor, row) for row in cursor.fetchall()]

    def create_family(self, organization_id: UUID, company_id: UUID, user_id: UUID, name: str,
                      document_type: str, supplier: str = "", description: str = "") -> dict[str, Any]:
        family_id = uuid4()
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO document_format_families
                (id,organization_id,company_id,name,supplier,document_type,description,created_by)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *""", (family_id, organization_id, company_id, name, supplier or None,
                                   document_type, description, user_id))
            return self._record(cursor, cursor.fetchone())

    def list_families(self, organization_id: UUID, company_id: UUID, *, document_type: str = "",
                      status: str = "", supplier: str = "", search: str = "") -> list[dict[str, Any]]:
        clauses = ["f.organization_id=%s", "f.company_id=%s"]
        params: list[Any] = [organization_id, company_id]
        if document_type: clauses.append("f.document_type=%s"); params.append(document_type)
        if supplier: clauses.append("coalesce(f.supplier,'') ILIKE %s"); params.append(f"%{supplier}%")
        if search: clauses.append("(f.name ILIKE %s OR coalesce(f.supplier,'') ILIKE %s)"); params.extend([f"%{search}%"] * 2)
        if status: clauses.append("latest.status=%s"); params.append(status)
        with self._cursor() as cursor:
            cursor.execute("""SELECT f.*,latest.id AS latest_version_id,latest.version AS latest_version,
                latest.status AS latest_status,latest.updated_at AS version_updated_at,
                coalesce(health.documents_processed,0) AS documents_processed,
                coalesce(health.verified,0) AS verified,coalesce(health.review,0) AS review,
                coalesce(health.blocked,0) AS blocked,health.last_seen
                FROM document_format_families f
                LEFT JOIN LATERAL (SELECT tv.id,tv.version,tv.status,tv.updated_at FROM template_versions tv
                    WHERE tv.family_id=f.id ORDER BY tv.version DESC LIMIT 1) latest ON true
                LEFT JOIN LATERAL (SELECT count(*) AS documents_processed,
                    count(*) FILTER(WHERE d.status='VERIFIED') AS verified,
                    count(*) FILTER(WHERE d.status='REVIEW') AS review,
                    count(*) FILTER(WHERE d.status='BLOCKED') AS blocked,max(d.created_at) AS last_seen
                    FROM format_fingerprints fp JOIN documents d ON d.id=fp.document_id
                    WHERE fp.family_id=f.id AND d.company_id=%s) health ON true
                WHERE """ + " AND ".join(clauses) + " ORDER BY f.updated_at DESC,f.name", [company_id, *params])
            return self._records(cursor)

    def get_family(self, organization_id: UUID, company_id: UUID, family_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM document_format_families WHERE id=%s AND organization_id=%s AND company_id=%s",
                           (family_id, organization_id, company_id))
            family = self._record(cursor, cursor.fetchone())
            if not family: return None
            cursor.execute("SELECT * FROM template_versions WHERE family_id=%s ORDER BY version DESC", (family_id,))
            family["versions"] = self._records(cursor)
            return family

    def create_version(self, organization_id: UUID, company_id: UUID, family_id: UUID, user_id: UUID,
                       definition: dict[str, Any], *, parent_version_id: UUID | None = None,
                       validation_profile: str = "GENERIC", engine: str = "VISUAL_RULES",
                       change_summary: str = "") -> dict[str, Any]:
        version_id = uuid4()
        with self._cursor() as cursor:
            cursor.execute("SELECT id FROM document_format_families WHERE id=%s AND organization_id=%s AND company_id=%s FOR UPDATE",
                           (family_id, organization_id, company_id))
            if not cursor.fetchone(): raise KeyError("format family not found")
            cursor.execute("SELECT coalesce(max(version),0)+1 FROM template_versions WHERE family_id=%s", (family_id,))
            number = cursor.fetchone()[0]
            cursor.execute("""INSERT INTO template_versions
                (id,family_id,version,status,definition,created_by,parent_version_id,validation_profile,engine,
                 change_summary,updated_by) VALUES(%s,%s,%s,'DRAFT',%s::jsonb,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (version_id, family_id, number, json.dumps(definition), user_id, parent_version_id,
                 validation_profile, engine, change_summary, user_id))
            return self._record(cursor, cursor.fetchone())

    def get_version(self, organization_id: UUID, company_id: UUID, version_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute("""SELECT tv.*,f.organization_id,f.company_id,f.name AS family_name,f.document_type,f.supplier
                FROM template_versions tv JOIN document_format_families f ON f.id=tv.family_id
                WHERE tv.id=%s AND f.organization_id=%s AND f.company_id=%s""", (version_id, organization_id, company_id))
            return self._record(cursor, cursor.fetchone())

    def save_definition(self, organization_id: UUID, company_id: UUID, version_id: UUID, user_id: UUID,
                        definition: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute("""UPDATE template_versions tv SET definition=%s::jsonb,revision=revision+1,
                updated_by=%s,updated_at=now() FROM document_format_families f
                WHERE tv.family_id=f.id AND tv.id=%s AND f.organization_id=%s AND f.company_id=%s
                  AND tv.status IN ('DRAFT','TESTING') AND tv.revision=%s RETURNING tv.*""",
                (json.dumps(definition), user_id, version_id, organization_id, company_id, expected_revision))
            result = self._record(cursor, cursor.fetchone())
            if result: return result
            cursor.execute("""SELECT tv.status,tv.revision FROM template_versions tv JOIN document_format_families f ON f.id=tv.family_id
                WHERE tv.id=%s AND f.organization_id=%s AND f.company_id=%s""", (version_id, organization_id, company_id))
            state = cursor.fetchone()
            if not state: raise KeyError("template version not found")
            if state[0] not in {"DRAFT", "TESTING"}: raise TemplateImmutable("approved and historical versions are immutable; clone a new draft")
            raise TemplateConflict(f"stale revision {expected_revision}; current revision is {state[1]}")

    def set_status(self, organization_id: UUID, company_id: UUID, version_id: UUID, status: str,
                   user_id: UUID, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute("""UPDATE template_versions tv SET status=%s,updated_by=%s,updated_at=now(),
                approved_by=CASE WHEN %s='APPROVED' THEN %s ELSE approved_by END,
                approved_at=CASE WHEN %s='APPROVED' THEN now() ELSE approved_at END,
                approval_evidence=CASE WHEN %s='APPROVED' THEN %s::jsonb ELSE approval_evidence END,
                deprecated_by=CASE WHEN %s='DEPRECATED' THEN %s ELSE deprecated_by END,
                deprecated_at=CASE WHEN %s='DEPRECATED' THEN now() ELSE deprecated_at END
                FROM document_format_families f WHERE tv.family_id=f.id AND tv.id=%s
                AND f.organization_id=%s AND f.company_id=%s RETURNING tv.*""",
                (status, user_id, status, user_id, status, status, json.dumps(evidence or {}),
                 status, user_id, status, version_id, organization_id, company_id))
            result = self._record(cursor, cursor.fetchone())
            if not result: raise KeyError("template version not found")
            return result

    def add_sample(self, organization_id: UUID, company_id: UUID, version_id: UUID, document_id: UUID,
                   user_id: UUID, expected_result: dict[str, Any] | None = None, notes: str = "") -> None:
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO template_samples(template_version_id,document_id,expected_result,notes,added_by)
                SELECT %s,d.id,%s::jsonb,%s,%s FROM documents d JOIN template_versions tv ON tv.id=%s
                JOIN document_format_families f ON f.id=tv.family_id
                WHERE d.id=%s AND d.organization_id=%s AND d.company_id=%s AND f.organization_id=%s AND f.company_id=%s
                ON CONFLICT(template_version_id,document_id) DO UPDATE SET status='ACTIVE',expected_result=excluded.expected_result,
                notes=excluded.notes""", (version_id, json.dumps(expected_result) if expected_result is not None else None,
                    notes, user_id, version_id, document_id, organization_id, company_id, organization_id, company_id))
            if cursor.rowcount != 1: raise KeyError("tenant-scoped document or template not found")

    def remove_sample(self, organization_id: UUID, company_id: UUID, version_id: UUID, document_id: UUID) -> bool:
        with self._cursor() as cursor:
            cursor.execute("""UPDATE template_samples ts SET status='REMOVED' FROM template_versions tv,document_format_families f
                WHERE ts.template_version_id=tv.id AND tv.family_id=f.id AND ts.template_version_id=%s AND ts.document_id=%s
                  AND f.organization_id=%s AND f.company_id=%s""", (version_id, document_id, organization_id, company_id))
            return cursor.rowcount == 1

    def samples(self, organization_id: UUID, company_id: UUID, version_id: UUID) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute("""SELECT ts.*,d.original_filename,d.page_count,d.status AS document_status,
                e.normalized_result,vr.status AS validation_status
                FROM template_samples ts JOIN template_versions tv ON tv.id=ts.template_version_id
                JOIN document_format_families f ON f.id=tv.family_id JOIN documents d ON d.id=ts.document_id
                LEFT JOIN LATERAL (SELECT normalized_result FROM document_extractions WHERE document_id=d.id ORDER BY created_at DESC LIMIT 1) e ON true
                LEFT JOIN LATERAL (SELECT status FROM validation_results WHERE document_id=d.id ORDER BY created_at DESC LIMIT 1) vr ON true
                WHERE ts.template_version_id=%s AND ts.status='ACTIVE' AND f.organization_id=%s AND f.company_id=%s
                  AND d.organization_id=%s AND d.company_id=%s ORDER BY ts.added_at""",
                (version_id, organization_id, company_id, organization_id, company_id))
            records = self._records(cursor)
            if records:
                counts = sorted(int(item.get("page_count") or 0) for item in records)
                median = counts[len(counts) // 2]
                for item in records:
                    count = int(item.get("page_count") or 0)
                    item["possible_outlier"] = len(records) >= 3 and abs(count - median) > max(2, median * 0.5)
            return records

    def create_test_run(self, organization_id: UUID, company_id: UUID, version_id: UUID, user_id: UUID, total: int) -> UUID:
        run_id = uuid4()
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO template_test_runs(id,organization_id,company_id,template_version_id,status,total,created_by)
                VALUES(%s,%s,%s,%s,'QUEUED',%s,%s)""", (run_id, organization_id, company_id, version_id, total, user_id))
        return run_id

    def start_test_run(self, organization_id: UUID, company_id: UUID, run_id: UUID) -> None:
        with self._cursor() as cursor:
            cursor.execute("UPDATE template_test_runs SET status='RUNNING' WHERE id=%s AND organization_id=%s AND company_id=%s",
                           (run_id, organization_id, company_id))

    def add_test_result(self, organization_id: UUID, company_id: UUID, run_id: UUID, document_id: UUID,
                        result: str, extraction: dict[str, Any], validation: dict[str, Any], comparison: dict[str, Any],
                        duration_ms: int = 0, error_code: str | None = None) -> None:
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO template_test_results(id,test_run_id,document_id,result,extraction,validation,comparison,error_code,duration_ms)
                SELECT %s,r.id,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s FROM template_test_runs r
                WHERE r.id=%s AND r.organization_id=%s AND r.company_id=%s""",
                (uuid4(), document_id, result, json.dumps(extraction), json.dumps(validation), json.dumps(comparison),
                 error_code, duration_ms, run_id, organization_id, company_id))
            column = {"VERIFIED": "verified", "REVIEW": "review", "BLOCKED": "blocked", "FAILED": "failed"}[result]
            cursor.execute(f"UPDATE template_test_runs SET processed=processed+1,{column}={column}+1 WHERE id=%s AND organization_id=%s AND company_id=%s",
                           (run_id, organization_id, company_id))

    def finish_test_run(self, organization_id: UUID, company_id: UUID, run_id: UUID) -> None:
        with self._cursor() as cursor:
            cursor.execute("UPDATE template_test_runs SET status='COMPLETED',completed_at=now() WHERE id=%s AND organization_id=%s AND company_id=%s",
                           (run_id, organization_id, company_id))

    def test_run(self, organization_id: UUID, company_id: UUID, run_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM template_test_runs WHERE id=%s AND organization_id=%s AND company_id=%s", (run_id, organization_id, company_id))
            run = self._record(cursor, cursor.fetchone())
            if not run: return None
            cursor.execute("""SELECT tr.*,d.original_filename FROM template_test_results tr JOIN documents d ON d.id=tr.document_id
                WHERE tr.test_run_id=%s AND d.organization_id=%s AND d.company_id=%s ORDER BY d.original_filename""",
                (run_id, organization_id, company_id))
            run["results"] = self._records(cursor)
            return run

    def latest_test_run(self, organization_id: UUID, company_id: UUID, version_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute("""SELECT id FROM template_test_runs WHERE organization_id=%s AND company_id=%s
                AND template_version_id=%s AND status='COMPLETED' ORDER BY completed_at DESC LIMIT 1""",
                (organization_id, company_id, version_id))
            row = cursor.fetchone()
        return self.test_run(organization_id, company_id, row[0]) if row else None

    def activity(self, organization_id: UUID, company_id: UUID, family_id: UUID) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM template_activity WHERE organization_id=%s AND company_id=%s AND family_id=%s ORDER BY created_at DESC",
                           (organization_id, company_id, family_id))
            return self._records(cursor)

    def record_activity(self, organization_id: UUID, company_id: UUID, family_id: UUID, version_id: UUID | None,
                        user_id: UUID, event_type: str, detail: dict[str, Any] | None = None) -> None:
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO template_activity(id,organization_id,company_id,family_id,template_version_id,actor_id,event_type,detail)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""", (uuid4(), organization_id, company_id, family_id,
                    version_id, user_id, event_type, json.dumps(detail or {})))

    def add_comment(self, organization_id: UUID, company_id: UUID, family_id: UUID, version_id: UUID | None,
                    document_id: UUID | None, user_id: UUID, note: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO template_comments(id,organization_id,company_id,family_id,template_version_id,document_id,author_id,note)
                SELECT %s,%s,%s,f.id,%s,%s,%s,%s FROM document_format_families f
                WHERE f.id=%s AND f.organization_id=%s AND f.company_id=%s RETURNING *""",
                (uuid4(), organization_id, company_id, version_id, document_id, user_id, note,
                 family_id, organization_id, company_id))
            result = self._record(cursor, cursor.fetchone())
            if not result: raise KeyError("format family not found")
            return result

    def version_diff(self, organization_id: UUID, company_id: UUID, old_id: UUID, new_id: UUID) -> dict[str, Any]:
        old, new = self.get_version(organization_id, company_id, old_id), self.get_version(organization_id, company_id, new_id)
        if not old or not new or old["family_id"] != new["family_id"]: raise KeyError("comparable versions not found")
        old_objects = {item["id"]: item for item in old["definition"].get("objects", [])}
        new_objects = {item["id"]: item for item in new["definition"].get("objects", [])}
        return {"old_version": old["version"], "new_version": new["version"],
                "added": [new_objects[key] for key in new_objects.keys() - old_objects.keys()],
                "removed": [old_objects[key] for key in old_objects.keys() - new_objects.keys()],
                "changed": [{"id": key, "before": old_objects[key], "after": new_objects[key]}
                            for key in old_objects.keys() & new_objects.keys() if old_objects[key] != new_objects[key]],
                "validation_changed": old["validation_profile"] != new["validation_profile"]}

    def routing_fingerprints(self, organization_id: UUID, company_id: UUID, document_id: UUID) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with self._cursor() as cursor:
            cursor.execute("""SELECT fp.signature,fp.features FROM format_fingerprints fp JOIN documents d ON d.id=fp.document_id
                WHERE fp.document_id=%s AND fp.organization_id=%s AND d.company_id=%s""", (document_id, organization_id, company_id))
            current = self._record(cursor, cursor.fetchone())
            if not current: raise KeyError("tenant-scoped document fingerprint not found")
            cursor.execute("""SELECT DISTINCT ON(fp.family_id) fp.family_id,f.name,fp.signature,fp.features,tv.id AS version_id
                FROM format_fingerprints fp JOIN documents d ON d.id=fp.document_id
                JOIN document_format_families f ON f.id=fp.family_id
                LEFT JOIN LATERAL (SELECT id FROM template_versions WHERE family_id=f.id AND status='APPROVED' ORDER BY version DESC LIMIT 1) tv ON true
                WHERE fp.organization_id=%s AND d.company_id=%s AND fp.family_id IS NOT NULL AND fp.document_id<>%s
                ORDER BY fp.family_id,fp.created_at DESC""", (organization_id, company_id, document_id))
            return current, self._records(cursor)
