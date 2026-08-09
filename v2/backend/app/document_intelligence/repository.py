from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date,datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from uuid import UUID, uuid4

from .models import DocumentRecord, DocumentStatus, to_jsonable


class DocumentRepository:
    """PostgreSQL metadata repository with mandatory organization/company scoping."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @property
    def connection_factory(self)->Callable[[],Any]:
        return self._connect

    @contextmanager
    def _cursor(self):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _records(cursor) -> list[dict[str, Any]]:
        names = [column.name if hasattr(column, "name") else column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def exact_duplicate(self, organization_id: UUID, company_id: UUID, sha256: str) -> UUID | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT document_id FROM document_hashes WHERE organization_id=%s AND company_id=%s AND sha256=%s",
                (organization_id, company_id, sha256),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def record_duplicate_attempt(self, organization_id:UUID, company_id:UUID, existing_document_id:UUID,
                                 attempted_by:UUID, sha256:str, original_filename:str)->None:
        """Persist audit evidence only; a duplicate source object is never stored."""
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO duplicate_upload_attempts(id,organization_id,company_id,
                existing_document_id,attempted_by,sha256,original_filename)
                VALUES(%s,%s,%s,%s,%s,%s,%s)""",(uuid4(),organization_id,company_id,
                existing_document_id,attempted_by,sha256,original_filename[:500]))

    def create(self, record: DocumentRecord) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO documents(
                    id,organization_id,company_id,filename,original_filename,safe_filename,mime_type,byte_size,
                    storage_key,status,created_by,created_at,page_count,duplicate_of_document_id,batch_id
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (record.document_id, record.organization_id, record.company_id, record.safe_filename,
                 record.original_filename, record.safe_filename, record.mime_type, record.size, record.storage_key,
                 record.status.value, record.created_by, record.created_at, record.page_count,
                 record.duplicate_of_document_id, record.batch_id),
            )
            cursor.execute(
                "INSERT INTO document_hashes(document_id,organization_id,company_id,sha256) VALUES(%s,%s,%s,%s)",
                (record.document_id, record.organization_id, record.company_id, record.sha256),
            )

    def transition(self, organization_id: UUID, company_id: UUID, document_id: UUID,
                   expected: DocumentStatus, target: DocumentStatus, **values: Any) -> None:
        allowed = {"page_count", "document_type", "supplier", "invoice_number", "invoice_date", "total_amount",
                   "extraction_method", "quality_status", "error_code", "duplicate_of_document_id"}
        updates = {key: value.value if hasattr(value, "value") else value for key, value in values.items() if key in allowed}
        assignments = ["status=%s", "updated_at=now()"] + [f"{key}=%s" for key in updates]
        parameters = [target.value, *updates.values(), organization_id, company_id, document_id, expected.value]
        with self._cursor() as cursor:
            cursor.execute(
                f"UPDATE documents SET {','.join(assignments)} WHERE organization_id=%s AND company_id=%s AND id=%s AND status=%s",
                parameters,
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"document transition conflict: {expected.value} -> {target.value}")
            invoice_date=updates.get("invoice_date")
            if invoice_date:
                if isinstance(invoice_date,str):invoice_date=date.fromisoformat(invoice_date)
                start_year=invoice_date.year if invoice_date.month>=4 else invoice_date.year-1
                starts=date(start_year,4,1);ends=date(start_year+1,3,31);label=f"{start_year}-{str(start_year+1)[-2:]}";financial_year_id=uuid4()
                cursor.execute("""INSERT INTO financial_years(id,organization_id,company_id,label,starts_on,ends_on)
                    VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(company_id,label) DO UPDATE SET label=excluded.label RETURNING id""",
                    (financial_year_id,organization_id,company_id,label,starts,ends));financial_year_id=cursor.fetchone()[0]
                cursor.execute("UPDATE documents SET financial_year_id=%s WHERE id=%s AND organization_id=%s AND company_id=%s",
                    (financial_year_id,document_id,organization_id,company_id))

    def list(self, organization_id: UUID, company_id: UUID, status: str | None = None,
             search: str = "", limit: int = 100, offset: int = 0, *,
             date_from: str | None = None, date_to: str | None = None,
             document_type: str = "", supplier: str = "", format_family_id: UUID | None = None,
             validation_status: str = "", review_status: str = "", duplicate_status: str = "",
             uploaded_by: UUID | None = None, financial_year_id:UUID|None=None) -> list[dict[str, Any]]:
        clauses = ["d.organization_id=%s", "d.company_id=%s"]
        parameters: list[Any] = [organization_id, company_id]
        if status:
            clauses.append("d.status=%s")
            parameters.append(status)
        if financial_year_id:
            clauses.append("d.financial_year_id=%s");parameters.append(financial_year_id)
        if search:
            clauses.append("(d.original_filename ILIKE %s OR d.supplier ILIKE %s OR d.invoice_number ILIKE %s)")
            parameters.extend([f"%{search}%"] * 3)
        if date_from:
            clauses.append("d.created_at::date >= %s::date")
            parameters.append(date_from)
        if date_to:
            clauses.append("d.created_at::date <= %s::date")
            parameters.append(date_to)
        if document_type:
            clauses.append("d.document_type=%s")
            parameters.append(document_type)
        if supplier:
            clauses.append("d.supplier ILIKE %s")
            parameters.append(f"%{supplier}%")
        if format_family_id:
            clauses.append("fp.family_id=%s")
            parameters.append(format_family_id)
        if validation_status:
            clauses.append("EXISTS(SELECT 1 FROM validation_results vr WHERE vr.document_id=d.id AND vr.status=%s)")
            parameters.append(validation_status)
        if review_status:
            clauses.append("EXISTS(SELECT 1 FROM review_tasks rt WHERE rt.document_id=d.id AND rt.status=%s)")
            parameters.append(review_status)
        if duplicate_status == "DUPLICATE":
            clauses.append("(d.duplicate_of_document_id IS NOT NULL OR EXISTS(SELECT 1 FROM review_tasks rt WHERE rt.document_id=d.id AND rt.reason_code='POSSIBLE_DUPLICATE'))")
        elif duplicate_status == "UNIQUE":
            clauses.append("d.duplicate_of_document_id IS NULL AND NOT EXISTS(SELECT 1 FROM review_tasks rt WHERE rt.document_id=d.id AND rt.reason_code='POSSIBLE_DUPLICATE')")
        if uploaded_by:
            clauses.append("d.created_by=%s")
            parameters.append(uploaded_by)
        parameters.extend([min(max(limit, 1), 250), max(offset, 0)])
        with self._cursor() as cursor:
            cursor.execute(
                f"""SELECT d.id AS document_id,d.company_id,d.original_filename,d.safe_filename,d.status,
                    d.document_type,d.supplier,d.invoice_number,d.invoice_date,d.total_amount,d.page_count,
                    d.extraction_method,d.quality_status,d.error_code,d.duplicate_of_document_id,d.created_at,
                    f.id AS format_family_id,f.name AS format_family,
                    (SELECT vr.status FROM validation_results vr WHERE vr.document_id=d.id ORDER BY vr.created_at DESC LIMIT 1) AS validation_status,
                    (SELECT rt.status FROM review_tasks rt WHERE rt.document_id=d.id ORDER BY rt.created_at DESC LIMIT 1) AS review_status
                    FROM documents d LEFT JOIN format_fingerprints fp ON fp.document_id=d.id
                    LEFT JOIN document_format_families f ON f.id=fp.family_id
                    WHERE {' AND '.join(clauses)} ORDER BY d.created_at DESC LIMIT %s OFFSET %s""",
                parameters,
            )
            return self._records(cursor)

    def get(self, organization_id: UUID, company_id: UUID, document_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT d.*,h.sha256 FROM documents d JOIN document_hashes h ON h.document_id=d.id
                   WHERE d.organization_id=%s AND d.company_id=%s AND d.id=%s""",
                (organization_id, company_id, document_id),
            )
            records = self._records(cursor)
            return records[0] if records else None

    def save_pages(self, document_id: UUID, pages: tuple[Any, ...]) -> None:
        with self._cursor() as cursor:
            for page in pages:
                cursor.execute(
                    """INSERT INTO document_pages(id,document_id,page_number,width,height)
                       VALUES(%s,%s,%s,%s,%s) ON CONFLICT(document_id,page_number)
                       DO UPDATE SET width=excluded.width,height=excluded.height""",
                    (uuid4(), document_id, page.page_number, page.width, page.height),
                )

    def save_fingerprint(self, organization_id: UUID, document_id: UUID, fingerprint: Any) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO format_fingerprints(id,organization_id,document_id,signature,features)
                   VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT(organization_id,document_id)
                   DO UPDATE SET signature=excluded.signature,features=excluded.features""",
                (uuid4(), organization_id, document_id, fingerprint.signature,
                 json.dumps(to_jsonable(fingerprint))),
            )

    def resolve_known_format(self, record: DocumentRecord, route: str) -> tuple[UUID, UUID]:
        family_name = route.replace(":", " / ").replace("_", " ").title()
        with self._cursor() as cursor:
            cursor.execute("""SELECT id FROM document_format_families
                WHERE organization_id=%s AND company_id=%s AND name=%s""",
                (record.organization_id, record.company_id, family_name))
            row = cursor.fetchone()
            family_id = row[0] if row else uuid4()
            if not row:
                cursor.execute("""INSERT INTO document_format_families(id,organization_id,company_id,name,supplier,document_type,created_by)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)""", (family_id, record.organization_id, record.company_id,
                    family_name, record.supplier or None, record.document_type or "Accounting Document", record.created_by))
            cursor.execute("""SELECT id FROM template_versions WHERE family_id=%s AND status='APPROVED'
                ORDER BY version DESC LIMIT 1""", (family_id,))
            version = cursor.fetchone()
            template_id = version[0] if version else uuid4()
            if not version:
                cursor.execute("""INSERT INTO template_versions(id,family_id,version,status,definition,created_by,approved_by,approved_at,
                    engine,validation_profile,updated_by)
                    VALUES(%s,%s,1,'APPROVED',%s::jsonb,%s,%s,now(),'LEGACY_PARSER','GENERIC',%s)""",
                    (template_id, family_id, json.dumps({"route": route, "adapter": "v2-native-template"}),
                     record.created_by, record.created_by, record.created_by))
            cursor.execute("UPDATE format_fingerprints SET family_id=%s WHERE organization_id=%s AND document_id=%s",
                           (family_id, record.organization_id, record.document_id))
        return family_id, template_id

    def business_duplicate(self, organization_id: UUID, company_id: UUID, signature: str) -> UUID | None:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT document_id FROM accounting_duplicate_signatures
                   WHERE organization_id=%s AND company_id=%s AND signature=%s""",
                (organization_id, company_id, signature),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def save_business_signature(self, record: DocumentRecord, signature: str) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO accounting_duplicate_signatures(document_id,organization_id,company_id,document_type,
                   supplier_token,invoice_number_token,invoice_date,total_amount,signature)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (record.document_id, record.organization_id, record.company_id, record.document_type,
                 record.supplier.casefold(), record.invoice_number.casefold(), record.invoice_date,
                 record.total_amount, signature),
            )

    def save_metric(self, record: DocumentRecord, stage: str, duration_ms: int, outcome: str, *,
                    ocr_pages: int = 0, format_route: str = "", validation_status: str = "",
                    job_id: UUID | None = None) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO document_processing_metrics(id,organization_id,company_id,document_id,stage,duration_ms,
                   page_count,method,outcome,ocr_pages,format_route,validation_status,batch_id,job_id)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (uuid4(), record.organization_id, record.company_id, record.document_id, stage,
                 max(0, duration_ms), record.page_count,
                 record.extraction_method.value if record.extraction_method else None, outcome,
                 max(0, ocr_pages), format_route, validation_status, record.batch_id, job_id),
            )

    def save_extraction(self, record: DocumentRecord, result: Any, extractor_version: str) -> UUID:
        extraction_id = uuid4()
        quality = result.quality.status.value if result.quality else "DEGRADED"
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO document_extractions(id,organization_id,company_id,document_id,method,quality_status,
                   normalized_result,extractor_version) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                (extraction_id, record.organization_id, record.company_id, record.document_id, result.method.value,
                 quality, json.dumps(to_jsonable(result)), extractor_version),
            )
            for field in result.fields:
                cursor.execute(
                    """INSERT INTO document_detected_fields(id,extraction_id,field_name,value_json,confidence,
                       source_reference,original_token,normalization) VALUES(%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s,%s)""",
                    (uuid4(), extraction_id, field.name, json.dumps(to_jsonable(field.value)), field.confidence,
                     json.dumps(to_jsonable(field.source)), field.original_token, field.normalization),
                )
        return extraction_id

    def extraction(self, organization_id: UUID, company_id: UUID, document_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT e.id,e.method,e.quality_status,e.normalized_result,e.extractor_version,e.created_at
                   FROM document_extractions e WHERE e.organization_id=%s AND e.company_id=%s AND e.document_id=%s
                   ORDER BY e.created_at DESC LIMIT 1""", (organization_id, company_id, document_id),
            )
            records = self._records(cursor)
            return records[0] if records else None

    def save_validation(self, record: DocumentRecord, extraction_id: UUID | None, report: Any) -> UUID:
        validation_id = uuid4()
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO validation_results(id,organization_id,company_id,document_id,extraction_result_id,status,
                   calculations,validator_version) VALUES(%s,%s,%s,%s,NULL,%s,%s::jsonb,'phase3-deterministic-v1')""",
                (validation_id, record.organization_id, record.company_id, record.document_id,
                 report.status, json.dumps(to_jsonable(report.calculations))),
            )
            for finding in report.findings:
                cursor.execute(
                    """INSERT INTO validation_issues(id,validation_result_id,code,severity,message,source_reference)
                       VALUES(%s,%s,%s,%s,%s,%s::jsonb)""",
                    (uuid4(), validation_id, (finding.error_code.value if finding.error_code else finding.validator)[:80],
                     finding.severity.value, finding.message, json.dumps(to_jsonable(finding.source_references))),
                )
        return validation_id

    def validation(self, organization_id: UUID, company_id: UUID, document_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT id,status,calculations,validator_version,created_at FROM validation_results
                   WHERE organization_id=%s AND company_id=%s AND document_id=%s ORDER BY created_at DESC LIMIT 1""",
                (organization_id, company_id, document_id),
            )
            records = self._records(cursor)
            if not records:
                return None
            result = records[0]
            cursor.execute("SELECT code,severity,message,source_reference FROM validation_issues WHERE validation_result_id=%s ORDER BY severity,code", (result["id"],))
            result["issues"] = self._records(cursor)
            return result

    def record_export(self, organization_id:UUID,company_id:UUID,document_id:UUID,actor_id:UUID,
                      export_type:str,filename:str,file_sha256:str,validation_status:str,
                      extraction_result_id:UUID|None,evidence:dict[str,Any])->UUID:
        export_id=uuid4()
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO document_exports(id,organization_id,company_id,document_id,export_type,
                filename,file_sha256,validation_status,extraction_result_id,evidence,created_by)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                (export_id,organization_id,company_id,document_id,export_type,filename,file_sha256,
                 validation_status,extraction_result_id,json.dumps(to_jsonable(evidence)),actor_id))
            cursor.execute("""INSERT INTO audit_logs(id,organization_id,company_id,actor_id,action,entity_type,
                entity_id,new_reference,document_id,reason,source_context)
                VALUES(%s,%s,%s,%s,%s,'document_export',%s,%s,%s,'deterministic verified export',%s::jsonb)""",
                (uuid4(),organization_id,company_id,actor_id,f"{export_type}_EXPORTED",str(export_id),file_sha256,
                 document_id,json.dumps({"filename":filename,"validation_status":validation_status})))
        return export_id

    def exports(self,organization_id:UUID,company_id:UUID,document_id:UUID|None=None)->list[dict[str,Any]]:
        with self._cursor() as cursor:
            cursor.execute("""SELECT id,document_id,export_type,filename,file_sha256,validation_status,evidence,
                created_by,created_at FROM document_exports WHERE organization_id=%s AND company_id=%s
                AND (%s IS NULL OR document_id=%s) ORDER BY created_at DESC""",
                (organization_id,company_id,document_id,document_id))
            return self._records(cursor)

    def create_review(self, record: DocumentRecord, reason: str, severity: str = "REVIEW", detail: dict[str, Any] | None = None) -> UUID:
        review_id = uuid4()
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO review_tasks(id,organization_id,company_id,document_id,status,reason_code,severity,detail)
                   VALUES(%s,%s,%s,%s,'OPEN',%s,%s,%s::jsonb)""",
                (review_id, record.organization_id, record.company_id, record.document_id, reason, severity,
                 json.dumps(to_jsonable(detail or {}))),
            )
        return review_id

    def reviews(self, organization_id: UUID, company_id: UUID, status: str = "OPEN", *,
                reason: str = "", severity: str = "", assigned_to: UUID | None = None,
                date_from: str | None = None, date_to: str | None = None) -> list[dict[str, Any]]:
        clauses = ["r.organization_id=%s", "r.company_id=%s"]
        parameters: list[Any] = [organization_id, company_id]
        if status:
            clauses.append("r.status=%s"); parameters.append(status)
        if reason:
            clauses.append("r.reason_code=%s"); parameters.append(reason)
        if severity:
            clauses.append("r.severity=%s"); parameters.append(severity)
        if assigned_to:
            clauses.append("r.assigned_to=%s"); parameters.append(assigned_to)
        if date_from:
            clauses.append("r.created_at::date >= %s::date"); parameters.append(date_from)
        if date_to:
            clauses.append("r.created_at::date <= %s::date"); parameters.append(date_to)
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT r.id AS review_id,r.document_id,r.status,r.reason_code,r.severity,r.detail,r.created_at,
                   d.original_filename,d.supplier,d.invoice_number FROM review_tasks r JOIN documents d ON d.id=r.document_id
                   WHERE """ + " AND ".join(clauses) + " ORDER BY r.created_at",
                parameters,
            )
            return self._records(cursor)

    def resolve_review(self, organization_id: UUID, company_id: UUID, review_id: UUID,
                       user_id: UUID, resolution_note: str, status: str = "RESOLVED") -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                """UPDATE review_tasks SET status=%s,resolution_note=%s,resolved_by=%s,resolved_at=now()
                   WHERE id=%s AND organization_id=%s AND company_id=%s AND status IN ('OPEN','IN_PROGRESS')""",
                (status, resolution_note[:2000], user_id, review_id, organization_id, company_id),
            )
            return cursor.rowcount == 1

    def dashboard(self, organization_id: UUID, company_id: UUID) -> dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT status,count(*) AS count FROM documents WHERE organization_id=%s AND company_id=%s
                   GROUP BY status ORDER BY status""", (organization_id, company_id),
            )
            statuses = {row[0]: row[1] for row in cursor.fetchall()}
            cursor.execute(
                """SELECT coalesce(avg(duration_ms),0)::numeric(18,2),count(*) FROM document_processing_metrics
                   WHERE organization_id=%s AND company_id=%s""", (organization_id, company_id),
            )
            average_duration_ms, metric_count = cursor.fetchone()
        return {"statuses": statuses, "processed": sum(statuses.values()),
                "average_duration_ms": average_duration_ms, "metric_count": metric_count,
                "generated_at": datetime.now(timezone.utc)}

    def create_batch(self, organization_id: UUID, company_id: UUID, created_by: UUID, total: int) -> UUID:
        batch_id = uuid4()
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO document_batches(id,organization_id,company_id,created_by,total,queued,status)
                   VALUES(%s,%s,%s,%s,%s,%s,'QUEUED')""",
                (batch_id, organization_id, company_id, created_by, total, total),
            )
        return batch_id

    def mark_interrupted_batches(self) -> int:
        with self._cursor() as cursor:
            cursor.execute("""UPDATE document_batches SET status='INTERRUPTED',running=0,updated_at=now(),
                restart_note='In-process execution was interrupted; unprocessed files require explicit resubmission.'
                WHERE status IN ('QUEUED','RUNNING')""")
            return cursor.rowcount

    def start_batch(self, organization_id: UUID, company_id: UUID, batch_id: UUID) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """UPDATE document_batches SET status='RUNNING',updated_at=now()
                   WHERE id=%s AND organization_id=%s AND company_id=%s AND status='QUEUED'""",
                (batch_id, organization_id, company_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("batch cannot start")

    def batch_document_started(self, organization_id: UUID, company_id: UUID, batch_id: UUID) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """UPDATE document_batches SET queued=greatest(0,queued-1),running=running+1,updated_at=now()
                   WHERE id=%s AND organization_id=%s AND company_id=%s""",
                (batch_id, organization_id, company_id),
            )

    def batch_document_finished(self, organization_id: UUID, company_id: UUID, batch_id: UUID, outcome: str) -> None:
        column = {"VERIFIED": "verified", "REVIEW": "review", "BLOCKED": "blocked",
                  "DUPLICATE": "duplicate", "FAILED": "failed"}.get(outcome, "failed")
        with self._cursor() as cursor:
            cursor.execute(
                f"""UPDATE document_batches SET running=greatest(0,running-1),processed=processed+1,
                    {column}={column}+1,updated_at=now() WHERE id=%s AND organization_id=%s AND company_id=%s""",
                (batch_id, organization_id, company_id),
            )

    def finish_batch(self, organization_id: UUID, company_id: UUID, batch_id: UUID) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """UPDATE document_batches SET status=CASE WHEN failed>0 THEN 'COMPLETED_WITH_ERRORS' ELSE 'COMPLETED' END,
                   queued=0,running=0,completed_at=now(),updated_at=now()
                   WHERE id=%s AND organization_id=%s AND company_id=%s""",
                (batch_id, organization_id, company_id),
            )

    def get_batch(self, organization_id: UUID, company_id: UUID, batch_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT id AS batch_id,status,total,processed,queued,running,verified,review,blocked,duplicate,failed,
                   created_at,updated_at,completed_at,restart_note,
                   CASE WHEN total=0 THEN 100 ELSE round(processed::numeric*100/total,2) END AS progress
                   FROM document_batches WHERE id=%s AND organization_id=%s AND company_id=%s""",
                (batch_id, organization_id, company_id),
            )
            records = self._records(cursor)
            return records[0] if records else None

    def batch_documents(self, organization_id: UUID, company_id: UUID, batch_id: UUID) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT id AS document_id,original_filename,status,document_type,supplier,invoice_number,
                   total_amount,error_code,created_at FROM documents
                   WHERE organization_id=%s AND company_id=%s AND batch_id=%s ORDER BY created_at,id""",
                (organization_id, company_id, batch_id),
            )
            return self._records(cursor)

    def batch_accounting_summary(self, organization_id: UUID, company_id: UUID, batch_id: UUID) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT d.document_type,e.normalized_result FROM documents d
                   JOIN LATERAL (SELECT normalized_result FROM document_extractions x WHERE x.document_id=d.id
                   ORDER BY x.created_at DESC LIMIT 1) e ON true
                   WHERE d.organization_id=%s AND d.company_id=%s AND d.batch_id=%s
                     AND d.status IN ('VERIFIED','REVIEW','BLOCKED')""",
                (organization_id, company_id, batch_id),
            )
            rows = cursor.fetchall()
        for document_type, payload in rows:
            currency = str(payload.get("currency") or "INR")
            key = (document_type or "Unclassified", currency)
            group = groups.setdefault(key, {"document_category": key[0], "currency": currency,
                "document_count": 0, "taxable": Decimal("0"), "CGST": Decimal("0"),
                "SGST": Decimal("0"), "IGST": Decimal("0"), "total_gst": Decimal("0"), "invoice_total": Decimal("0")})
            group["document_count"] += 1
            from .validation import taxable_base_total
            buckets=payload.get("tax_buckets") or []
            for bucket in payload.get("tax_buckets") or []:
                taxable = Decimal(str(bucket.get("taxable") or 0)); tax = Decimal(str(bucket.get("tax") or 0))
                tax_type = str(bucket.get("tax_type") or "").upper()
                if tax_type in {"CGST", "SGST", "IGST"}: group[tax_type] += tax
                group["total_gst"] += tax
            group["taxable"] += taxable_base_total(buckets)
            group["invoice_total"] += Decimal(str((payload.get("totals") or {}).get("invoice_total") or 0))
        return list(groups.values())

    def unified_report(self, organization_id: UUID, company_id: UUID,
                       date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
        def dated(column: str) -> tuple[str, list[Any]]:
            clauses, values = [], []
            if date_from: clauses.append(f"{column} >= %s::date"); values.append(date_from)
            if date_to: clauses.append(f"{column} <= %s::date"); values.append(date_to)
            return ((" AND " + " AND ".join(clauses)) if clauses else "", values)
        date_clauses = []
        parameters: list[Any] = [organization_id, company_id]
        if date_from: date_clauses.append("created_at::date >= %s::date"); parameters.append(date_from)
        if date_to: date_clauses.append("created_at::date <= %s::date"); parameters.append(date_to)
        suffix = (" AND " + " AND ".join(date_clauses)) if date_clauses else ""
        with self._cursor() as cursor:
            cursor.execute("SELECT status,count(*) FROM documents WHERE organization_id=%s AND company_id=%s" + suffix + " GROUP BY status", parameters)
            document_statuses = {row[0]: row[1] for row in cursor.fetchall()}
            invoice_suffix, invoice_dates = dated("invoice_date")
            cursor.execute("SELECT count(*),coalesce(sum(total),0) FROM invoices WHERE organization_id=%s AND company_id=%s" + invoice_suffix,
                           [organization_id, company_id, *invoice_dates])
            invoice_count, invoice_total = cursor.fetchone()
            cursor.execute("""SELECT coalesce(sum(taxable),0) FROM (
                SELECT DISTINCT b.invoice_id,coalesce(nullif(b.base_partition_id,''),
                    b.rate::text||'|'||b.hsn_sac||'|'||b.taxable::text) partition_id,b.taxable FROM invoice_tax_buckets b
                JOIN invoices i ON i.id=b.invoice_id WHERE i.organization_id=%s AND i.company_id=%s""" + invoice_suffix +
                ") partitions", [organization_id, company_id, *invoice_dates])
            taxable = cursor.fetchone()[0]
            cursor.execute("""SELECT coalesce(sum(CASE WHEN b.tax_type='CGST' THEN b.tax ELSE 0 END),0),
                coalesce(sum(CASE WHEN b.tax_type='SGST' THEN b.tax ELSE 0 END),0),
                coalesce(sum(CASE WHEN b.tax_type='IGST' THEN b.tax ELSE 0 END),0)
                FROM invoices i LEFT JOIN invoice_tax_buckets b ON b.invoice_id=i.id
                WHERE i.organization_id=%s AND i.company_id=%s""" + invoice_suffix,
                [organization_id, company_id, *invoice_dates])
            cgst, sgst, igst = cursor.fetchone()
            cursor.execute("""SELECT count(DISTINCT md.id),coalesce(sum(ml.taxable),0),
                coalesce(sum(ml.cgst+ml.sgst+ml.igst),0),
                count(*) FILTER (WHERE ml.mapping_status<>'MAPPED')
                FROM marketplace_documents md LEFT JOIN marketplace_lines ml ON ml.marketplace_document_id=md.id
                WHERE md.organization_id=%s AND md.company_id=%s""" + dated("md.invoice_date")[0],
                [organization_id, company_id, *dated("md.invoice_date")[1]])
            marketplace_count, marketplace_taxable, marketplace_gst, marketplace_unmapped = cursor.fetchone()
            cursor.execute("""SELECT count(*),coalesce(sum(credit),0),coalesce(sum(debit),0),
                count(*) FILTER (WHERE mapping_status<>'MAPPED') FROM bank_transactions
                WHERE organization_id=%s AND company_id=%s""" + dated("transaction_date")[0],
                [organization_id, company_id, *dated("transaction_date")[1]])
            bank_count, credits, debits, bank_unmapped = cursor.fetchone()
            cursor.execute("""SELECT count(*),coalesce(avg(duration_ms),0)::numeric(18,2),
                count(*) FILTER (WHERE method='LOCAL_OCR') FROM document_processing_metrics
                WHERE organization_id=%s AND company_id=%s""" + dated("created_at::date")[0],
                [organization_id, company_id, *dated("created_at::date")[1]])
            metric_count, average_duration, ocr_metrics = cursor.fetchone()
            cursor.execute("""SELECT count(*) FROM review_tasks WHERE organization_id=%s AND company_id=%s
                AND reason_code='BANK_RECONCILIATION_FAILED' AND status='OPEN'""", (organization_id, company_id))
            bank_failures = cursor.fetchone()[0]
            cursor.execute("""SELECT u.id,u.display_name,u.email,count(DISTINCT d.id) documents,
                count(DISTINCT r.id) FILTER(WHERE r.resolved_by=u.id) reviews
                FROM users u LEFT JOIN documents d ON d.created_by=u.id AND d.company_id=%s
                LEFT JOIN review_tasks r ON r.resolved_by=u.id AND r.company_id=%s
                WHERE u.organization_id=%s GROUP BY u.id ORDER BY documents DESC,reviews DESC,u.display_name""",
                (company_id,company_id,organization_id));user_activity=self._records(cursor)
            cursor.execute("""SELECT count(*) FILTER(WHERE provider='LOCAL'),
                count(*) FILTER(WHERE provider='CLOUDFLARE_WORKERS_AI'),count(*)
                FROM ai_audit_events WHERE organization_id=%s AND company_id=%s""",(organization_id,company_id));local_ai,cloud_ai,ai_events=cursor.fetchone()
            cursor.execute("""SELECT coalesce(sum(used_units),0),coalesce(sum(reserved_units),0) FROM ai_daily_usage
                WHERE organization_id=%s AND company_id=%s""",(organization_id,company_id));used_units,reserved_units=cursor.fetchone()
            cursor.execute("""SELECT export_type,count(*),max(created_at) FROM document_exports
                WHERE organization_id=%s AND company_id=%s GROUP BY export_type ORDER BY export_type""",(organization_id,company_id));export_rows=cursor.fetchall()
        processed = sum(document_statuses.values())
        verified = document_statuses.get("VERIFIED", 0)
        review = document_statuses.get("REVIEW", 0)
        return {"documents": {"total": processed, "statuses": document_statuses,
                "unknown_formats": self._count_reviews(organization_id, company_id, "UNKNOWN_FORMAT")},
            "invoices": {"count": invoice_count, "taxable": taxable, "CGST": cgst, "SGST": sgst,
                "IGST": igst, "GST_total": cgst + sgst + igst, "invoice_total": invoice_total},
            "marketplace": {"document_count": marketplace_count, "taxable": marketplace_taxable,
                "GST": marketplace_gst, "unmapped": marketplace_unmapped},
            "bank": {"transactions": bank_count, "credits": credits, "debits": debits,
                "unmapped": bank_unmapped, "reconciliation_failures": bank_failures},
            "processing": {"success_rate": Decimal(verified) * 100 / Decimal(processed) if processed else Decimal("0"),
                "review_rate": Decimal(review) * 100 / Decimal(processed) if processed else Decimal("0"),
                "OCR_usage": ocr_metrics, "average_duration_ms": average_duration, "metric_count": metric_count},
            "users":{"activity":user_activity},
            "ai":{"local_jobs":local_ai,"cloud_jobs":cloud_ai,"audit_events":ai_events,"used_units":used_units,
                "reserved_units":reserved_units,"cloud_avoided":max(0,metric_count-cloud_ai)},
            "exports":{"types":{row[0]:{"count":row[1],"last_exported_at":row[2]} for row in export_rows}},
            "generated_at": datetime.now(timezone.utc)}

    def financial_years(self,organization_id:UUID,company_id:UUID)->list[dict[str,Any]]:
        with self._cursor() as cursor:
            cursor.execute("SELECT id,label,starts_on,ends_on,active FROM financial_years WHERE organization_id=%s AND company_id=%s ORDER BY starts_on DESC",(organization_id,company_id))
            return self._records(cursor)

    def financial_year(self,organization_id:UUID,company_id:UUID,financial_year_id:UUID)->dict[str,Any]|None:
        with self._cursor() as cursor:
            cursor.execute("SELECT id,label,starts_on,ends_on,active FROM financial_years WHERE id=%s AND organization_id=%s AND company_id=%s",(financial_year_id,organization_id,company_id));records=self._records(cursor)
            return records[0] if records else None

    def _count_reviews(self, organization_id: UUID, company_id: UUID, reason: str) -> int:
        with self._cursor() as cursor:
            cursor.execute("SELECT count(*) FROM review_tasks WHERE organization_id=%s AND company_id=%s AND reason_code=%s",
                           (organization_id, company_id, reason))
            return cursor.fetchone()[0]

    def format_health(self, organization_id: UUID, company_id: UUID) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute("""SELECT coalesce(f.id::text,'unknown') AS family_id,coalesce(f.name,'Unknown formats') AS family,
                count(DISTINCT d.id) AS documents_seen,
                count(DISTINCT tv.id) FILTER (WHERE tv.status='APPROVED') AS approved_versions,
                max(tv.version) AS latest_version,
                count(DISTINCT d.id) FILTER (WHERE d.status='VERIFIED') AS verified,
                count(DISTINCT d.id) FILTER (WHERE d.status='REVIEW') AS review,
                count(DISTINCT d.id) FILTER (WHERE d.extraction_method='LOCAL_OCR') AS ocr,
                max(d.created_at) AS last_seen
                FROM documents d LEFT JOIN format_fingerprints fp ON fp.document_id=d.id
                LEFT JOIN document_format_families f ON f.id=fp.family_id
                LEFT JOIN template_versions tv ON tv.family_id=f.id
                WHERE d.organization_id=%s AND d.company_id=%s
                GROUP BY f.id,f.name ORDER BY documents_seen DESC""", (organization_id, company_id))
            records = self._records(cursor)
        for record in records:
            total = record["documents_seen"] or 0
            record["success_rate"] = Decimal(record["verified"] or 0) * 100 / Decimal(total) if total else Decimal("0")
            record["review_rate"] = Decimal(record["review"] or 0) * 100 / Decimal(total) if total else Decimal("0")
            record["ocr_rate"] = Decimal(record["ocr"] or 0) * 100 / Decimal(total) if total else Decimal("0")
            record["unknown_variations"] = total if record["family_id"] == "unknown" else 0
        return records
