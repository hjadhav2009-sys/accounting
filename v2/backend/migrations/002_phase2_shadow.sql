-- Phase 2 development/shadow additions. PostgreSQL remains non-authoritative.
BEGIN;

ALTER TABLE companies ADD COLUMN suspense_ledger text NOT NULL DEFAULT 'Suspense';
ALTER TABLE companies ADD COLUMN cgst_ledger text NOT NULL DEFAULT 'INPUT CGST';
ALTER TABLE companies ADD COLUMN sgst_ledger text NOT NULL DEFAULT 'INPUT SGST';
ALTER TABLE companies ADD COLUMN igst_ledger text NOT NULL DEFAULT 'INPUT IGST';
ALTER TABLE bank_accounts ADD COLUMN notes text;
ALTER TABLE ledger_mappings ADD COLUMN notes text;
ALTER TABLE extraction_jobs ALTER COLUMN document_id DROP NOT NULL;

CREATE TABLE legacy_identity_map (
    legacy_source text NOT NULL,
    legacy_table text NOT NULL,
    legacy_id text NOT NULL,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid REFERENCES companies(id),
    v2_uuid uuid NOT NULL,
    source_fingerprint char(64) NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (legacy_source, legacy_table, legacy_id, organization_id),
    UNIQUE (v2_uuid)
);

CREATE TABLE migration_runs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    source_sha256 char(64) NOT NULL,
    source_sha256_after char(64) NOT NULL,
    status text NOT NULL CHECK (status IN ('RUNNING','COMPLETED','FAILED')),
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE migration_normalizations (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    legacy_table text NOT NULL,
    legacy_id text NOT NULL,
    field_name text NOT NULL,
    source_value text NOT NULL,
    normalized_value text NOT NULL,
    normalization_rule text NOT NULL,
    UNIQUE(organization_id, legacy_table, legacy_id, field_name)
);

CREATE TABLE parity_observations (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid REFERENCES companies(id),
    query_type text NOT NULL,
    result text NOT NULL CHECK (result IN ('MATCH','MISMATCH','MISSING_IN_POSTGRES','EXTRA_IN_POSTGRES','NORMALIZATION_DIFFERENCE','SHADOW_ERROR')),
    source_reference text,
    observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE invoices (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid REFERENCES documents(id),
    invoice_number text NOT NULL,
    invoice_date date,
    supplier text NOT NULL,
    document_type text NOT NULL,
    currency char(3) NOT NULL DEFAULT 'INR',
    total numeric(18,2) NOT NULL DEFAULT 0,
    UNIQUE(company_id, document_type, invoice_number)
);

CREATE TABLE invoice_tax_buckets (
    id uuid PRIMARY KEY,
    invoice_id uuid NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    tax_type text NOT NULL CHECK (tax_type IN ('CGST','SGST','IGST')),
    rate numeric(9,4) NOT NULL CHECK (rate >= 0),
    taxable numeric(18,2) NOT NULL,
    tax numeric(18,2) NOT NULL,
    hsn_sac text NOT NULL DEFAULT '',
    UNIQUE(invoice_id, tax_type, rate, hsn_sac)
);

CREATE INDEX ix_legacy_identity_v2 ON legacy_identity_map(organization_id, v2_uuid);
CREATE INDEX ix_parity_observations_summary ON parity_observations(organization_id, result, observed_at DESC);
CREATE INDEX ix_invoice_tax_buckets_invoice ON invoice_tax_buckets(invoice_id, rate);

-- Candidate policies are created for development validation but RLS is not enabled.
CREATE POLICY companies_tenant_candidate ON companies
    USING (organization_id = nullif(current_setting('app.organization_id', true), '')::uuid);
CREATE POLICY ledger_mappings_tenant_candidate ON ledger_mappings
    USING (organization_id = nullif(current_setting('app.organization_id', true), '')::uuid);
CREATE POLICY documents_tenant_candidate ON documents
    USING (organization_id = nullif(current_setting('app.organization_id', true), '')::uuid);
CREATE POLICY extraction_jobs_tenant_candidate ON extraction_jobs
    USING (organization_id = nullif(current_setting('app.organization_id', true), '')::uuid);
CREATE POLICY audit_logs_tenant_candidate ON audit_logs
    USING (organization_id = nullif(current_setting('app.organization_id', true), '')::uuid);

COMMIT;
