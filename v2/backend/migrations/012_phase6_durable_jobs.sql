-- Restart-safe local document queue. Source bytes remain in protected filesystem storage.
BEGIN;

CREATE TABLE durable_document_jobs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    batch_id uuid REFERENCES document_batches(id),
    initiated_by uuid NOT NULL REFERENCES users(id),
    source_storage_key text NOT NULL,
    original_filename text NOT NULL,
    mime_type text NOT NULL,
    source_sha256 char(64) NOT NULL,
    status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')),
    progress integer NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
    attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK(max_attempts BETWEEN 1 AND 10),
    available_at timestamptz NOT NULL DEFAULT now(),
    claimed_by text,
    claimed_at timestamptz,
    heartbeat_at timestamptz,
    cancel_requested boolean NOT NULL DEFAULT false,
    document_id uuid REFERENCES documents(id),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX durable_document_jobs_tenant_status_idx
    ON durable_document_jobs(organization_id,company_id,status,available_at,created_at);
CREATE UNIQUE INDEX durable_document_jobs_active_source_idx
    ON durable_document_jobs(organization_id,company_id,source_sha256,batch_id)
    WHERE status IN ('QUEUED','RUNNING');

-- Non-content scheduling index lets a local worker discover tenant context before
-- opening the RLS-protected job. It contains no filenames, document text, or PII.
CREATE TABLE durable_job_schedule (
    job_id uuid PRIMARY KEY REFERENCES durable_document_jobs(id) ON DELETE CASCADE,
    organization_id uuid NOT NULL,
    company_id uuid NOT NULL,
    batch_id uuid,
    status text NOT NULL CHECK(status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')),
    available_at timestamptz NOT NULL,
    heartbeat_at timestamptz
);
CREATE INDEX durable_job_schedule_claim_idx ON durable_job_schedule(status,available_at,job_id);

ALTER TABLE durable_document_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE durable_document_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY v2_tenant_isolation ON durable_document_jobs
    USING (organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
       AND company_id=nullif(current_setting('app.company_id',true),'')::uuid)
    WITH CHECK (organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
       AND company_id=nullif(current_setting('app.company_id',true),'')::uuid);

COMMIT;
