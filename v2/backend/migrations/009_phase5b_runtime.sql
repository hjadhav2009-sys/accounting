-- Phase 5B reset-queue runtime metadata. PostgreSQL V2 only.
BEGIN;
ALTER TABLE ai_jobs ADD COLUMN document_id uuid REFERENCES documents(id);
ALTER TABLE ai_jobs ADD COLUMN template_version_id uuid REFERENCES template_versions(id);
ALTER TABLE ai_jobs ADD COLUMN template_revision integer CHECK (template_revision IS NULL OR template_revision > 0);
ALTER TABLE ai_jobs ADD COLUMN not_before timestamptz;
CREATE INDEX ai_jobs_reset_dispatch_idx ON ai_jobs(not_before,organization_id,company_id)
    WHERE status='QUEUED' AND route_reason='QUOTA_RESET';
COMMIT;
