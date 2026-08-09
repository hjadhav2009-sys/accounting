from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID, uuid4


@dataclass(frozen=True)
class DurableDocumentJob:
    id:UUID;organization_id:UUID;company_id:UUID;batch_id:UUID|None;initiated_by:UUID
    source_storage_key:str;original_filename:str;mime_type:str;attempt_count:int;max_attempts:int


class DurableJobRepository:
    """PostgreSQL queue with a metadata-only scheduler and RLS-protected payload rows."""
    def __init__(self,connect:Callable[[],Any]): self.connect=connect

    @staticmethod
    def _tenant(cursor,organization_id:UUID,company_id:UUID)->None:
        cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(organization_id),))
        cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company_id),))

    def _tenant_pairs(self,cursor)->list[tuple[UUID,UUID]]:
        """Discover IDs only, then enter each RLS context before reading queue metadata."""
        cursor.execute("SELECT id FROM organizations ORDER BY id")
        organizations=[row[0] for row in cursor.fetchall()];pairs=[]
        for organization_id in organizations:
            cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(organization_id),))
            cursor.execute("SELECT id FROM companies WHERE organization_id=%s ORDER BY id",(organization_id,))
            pairs.extend((organization_id,row[0]) for row in cursor.fetchall())
        return pairs

    def enqueue(self,organization_id:UUID,company_id:UUID,batch_id:UUID|None,user_id:UUID,
                storage_key:str,filename:str,mime_type:str,sha256:str)->UUID:
        job_id=uuid4();connection=self.connect()
        try:
            with connection.cursor() as cursor:
                self._tenant(cursor,organization_id,company_id)
                cursor.execute("""INSERT INTO durable_document_jobs
                    (id,organization_id,company_id,batch_id,initiated_by,source_storage_key,original_filename,mime_type,source_sha256)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (job_id,organization_id,company_id,batch_id,user_id,storage_key,filename,mime_type,sha256))
                cursor.execute("""INSERT INTO durable_job_schedule(job_id,organization_id,company_id,batch_id,status,available_at)
                    VALUES(%s,%s,%s,%s,'QUEUED',now())""",(job_id,organization_id,company_id,batch_id))
            connection.commit();return job_id
        except Exception: connection.rollback();raise
        finally: connection.close()

    def claim(self,worker_id:str,batch_id:UUID|None=None)->DurableDocumentJob|None:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                candidates=[]
                for organization_id,company_id in self._tenant_pairs(cursor):
                    self._tenant(cursor,organization_id,company_id)
                    cursor.execute("""SELECT job_id,available_at FROM durable_job_schedule
                        WHERE status='QUEUED' AND available_at<=now() AND (%s::uuid IS NULL OR batch_id=%s)
                        ORDER BY available_at,job_id LIMIT 1""",(batch_id,batch_id))
                    row=cursor.fetchone()
                    if row:candidates.append((row[1],row[0],organization_id,company_id))
                scheduled=None
                for _available,job_id,organization_id,company_id in sorted(candidates):
                    self._tenant(cursor,organization_id,company_id)
                    cursor.execute("""SELECT job_id FROM durable_job_schedule WHERE job_id=%s AND status='QUEUED'
                        AND available_at<=now() FOR UPDATE SKIP LOCKED""",(job_id,))
                    if cursor.fetchone():scheduled=(job_id,organization_id,company_id);break
                if not scheduled: connection.rollback();return None
                job_id,organization_id,company_id=scheduled
                cursor.execute("""UPDATE durable_document_jobs SET status='RUNNING',attempt_count=attempt_count+1,
                    claimed_by=%s,claimed_at=now(),heartbeat_at=now(),progress=1
                    WHERE id=%s AND status='QUEUED' AND cancel_requested=false
                    RETURNING id,organization_id,company_id,batch_id,initiated_by,source_storage_key,
                              original_filename,mime_type,attempt_count,max_attempts""",(worker_id,job_id))
                row=cursor.fetchone()
                if not row:
                    cursor.execute("UPDATE durable_job_schedule SET status='CANCELLED' WHERE job_id=%s",(job_id,))
                    connection.commit();return None
                cursor.execute("UPDATE durable_job_schedule SET status='RUNNING',heartbeat_at=now() WHERE job_id=%s",(job_id,))
            connection.commit();return DurableDocumentJob(*row)
        except Exception: connection.rollback();raise
        finally: connection.close()

    def heartbeat(self,job:DurableDocumentJob,progress:int)->None:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                self._tenant(cursor,job.organization_id,job.company_id)
                cursor.execute("UPDATE durable_document_jobs SET heartbeat_at=now(),progress=%s WHERE id=%s AND status='RUNNING'",
                               (max(1,min(99,progress)),job.id))
                cursor.execute("UPDATE durable_job_schedule SET heartbeat_at=now() WHERE job_id=%s",(job.id,))
            connection.commit()
        finally: connection.close()

    def finish(self,job:DurableDocumentJob,document_id:UUID|None,error_code:str="",retryable:bool=True)->str:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                self._tenant(cursor,job.organization_id,job.company_id)
                status="COMPLETED" if document_id else ("QUEUED" if retryable and job.attempt_count<job.max_attempts else "FAILED")
                available=datetime.now(timezone.utc)+timedelta(seconds=min(60,2**job.attempt_count))
                cursor.execute("""UPDATE durable_document_jobs SET status=%s,progress=%s,document_id=%s,error_code=%s,
                    available_at=%s,completed_at=CASE WHEN %s IN ('COMPLETED','FAILED') THEN now() END
                    WHERE id=%s""",(status,100 if document_id else 0,document_id,error_code[:80],available,status,job.id))
                cursor.execute("UPDATE durable_job_schedule SET status=%s,available_at=%s,heartbeat_at=now() WHERE job_id=%s",
                               (status,available,job.id))
            connection.commit();return status
        except Exception: connection.rollback();raise
        finally: connection.close()

    def cancel(self,organization_id:UUID,company_id:UUID,job_id:UUID)->bool:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                self._tenant(cursor,organization_id,company_id)
                cursor.execute("""UPDATE durable_document_jobs SET cancel_requested=true,
                    status=CASE WHEN status='QUEUED' THEN 'CANCELLED' ELSE status END
                    WHERE id=%s AND status IN ('QUEUED','RUNNING') RETURNING status""",(job_id,))
                row=cursor.fetchone()
                if row and row[0]=='CANCELLED':cursor.execute("UPDATE durable_job_schedule SET status='CANCELLED' WHERE job_id=%s",(job_id,))
            connection.commit();return bool(row)
        finally: connection.close()

    def recover_stale(self,older_than_seconds:int=120)->int:
        connection=self.connect();recovered=0
        try:
            with connection.cursor() as cursor:
                stale=[]
                for organization_id,company_id in self._tenant_pairs(cursor):
                    self._tenant(cursor,organization_id,company_id)
                    cursor.execute("""SELECT job_id FROM durable_job_schedule WHERE status='RUNNING'
                        AND heartbeat_at<now()-(%s*interval '1 second') FOR UPDATE SKIP LOCKED""",(older_than_seconds,))
                    stale.extend((row[0],organization_id,company_id) for row in cursor.fetchall())
                for job_id,organization_id,company_id in stale:
                    self._tenant(cursor,organization_id,company_id)
                    cursor.execute("""UPDATE durable_document_jobs SET status=CASE WHEN attempt_count<max_attempts THEN 'QUEUED' ELSE 'FAILED' END,
                        available_at=now(),claimed_by=NULL,claimed_at=NULL WHERE id=%s RETURNING status""",(job_id,))
                    status=cursor.fetchone()[0]
                    cursor.execute("UPDATE durable_job_schedule SET status=%s,available_at=now() WHERE job_id=%s",(status,job_id));recovered+=1
            connection.commit();return recovered
        except Exception:connection.rollback();raise
        finally:connection.close()

    def active_for_batch(self,batch_id:UUID)->int:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                for organization_id,company_id in self._tenant_pairs(cursor):
                    self._tenant(cursor,organization_id,company_id)
                    cursor.execute("SELECT count(*) FROM durable_job_schedule WHERE batch_id=%s AND status IN ('QUEUED','RUNNING')",(batch_id,))
                    count=int(cursor.fetchone()[0])
                    if count:return count
                return 0
        finally:connection.close()

    def status(self,job_id:UUID)->str|None:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                for organization_id,company_id in self._tenant_pairs(cursor):
                    self._tenant(cursor,organization_id,company_id)
                    cursor.execute("SELECT status FROM durable_job_schedule WHERE job_id=%s",(job_id,));row=cursor.fetchone()
                    if row:return row[0]
                return None
        finally:connection.close()
