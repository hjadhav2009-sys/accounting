BEGIN;

CREATE TABLE mapping_import_previews (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    workbook_sha256 char(64) NOT NULL,
    rows_json jsonb NOT NULL,
    summary jsonb NOT NULL,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    applied_at timestamptz
);
CREATE TABLE mapping_import_backups (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    preview_id uuid NOT NULL REFERENCES mapping_import_previews(id),
    snapshot jsonb NOT NULL,
    snapshot_sha256 char(64) NOT NULL,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['mapping_import_previews','mapping_import_backups'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format('CREATE POLICY v2_tenant_isolation ON %I USING (organization_id=nullif(current_setting(''app.organization_id'',true),'''')::uuid AND company_id=nullif(current_setting(''app.company_id'',true),'''')::uuid) WITH CHECK (organization_id=nullif(current_setting(''app.organization_id'',true),'''')::uuid AND company_id=nullif(current_setting(''app.company_id'',true),'''')::uuid)',table_name);
  END LOOP;
END $rls$;

COMMIT;
