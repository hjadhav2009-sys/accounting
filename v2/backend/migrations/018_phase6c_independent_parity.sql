-- Phase 6C independent document parity and preview-first legacy data migration.
BEGIN;

CREATE TABLE document_parity_runs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid NOT NULL REFERENCES documents(id),
    mode text NOT NULL CHECK (mode IN ('LEGACY_REFERENCE','V2_NATIVE','COMPARE')),
    status text NOT NULL CHECK (status IN ('MATCH','DIFFERENCE','MISSING_LEGACY','MISSING_V2','BLOCKED')),
    legacy_template text,
    v2_template_version_id uuid REFERENCES template_versions(id),
    legacy_result jsonb NOT NULL DEFAULT '{}'::jsonb,
    v2_result jsonb NOT NULL DEFAULT '{}'::jsonb,
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document_parity_fields (
    id uuid PRIMARY KEY,
    parity_run_id uuid NOT NULL REFERENCES document_parity_runs(id) ON DELETE CASCADE,
    field_path text NOT NULL,
    status text NOT NULL CHECK (status IN ('MATCH','DIFFERENCE','MISSING_LEGACY','MISSING_V2','BLOCKED')),
    legacy_value jsonb,
    v2_value jsonb,
    UNIQUE(parity_run_id,field_path)
);

CREATE TABLE sqlite_migration_previews (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    source_file text NOT NULL,
    source_sha256 char(64) NOT NULL,
    expected_sha256 char(64) NOT NULL,
    status text NOT NULL CHECK (status IN ('PREVIEW','APPLIED','STALE','BLOCKED')),
    report jsonb NOT NULL,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    applied_at timestamptz
);

CREATE INDEX ix_document_parity_tenant ON document_parity_runs(organization_id,company_id,created_at DESC);
CREATE INDEX ix_sqlite_migration_preview_tenant ON sqlite_migration_previews(organization_id,created_at DESC);

ALTER TABLE document_parity_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_parity_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY v2_tenant_isolation ON document_parity_runs USING (
    organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
    AND company_id=nullif(current_setting('app.company_id',true),'')::uuid
) WITH CHECK (
    organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
    AND company_id=nullif(current_setting('app.company_id',true),'')::uuid
);

ALTER TABLE sqlite_migration_previews ENABLE ROW LEVEL SECURITY;
ALTER TABLE sqlite_migration_previews FORCE ROW LEVEL SECURITY;
CREATE POLICY v2_tenant_isolation ON sqlite_migration_previews USING (
    organization_id=nullif(current_setting('app.organization_id',true),'')::uuid
) WITH CHECK (organization_id=nullif(current_setting('app.organization_id',true),'')::uuid);

COMMIT;
