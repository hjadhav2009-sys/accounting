BEGIN;

CREATE TABLE financial_years (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    label text NOT NULL,
    starts_on date NOT NULL,
    ends_on date NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(company_id,label),
    CHECK (ends_on>starts_on)
);
ALTER TABLE documents ADD COLUMN financial_year_id uuid REFERENCES financial_years(id);
CREATE INDEX documents_financial_year_idx ON documents(organization_id,company_id,financial_year_id,invoice_date);

ALTER TABLE financial_years ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_years FORCE ROW LEVEL SECURITY;
CREATE POLICY v2_tenant_isolation ON financial_years
USING (organization_id=nullif(current_setting('app.organization_id',true),'')::uuid AND company_id=nullif(current_setting('app.company_id',true),'')::uuid)
WITH CHECK (organization_id=nullif(current_setting('app.organization_id',true),'')::uuid AND company_id=nullif(current_setting('app.company_id',true),'')::uuid);

COMMIT;
