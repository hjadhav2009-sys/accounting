-- Phase 1 design only. PostgreSQL is NOT authoritative and this migration is not auto-run.
BEGIN;

CREATE TABLE organizations (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (name)
);

CREATE TABLE companies (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    name text NOT NULL,
    tally_company_name text NOT NULL,
    gstin text,
    state text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, name)
);

CREATE TABLE users (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    email text NOT NULL,
    display_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('ACTIVE','DISABLED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, email)
);

CREATE TABLE roles (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    code text NOT NULL CHECK (code IN ('OWNER','ADMIN','ACCOUNTANT','OPERATOR','REVIEWER','VIEWER')),
    UNIQUE (organization_id, code)
);

CREATE TABLE user_company_access (
    user_id uuid NOT NULL REFERENCES users(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    role_id uuid NOT NULL REFERENCES roles(id),
    PRIMARY KEY (user_id, company_id, role_id)
);

CREATE TABLE bank_accounts (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    account_hint_token text NOT NULL,
    bank_ledger text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE',
    UNIQUE (company_id, account_hint_token, bank_ledger)
);

CREATE TABLE party_ledgers (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    platform text NOT NULL,
    party_ledger text NOT NULL,
    party_gstin text,
    state text,
    UNIQUE (company_id, platform)
);

CREATE TABLE gst_ledgers (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    tax_type text NOT NULL CHECK (tax_type IN ('CGST','SGST','IGST')),
    ledger_name text NOT NULL,
    UNIQUE (company_id, tax_type)
);

CREATE TABLE ledger_mappings (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    tool text NOT NULL,
    platform text NOT NULL DEFAULT '',
    pattern text NOT NULL,
    voucher_type text NOT NULL DEFAULT '',
    ledger text NOT NULL,
    match_type text NOT NULL CHECK (match_type IN ('contains','smart_contains','equals','starts_with','regex')),
    priority integer NOT NULL DEFAULT 0,
    enabled boolean NOT NULL DEFAULT true,
    UNIQUE (company_id, tool, platform, pattern, voucher_type)
);

CREATE TABLE voucher_rules (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    platform text NOT NULL,
    document_type text NOT NULL,
    tally_voucher_type text NOT NULL,
    sign_mode text NOT NULL CHECK (sign_mode IN ('charge','reverse')),
    UNIQUE (company_id, platform, document_type)
);

CREATE TABLE documents (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    filename text NOT NULL,
    mime_type text NOT NULL,
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    storage_key text NOT NULL,
    status text NOT NULL CHECK (status IN ('UPLOADED','PROCESSING','VERIFIED','REVIEW','BLOCKED','FAILED')),
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document_hashes (
    document_id uuid PRIMARY KEY REFERENCES documents(id),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    sha256 char(64) NOT NULL,
    UNIQUE (organization_id, company_id, sha256)
);

CREATE TABLE document_pages (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id),
    page_number integer NOT NULL CHECK (page_number > 0),
    width numeric(12,4),
    height numeric(12,4),
    text_storage_key text,
    UNIQUE (document_id, page_number)
);

CREATE TABLE document_format_families (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    name text NOT NULL,
    supplier text,
    document_type text NOT NULL,
    UNIQUE (organization_id, name)
);

CREATE TABLE template_versions (
    id uuid PRIMARY KEY,
    family_id uuid NOT NULL REFERENCES document_format_families(id),
    version integer NOT NULL CHECK (version > 0),
    status text NOT NULL CHECK (status IN ('DRAFT','APPROVED','REJECTED','RETIRED')),
    definition jsonb NOT NULL,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_by uuid REFERENCES users(id),
    approved_at timestamptz,
    UNIQUE (family_id, version)
);

CREATE TABLE template_fields (
    id uuid PRIMARY KEY,
    template_version_id uuid NOT NULL REFERENCES template_versions(id),
    semantic_field text NOT NULL,
    selector jsonb NOT NULL,
    normalization jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE template_samples (
    template_version_id uuid NOT NULL REFERENCES template_versions(id),
    document_id uuid NOT NULL REFERENCES documents(id),
    expected_result jsonb,
    PRIMARY KEY (template_version_id, document_id)
);

CREATE TABLE extraction_jobs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid NOT NULL REFERENCES documents(id),
    job_type text NOT NULL,
    status text NOT NULL CHECK (status IN ('QUEUED','RUNNING','REVIEW','COMPLETED','FAILED','CANCELLED')),
    progress integer NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    error_code text
);

CREATE TABLE extraction_results (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES extraction_jobs(id),
    template_version_id uuid REFERENCES template_versions(id),
    result jsonb NOT NULL,
    confidence numeric(5,4),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE extracted_rows (
    id uuid PRIMARY KEY,
    extraction_result_id uuid NOT NULL REFERENCES extraction_results(id),
    row_number integer NOT NULL,
    values_json jsonb NOT NULL,
    source_reference jsonb,
    UNIQUE (extraction_result_id, row_number)
);

CREATE TABLE validation_results (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid NOT NULL REFERENCES documents(id),
    extraction_result_id uuid REFERENCES extraction_results(id),
    status text NOT NULL CHECK (status IN ('VERIFIED','REVIEW','BLOCKED')),
    calculations jsonb NOT NULL DEFAULT '{}'::jsonb,
    validator_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_issues (
    id uuid PRIMARY KEY,
    validation_result_id uuid NOT NULL REFERENCES validation_results(id),
    code text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('INFO','REVIEW','BLOCKING')),
    message text NOT NULL,
    source_reference jsonb
);

CREATE TABLE bank_transactions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    bank_account_id uuid NOT NULL REFERENCES bank_accounts(id),
    document_id uuid REFERENCES documents(id),
    transaction_date date NOT NULL,
    narration text NOT NULL,
    debit numeric(18,2) NOT NULL DEFAULT 0,
    credit numeric(18,2) NOT NULL DEFAULT 0,
    balance numeric(18,2),
    mapped_ledger text,
    mapping_status text NOT NULL DEFAULT 'UNMAPPED'
);

CREATE TABLE marketplace_documents (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid NOT NULL REFERENCES documents(id),
    platform text NOT NULL,
    supplier text,
    document_type text NOT NULL,
    invoice_number text NOT NULL,
    invoice_date date,
    voucher_type text NOT NULL,
    total_amount numeric(18,2) NOT NULL
);

CREATE TABLE marketplace_lines (
    id uuid PRIMARY KEY,
    marketplace_document_id uuid NOT NULL REFERENCES marketplace_documents(id),
    description text NOT NULL,
    mapped_ledger text,
    taxable numeric(18,2) NOT NULL,
    cgst numeric(18,2) NOT NULL DEFAULT 0,
    sgst numeric(18,2) NOT NULL DEFAULT 0,
    igst numeric(18,2) NOT NULL DEFAULT 0,
    total numeric(18,2) NOT NULL,
    mapping_status text NOT NULL
);

CREATE TABLE review_tasks (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid REFERENCES documents(id),
    status text NOT NULL CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED','REJECTED')),
    reason_code text NOT NULL,
    assigned_to uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE TABLE excel_exports (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid REFERENCES documents(id),
    storage_key text NOT NULL,
    sha256 char(64) NOT NULL,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE xml_exports (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid REFERENCES documents(id),
    voucher_type text NOT NULL,
    storage_key text NOT NULL,
    sha256 char(64) NOT NULL,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_jobs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    extraction_job_id uuid REFERENCES extraction_jobs(id),
    processing_mode text NOT NULL CHECK (processing_mode IN ('LOCAL_ONLY','HYBRID_PRIVATE','FULL_CLOUD_ADMIN_OPT_IN')),
    provider text,
    model text,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_usage (
    id uuid PRIMARY KEY,
    ai_job_id uuid NOT NULL REFERENCES ai_jobs(id),
    usage_date date NOT NULL,
    requests integer NOT NULL DEFAULT 0,
    estimated_usage numeric(18,4),
    actual_usage numeric(18,4),
    quota_state text NOT NULL CHECK (quota_state IN ('NORMAL','WARNING','CRITICAL','LOCAL_ONLY','QUEUE_UNTIL_RESET'))
);

CREATE TABLE audit_logs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid REFERENCES companies(id),
    actor_id uuid NOT NULL REFERENCES users(id),
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    previous_reference text,
    new_reference text,
    document_id uuid REFERENCES documents(id),
    reason text,
    source_context jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_documents_company_created ON documents(company_id, created_at DESC);
CREATE INDEX ix_extraction_jobs_status_created ON extraction_jobs(status, created_at);
CREATE INDEX ix_validation_results_document ON validation_results(document_id, created_at DESC);
CREATE INDEX ix_bank_transactions_account_date ON bank_transactions(bank_account_id, transaction_date);
CREATE INDEX ix_marketplace_documents_company_date ON marketplace_documents(company_id, invoice_date);
CREATE INDEX ix_review_tasks_company_status ON review_tasks(company_id, status, created_at);
CREATE INDEX ix_audit_logs_entity ON audit_logs(organization_id, entity_type, entity_id, occurred_at DESC);
CREATE INDEX ix_ai_usage_date ON ai_usage(usage_date, quota_state);

-- Row-Level Security is intentionally deferred until authenticated session context exists.
COMMIT;
