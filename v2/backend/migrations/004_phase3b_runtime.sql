-- Phase 3B runtime, durable batch progress, metrics, and report support.
BEGIN;
ALTER TABLE document_batches ADD COLUMN status text NOT NULL DEFAULT 'QUEUED'
    CHECK (status IN ('QUEUED','RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','INTERRUPTED'));
ALTER TABLE document_batches ADD COLUMN queued integer NOT NULL DEFAULT 0 CHECK (queued >= 0);
ALTER TABLE document_batches ADD COLUMN running integer NOT NULL DEFAULT 0 CHECK (running >= 0);
ALTER TABLE document_batches ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE document_batches ADD COLUMN restart_note text NOT NULL DEFAULT '';
CREATE INDEX ix_document_batches_tenant_created ON document_batches(organization_id, company_id, created_at DESC);
COMMIT;
