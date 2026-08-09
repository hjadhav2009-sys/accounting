BEGIN;

CREATE TABLE duplicate_upload_attempts (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    existing_document_id uuid NOT NULL REFERENCES documents(id),
    attempted_by uuid NOT NULL REFERENCES users(id),
    sha256 char(64) NOT NULL,
    original_filename text NOT NULL,
    attempted_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX duplicate_upload_attempts_tenant_time_idx
    ON duplicate_upload_attempts(organization_id,company_id,attempted_at DESC);
ALTER TABLE duplicate_upload_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE duplicate_upload_attempts FORCE ROW LEVEL SECURITY;
CREATE POLICY v2_tenant_isolation ON duplicate_upload_attempts
USING (organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
   AND company_id=nullif(current_setting('app.company_id',true),'')::uuid)
WITH CHECK (organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
   AND company_id=nullif(current_setting('app.company_id',true),'')::uuid);

COMMIT;
