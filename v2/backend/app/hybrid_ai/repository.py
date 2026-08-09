from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID, uuid4


class AiRepository:
    def __init__(self, connect: Callable[[], Any]) -> None: self._connect = connect

    @contextmanager
    def _cursor(self):
        connection = self._connect()
        try:
            with connection.cursor() as cursor: yield cursor
            connection.commit()
        except Exception:
            connection.rollback(); raise
        finally: connection.close()

    @staticmethod
    def _record(cursor, row):
        if row is None: return None
        names = [column.name if hasattr(column, "name") else column[0] for column in cursor.description]
        return dict(zip(names, row))

    def create_job(self, organization_id: UUID, company_id: UUID, user_id: UUID, task: str,
                   mode: str, privacy_mode: str, prompt_version: str) -> dict[str, Any]:
        job_id = uuid4()
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO ai_jobs(id,organization_id,company_id,created_by,task,mode,privacy_mode,status,prompt_version)
                VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',%s) RETURNING *""",
                (job_id,organization_id,company_id,user_id,task,mode,privacy_mode,prompt_version))
            return self._record(cursor,cursor.fetchone())

    def finish_job(self, organization_id: UUID, company_id: UUID, job_id: UUID, result: dict[str, Any]) -> dict[str, Any] | None:
        state = str(result.get("state", "FAILED"))
        status = "READY_FOR_REVIEW" if state.endswith("READY_FOR_REVIEW") else "FAILED"
        proposal = result.get("proposal") or {}
        usage = result.get("usage") or {}
        with self._cursor() as cursor:
            cursor.execute("""UPDATE ai_jobs SET status=%s,provider=%s,model_key=%s,route_reason=%s,
                sanitized_input_sha256=%s,input_tokens=%s,output_tokens=%s,usage_units=%s,completed_at=now()
                WHERE id=%s AND organization_id=%s AND company_id=%s RETURNING *""",
                (status,proposal.get("provider",""),proposal.get("model",""),result.get("route_reason",result.get("reason","")),
                 (result.get("payload_preview") or {}).get("sanitized_sha256"),usage.get("input_tokens",0),usage.get("output_tokens",0),
                 usage.get("accounted_neurons",0),job_id,organization_id,company_id))
            job=self._record(cursor,cursor.fetchone())
            if job and proposal:
                cursor.execute("""INSERT INTO ai_template_proposals(id,organization_id,company_id,job_id,summary,proposal,status)
                    VALUES(%s,%s,%s,%s,%s,%s::jsonb,'PROPOSED')""",
                    (proposal.get("proposal_id",uuid4()),organization_id,company_id,job_id,proposal.get("summary",""),json.dumps(proposal)))
            if job:
                cursor.execute("""INSERT INTO ai_audit_events
                    (id,organization_id,company_id,actor_id,job_id,event_type,intent_summary,action_summary,provider,model_key,usage_metadata,safe_metadata)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s::jsonb)""",
                    (uuid4(),organization_id,company_id,job["created_by"],job_id,"AI_PROPOSAL_COMPLETED",
                     job["task"][:200],json.dumps([item.get("action","") for item in proposal.get("actions",[])]),
                     proposal.get("provider",""),proposal.get("model",""),json.dumps(usage),
                     json.dumps({"state":state,"raw_payload_retained":False})))
            return job

    def cancel_job(self, organization_id: UUID, company_id: UUID, job_id: UUID,
                   actor_id: UUID | None = None, privileged: bool = False) -> bool:
        with self._cursor() as cursor:
            cursor.execute("""UPDATE ai_jobs SET cancel_requested=true,status='CANCELLED',completed_at=now()
                WHERE id=%s AND organization_id=%s AND company_id=%s AND status IN ('QUEUED','RUNNING')
                  AND (created_by=%s OR %s::boolean)""",
                (job_id,organization_id,company_id,actor_id,privileged))
            return cursor.rowcount == 1

    def queue_until_reset(self, organization_id: UUID, company_id: UUID, job_id: UUID,
                          document_id: UUID, template_version_id: UUID,
                          template_revision: int, reset_at: datetime) -> bool:
        with self._cursor() as cursor:
            cursor.execute("""UPDATE ai_jobs SET status='QUEUED',route_reason='QUOTA_RESET',document_id=%s,
                template_version_id=%s,template_revision=%s,not_before=%s
                WHERE id=%s AND organization_id=%s AND company_id=%s AND cancel_requested=false""",
                (document_id,template_version_id,template_revision,reset_at,job_id,organization_id,company_id))
            return cursor.rowcount == 1

    def claim_reset_job(self, organization_id: UUID, company_id: UUID, job_id: UUID,
                        now: datetime) -> bool:
        """Atomically re-check persisted document/template state before resuming."""
        with self._cursor() as cursor:
            cursor.execute("""UPDATE ai_jobs j SET status='RUNNING',started_at=%s
                WHERE j.id=%s AND j.organization_id=%s AND j.company_id=%s AND j.status='QUEUED'
                  AND j.route_reason='QUOTA_RESET' AND j.cancel_requested=false AND j.not_before<=%s
                  AND EXISTS (SELECT 1 FROM documents d WHERE d.id=j.document_id
                    AND d.organization_id=j.organization_id AND d.company_id=j.company_id)
                  AND EXISTS (SELECT 1 FROM template_versions tv JOIN document_format_families f ON f.id=tv.family_id
                    WHERE tv.id=j.template_version_id AND tv.revision=j.template_revision
                      AND f.organization_id=j.organization_id AND f.company_id=j.company_id)""",
                (now,job_id,organization_id,company_id,now))
            return cursor.rowcount == 1

    def dashboard(self, organization_id: UUID, company_id: UUID) -> dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute("""SELECT status,count(*) FROM ai_jobs WHERE organization_id=%s AND company_id=%s GROUP BY status""",
                           (organization_id,company_id))
            jobs={row[0]:row[1] for row in cursor.fetchall()}
            cursor.execute("""SELECT coalesce(sum(input_tokens),0),coalesce(sum(output_tokens),0),coalesce(sum(usage_units),0)
                FROM ai_jobs WHERE organization_id=%s AND company_id=%s AND created_at >= now()-interval '30 days'""",
                (organization_id,company_id))
            usage=cursor.fetchone()
            return {"jobs":jobs,"usage_30d":{"input_tokens":usage[0],"output_tokens":usage[1],"units":usage[2]},
                    "raw_payload_retention":False,"reset_timezone":"UTC"}

    def purge_expired_cache(self, organization_id: UUID) -> int:
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM ai_response_cache WHERE organization_id=%s AND expires_at<now()",(organization_id,))
            return cursor.rowcount

    def store_approved_correction(self, organization_id: UUID, company_id: UUID,
                                  template_version_id: UUID, approved_by: UUID,
                                  format_family: str, document_type: str,
                                  correction: dict[str, Any]) -> dict[str, Any]:
        """Persist only corrections tied to an APPROVED tenant-owned template."""
        memory_id = uuid4()
        fingerprint = {"format_family": format_family[:160], "document_type": document_type[:100]}
        with self._cursor() as cursor:
            cursor.execute("""INSERT INTO ai_correction_memory
                (id,organization_id,company_id,template_version_id,fingerprint,correction,approved_by)
                SELECT %s,%s,%s,tv.id,%s::jsonb,%s::jsonb,%s
                FROM template_versions tv JOIN document_format_families f ON f.id=tv.family_id
                WHERE tv.id=%s AND f.organization_id=%s AND f.company_id=%s AND tv.status='APPROVED'
                RETURNING *""",(memory_id,organization_id,company_id,
                    json.dumps(fingerprint),json.dumps(correction),approved_by,template_version_id,
                    organization_id,company_id))
            row=self._record(cursor,cursor.fetchone())
            if not row: raise ValueError("correction memory requires an approved tenant template")
            return row

    def retrieve_approved_corrections(self, organization_id: UUID, company_id: UUID,
                                      format_family: str, document_type: str,
                                      limit: int = 5) -> list[dict[str, Any]]:
        if not 1 <= limit <= 20: raise ValueError("correction retrieval limit must be 1-20")
        with self._cursor() as cursor:
            cursor.execute("""SELECT m.correction,m.approved_at,m.template_version_id
                FROM ai_correction_memory m
                JOIN template_versions tv ON tv.id=m.template_version_id AND tv.status='APPROVED'
                JOIN document_format_families f ON f.id=tv.family_id
                WHERE m.organization_id=%s AND m.company_id=%s AND f.organization_id=%s AND f.company_id=%s
                  AND m.active=true AND m.fingerprint->>'format_family'=%s
                  AND m.fingerprint->>'document_type'=%s
                ORDER BY m.approved_at DESC,m.id LIMIT %s""",
                (organization_id,company_id,organization_id,company_id,format_family,document_type,limit))
            return [{"correction":row[0],"approved_at":row[1],"template_version_id":row[2]}
                    for row in cursor.fetchall()]
