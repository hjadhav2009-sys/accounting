-- Phase 4 deterministic Template Studio metadata. PostgreSQL V2 only.
BEGIN;

ALTER TABLE document_format_families ADD COLUMN company_id uuid REFERENCES companies(id);
ALTER TABLE document_format_families ADD COLUMN description text NOT NULL DEFAULT '';
ALTER TABLE document_format_families ADD COLUMN metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE document_format_families ADD COLUMN created_by uuid REFERENCES users(id);
ALTER TABLE document_format_families ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE document_format_families ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

UPDATE document_format_families family SET company_id=source.company_id
FROM (
    SELECT fp.family_id, min(d.company_id::text)::uuid AS company_id
    FROM format_fingerprints fp JOIN documents d ON d.id=fp.document_id
    WHERE fp.family_id IS NOT NULL
    GROUP BY fp.family_id HAVING count(DISTINCT d.company_id)=1
) source WHERE family.id=source.family_id AND family.company_id IS NULL;

ALTER TABLE template_versions ADD COLUMN schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version > 0);
ALTER TABLE template_versions ADD COLUMN revision integer NOT NULL DEFAULT 1 CHECK (revision > 0);
ALTER TABLE template_versions ADD COLUMN parent_version_id uuid REFERENCES template_versions(id);
ALTER TABLE template_versions ADD COLUMN validation_profile text NOT NULL DEFAULT 'GENERIC';
ALTER TABLE template_versions ADD COLUMN engine text NOT NULL DEFAULT 'VISUAL_RULES'
    CHECK (engine IN ('VISUAL_RULES','LEGACY_ADAPTER','LEGACY_PARSER'));
ALTER TABLE template_versions ADD COLUMN approval_evidence jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE template_versions ADD COLUMN change_summary text NOT NULL DEFAULT '';
ALTER TABLE template_versions ADD COLUMN updated_by uuid REFERENCES users(id);
ALTER TABLE template_versions ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE template_versions ADD COLUMN deprecated_by uuid REFERENCES users(id);
ALTER TABLE template_versions ADD COLUMN deprecated_at timestamptz;

ALTER TABLE template_samples ADD COLUMN status text NOT NULL DEFAULT 'ACTIVE'
    CHECK (status IN ('ACTIVE','REMOVED'));
ALTER TABLE template_samples ADD COLUMN notes text NOT NULL DEFAULT '';
ALTER TABLE template_samples ADD COLUMN added_by uuid REFERENCES users(id);
ALTER TABLE template_samples ADD COLUMN added_at timestamptz NOT NULL DEFAULT now();

CREATE TABLE template_test_runs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    template_version_id uuid NOT NULL REFERENCES template_versions(id),
    status text NOT NULL CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED')),
    total integer NOT NULL DEFAULT 0 CHECK (total >= 0),
    processed integer NOT NULL DEFAULT 0 CHECK (processed >= 0),
    verified integer NOT NULL DEFAULT 0 CHECK (verified >= 0),
    review integer NOT NULL DEFAULT 0 CHECK (review >= 0),
    blocked integer NOT NULL DEFAULT 0 CHECK (blocked >= 0),
    failed integer NOT NULL DEFAULT 0 CHECK (failed >= 0),
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE template_test_results (
    id uuid PRIMARY KEY,
    test_run_id uuid NOT NULL REFERENCES template_test_runs(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES documents(id),
    result text NOT NULL CHECK (result IN ('VERIFIED','REVIEW','BLOCKED','FAILED')),
    extraction jsonb NOT NULL DEFAULT '{}'::jsonb,
    validation jsonb NOT NULL DEFAULT '{}'::jsonb,
    comparison jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_code text,
    duration_ms integer NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    UNIQUE(test_run_id, document_id)
);

CREATE TABLE template_activity (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    family_id uuid NOT NULL REFERENCES document_format_families(id),
    template_version_id uuid REFERENCES template_versions(id),
    actor_id uuid NOT NULL REFERENCES users(id),
    event_type text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE template_comments (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    family_id uuid NOT NULL REFERENCES document_format_families(id),
    template_version_id uuid REFERENCES template_versions(id),
    document_id uuid REFERENCES documents(id),
    author_id uuid NOT NULL REFERENCES users(id),
    note text NOT NULL CHECK (char_length(note) BETWEEN 1 AND 2000),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION prevent_approved_template_mutation() RETURNS trigger AS $$
BEGIN
    IF OLD.status = 'APPROVED' AND (
        NEW.definition IS DISTINCT FROM OLD.definition OR
        NEW.schema_version IS DISTINCT FROM OLD.schema_version OR
        NEW.validation_profile IS DISTINCT FROM OLD.validation_profile OR
        NEW.engine IS DISTINCT FROM OLD.engine OR
        NEW.version IS DISTINCT FROM OLD.version OR
        NEW.family_id IS DISTINCT FROM OLD.family_id
    ) THEN
        RAISE EXCEPTION 'approved template versions are immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER template_approved_immutable BEFORE UPDATE ON template_versions
FOR EACH ROW EXECUTE FUNCTION prevent_approved_template_mutation();

CREATE INDEX ix_format_family_company ON document_format_families(organization_id,company_id,document_type);
CREATE INDEX ix_template_versions_family_status ON template_versions(family_id,status,version DESC);
CREATE INDEX ix_template_samples_version ON template_samples(template_version_id,status);
CREATE INDEX ix_template_runs_tenant ON template_test_runs(organization_id,company_id,created_at DESC);
CREATE INDEX ix_template_activity_tenant ON template_activity(organization_id,company_id,family_id,created_at DESC);

COMMIT;
