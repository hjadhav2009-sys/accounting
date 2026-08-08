-- Phase 3 document-intelligence persistence. PostgreSQL V2 only; no PDF blobs.
BEGIN;

ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check CHECK (status IN (
    'UPLOADED','REGISTERED','DUPLICATE','EXTRACTING','OCR_REQUIRED','EXTRACTED',
    'VALIDATING','VERIFIED','REVIEW','BLOCKED','FAILED','ARCHIVED'
));
-- Keep the Phase 1 filename column for backward-compatible shadow reads.
ALTER TABLE documents ADD COLUMN original_filename text NOT NULL DEFAULT '';
ALTER TABLE documents ADD COLUMN safe_filename text NOT NULL DEFAULT 'document.pdf';
ALTER TABLE documents ADD COLUMN page_count integer NOT NULL DEFAULT 0 CHECK (page_count >= 0);
ALTER TABLE documents ADD COLUMN duplicate_of_document_id uuid REFERENCES documents(id);
ALTER TABLE documents ADD COLUMN document_type text NOT NULL DEFAULT '';
ALTER TABLE documents ADD COLUMN supplier text NOT NULL DEFAULT '';
ALTER TABLE documents ADD COLUMN invoice_number text NOT NULL DEFAULT '';
ALTER TABLE documents ADD COLUMN invoice_date date;
ALTER TABLE documents ADD COLUMN total_amount numeric(18,2);
ALTER TABLE documents ADD COLUMN extraction_method text CHECK (extraction_method IN ('NATIVE_TEXT','LEGACY_PARSER','LOCAL_OCR'));
ALTER TABLE documents ADD COLUMN quality_status text CHECK (quality_status IN ('GOOD','DEGRADED','OCR_REQUIRED'));
ALTER TABLE documents ADD COLUMN error_code text;
ALTER TABLE documents ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

CREATE TABLE document_batches (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    created_by uuid NOT NULL REFERENCES users(id),
    total integer NOT NULL CHECK (total >= 0),
    processed integer NOT NULL DEFAULT 0 CHECK (processed >= 0),
    verified integer NOT NULL DEFAULT 0 CHECK (verified >= 0),
    review integer NOT NULL DEFAULT 0 CHECK (review >= 0),
    blocked integer NOT NULL DEFAULT 0 CHECK (blocked >= 0),
    duplicate integer NOT NULL DEFAULT 0 CHECK (duplicate >= 0),
    failed integer NOT NULL DEFAULT 0 CHECK (failed >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
ALTER TABLE documents ADD COLUMN batch_id uuid REFERENCES document_batches(id);

CREATE TABLE document_extractions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    method text NOT NULL CHECK (method IN ('NATIVE_TEXT','LEGACY_PARSER','LOCAL_OCR')),
    quality_status text NOT NULL CHECK (quality_status IN ('GOOD','DEGRADED','OCR_REQUIRED')),
    normalized_result jsonb NOT NULL,
    extractor_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document_detected_fields (
    id uuid PRIMARY KEY,
    extraction_id uuid NOT NULL REFERENCES document_extractions(id) ON DELETE CASCADE,
    field_name text NOT NULL,
    value_json jsonb NOT NULL,
    confidence numeric(5,4),
    source_reference jsonb,
    original_token text NOT NULL DEFAULT '',
    normalization text NOT NULL DEFAULT ''
);

CREATE TABLE format_fingerprints (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    family_id uuid REFERENCES document_format_families(id),
    signature char(64) NOT NULL,
    features jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, document_id)
);

CREATE TABLE document_processing_metrics (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    stage text NOT NULL,
    duration_ms integer NOT NULL CHECK (duration_ms >= 0),
    page_count integer NOT NULL DEFAULT 0 CHECK (page_count >= 0),
    method text,
    outcome text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE accounting_duplicate_signatures (
    document_id uuid PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    document_type text NOT NULL,
    supplier_token text NOT NULL,
    invoice_number_token text NOT NULL,
    invoice_date date,
    total_amount numeric(18,2),
    signature char(64) NOT NULL,
    UNIQUE (organization_id, company_id, signature)
);

ALTER TABLE review_tasks ADD COLUMN severity text NOT NULL DEFAULT 'REVIEW' CHECK (severity IN ('INFO','REVIEW','BLOCKING'));
ALTER TABLE review_tasks ADD COLUMN detail jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE review_tasks ADD COLUMN resolution_note text;
ALTER TABLE review_tasks ADD COLUMN resolved_by uuid REFERENCES users(id);

ALTER TABLE template_versions DROP CONSTRAINT template_versions_status_check;
ALTER TABLE template_versions ADD CONSTRAINT template_versions_status_check CHECK (status IN (
    'DRAFT','TESTING','APPROVED','DEPRECATED','REJECTED','RETIRED'
));

CREATE INDEX ix_documents_tenant_status_created ON documents(organization_id, company_id, status, created_at DESC);
CREATE INDEX ix_documents_batch ON documents(batch_id, created_at);
CREATE INDEX ix_document_extractions_document ON document_extractions(document_id, created_at DESC);
CREATE INDEX ix_document_fields_extraction_name ON document_detected_fields(extraction_id, field_name);
CREATE INDEX ix_fingerprints_signature ON format_fingerprints(organization_id, signature);
CREATE INDEX ix_metrics_tenant_created ON document_processing_metrics(organization_id, company_id, created_at DESC);
CREATE INDEX ix_accounting_duplicate_lookup ON accounting_duplicate_signatures(organization_id, company_id, signature);

COMMIT;
