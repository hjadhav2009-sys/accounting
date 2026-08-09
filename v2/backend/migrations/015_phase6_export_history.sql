BEGIN;

CREATE TABLE document_exports (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid NOT NULL REFERENCES documents(id),
    export_type text NOT NULL CHECK (export_type IN ('EXCEL','MARKETPLACE_XML','BANK_XML')),
    filename text NOT NULL,
    file_sha256 char(64) NOT NULL,
    validation_status text NOT NULL,
    extraction_result_id uuid REFERENCES document_extractions(id),
    template_version_id uuid REFERENCES template_versions(id),
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX document_exports_tenant_created_idx ON document_exports(organization_id,company_id,created_at DESC);
CREATE INDEX document_exports_document_idx ON document_exports(document_id,created_at DESC);

ALTER TABLE document_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_exports FORCE ROW LEVEL SECURITY;
CREATE POLICY v2_tenant_isolation ON document_exports
USING (
    organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
    AND company_id=nullif(current_setting('app.company_id',true),'')::uuid
)
WITH CHECK (
    organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
    AND company_id=nullif(current_setting('app.company_id',true),'')::uuid
);

COMMIT;
