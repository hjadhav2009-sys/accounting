-- Phase 5 advisory Hybrid AI metadata. PostgreSQL V2 only; SQLite remains untouched.
BEGIN;

CREATE TABLE ai_provider_accounts (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    provider text NOT NULL CHECK (provider IN ('LOCAL','CLOUDFLARE_WORKERS_AI')),
    provider_account_id text NOT NULL DEFAULT '',
    deployment_mode text NOT NULL CHECK (deployment_mode IN ('LOCAL_ONLY','BYOC','VENDOR_HOSTED_FUTURE')),
    billing_mode text NOT NULL DEFAULT 'FREE_ONLY' CHECK (billing_mode IN ('FREE_ONLY','PAID_ALLOWED')),
    daily_limit bigint NOT NULL DEFAULT 10000 CHECK (daily_limit >= 0),
    warning_percent integer NOT NULL DEFAULT 85 CHECK (warning_percent BETWEEN 1 AND 99),
    critical_percent integer NOT NULL DEFAULT 93 CHECK (critical_percent BETWEEN 1 AND 99),
    hard_stop_percent integer NOT NULL DEFAULT 95 CHECK (hard_stop_percent BETWEEN 1 AND 100),
    reset_timezone text NOT NULL DEFAULT 'UTC',
    enabled boolean NOT NULL DEFAULT false,
    health text NOT NULL DEFAULT 'UNVERIFIED' CHECK (health IN ('HEALTHY','DEGRADED','UNAVAILABLE','UNVERIFIED')),
    secret_reference text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(organization_id, provider, provider_account_id),
    CHECK (warning_percent < critical_percent AND critical_percent < hard_stop_percent)
);

CREATE TABLE ai_models (
    id uuid PRIMARY KEY,
    provider_account_id uuid NOT NULL REFERENCES ai_provider_accounts(id) ON DELETE CASCADE,
    model_key text NOT NULL,
    display_name text NOT NULL,
    capabilities text[] NOT NULL DEFAULT '{}',
    context_window integer NOT NULL DEFAULT 0 CHECK (context_window >= 0),
    resource_profile text NOT NULL DEFAULT 'LITE' CHECK (resource_profile IN ('LITE','STANDARD','ADVANCED','CUSTOM')),
    enabled boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'UNVERIFIED' CHECK (status IN ('READY','DEGRADED','UNAVAILABLE','UNVERIFIED','DEPRECATED')),
    last_health_at timestamptz,
    usage_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(provider_account_id, model_key)
);

CREATE TABLE ai_daily_usage (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid REFERENCES companies(id),
    provider_account_id uuid NOT NULL REFERENCES ai_provider_accounts(id),
    usage_date date NOT NULL,
    used_units bigint NOT NULL DEFAULT 0 CHECK (used_units >= 0),
    reserved_units bigint NOT NULL DEFAULT 0 CHECK (reserved_units >= 0),
    input_tokens bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    reset_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(organization_id, company_id, provider_account_id, usage_date)
);

CREATE TABLE ai_quota_reservations (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    provider_account_id uuid NOT NULL REFERENCES ai_provider_accounts(id),
    estimated_units bigint NOT NULL CHECK (estimated_units > 0),
    actual_units bigint CHECK (actual_units >= 0),
    status text NOT NULL CHECK (status IN ('RESERVED','RECONCILED','RELEASED','EXPIRED')),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    reconciled_at timestamptz
);

-- ai_jobs was reserved in Phase 1. Evolve it without discarding early metadata.
ALTER TABLE ai_jobs DROP CONSTRAINT ai_jobs_processing_mode_check;
UPDATE ai_jobs SET processing_mode='FULL_CLOUD_DOCUMENT_ANALYSIS'
    WHERE processing_mode='FULL_CLOUD_ADMIN_OPT_IN';
ALTER TABLE ai_jobs RENAME COLUMN processing_mode TO mode;
ALTER TABLE ai_jobs RENAME COLUMN model TO model_key;
ALTER TABLE ai_jobs ADD CONSTRAINT ai_jobs_mode_check
    CHECK (mode IN ('LOCAL_ONLY','HYBRID_PRIVATE','FULL_CLOUD_DOCUMENT_ANALYSIS'));
ALTER TABLE ai_jobs ADD COLUMN created_by uuid REFERENCES users(id);
ALTER TABLE ai_jobs ADD COLUMN task text NOT NULL DEFAULT 'DOCUMENT_ANALYSIS';
ALTER TABLE ai_jobs ADD COLUMN privacy_mode text NOT NULL DEFAULT 'BALANCED'
    CHECK (privacy_mode IN ('STRICT','BALANCED','OFF_ADMIN_ONLY'));
ALTER TABLE ai_jobs ADD COLUMN route_reason text NOT NULL DEFAULT '';
ALTER TABLE ai_jobs ADD COLUMN sanitized_input_sha256 char(64);
ALTER TABLE ai_jobs ADD COLUMN prompt_version text NOT NULL DEFAULT 'legacy-v1';
ALTER TABLE ai_jobs ADD COLUMN input_tokens integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0);
ALTER TABLE ai_jobs ADD COLUMN output_tokens integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0);
ALTER TABLE ai_jobs ADD COLUMN usage_units integer NOT NULL DEFAULT 0 CHECK (usage_units >= 0);
ALTER TABLE ai_jobs ADD COLUMN cancel_requested boolean NOT NULL DEFAULT false;
ALTER TABLE ai_jobs ADD COLUMN error_code text NOT NULL DEFAULT '';
ALTER TABLE ai_jobs ADD COLUMN started_at timestamptz;
ALTER TABLE ai_jobs ADD COLUMN completed_at timestamptz;

CREATE TABLE ai_template_proposals (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    job_id uuid NOT NULL REFERENCES ai_jobs(id),
    template_version_id uuid REFERENCES template_versions(id),
    summary text NOT NULL,
    proposal jsonb NOT NULL,
    deterministic_validation jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL CHECK (status IN ('PROPOSED','PARTIALLY_APPLIED','APPLIED','REJECTED','EXPIRED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_by uuid REFERENCES users(id),
    reviewed_at timestamptz
);

CREATE TABLE ai_audit_events (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    actor_id uuid NOT NULL REFERENCES users(id),
    job_id uuid REFERENCES ai_jobs(id),
    event_type text NOT NULL,
    intent_summary text NOT NULL DEFAULT '',
    action_summary jsonb NOT NULL DEFAULT '[]'::jsonb,
    provider text NOT NULL DEFAULT '',
    model_key text NOT NULL DEFAULT '',
    usage_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    safe_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_correction_memory (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    template_version_id uuid REFERENCES template_versions(id),
    fingerprint jsonb NOT NULL,
    correction jsonb NOT NULL,
    approved_by uuid NOT NULL REFERENCES users(id),
    approved_at timestamptz NOT NULL DEFAULT now(),
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE ai_prompt_versions (
    id uuid PRIMARY KEY,
    prompt_key text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    template_sha256 char(64) NOT NULL,
    allowed_tasks text[] NOT NULL,
    active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(prompt_key, version)
);

CREATE TABLE ai_response_cache (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    cache_key char(64) NOT NULL,
    model_key text NOT NULL,
    prompt_version text NOT NULL,
    sanitized_input_sha256 char(64) NOT NULL,
    template_revision integer NOT NULL DEFAULT 0,
    task text NOT NULL,
    response jsonb NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(organization_id, company_id, cache_key)
);

CREATE INDEX ai_jobs_tenant_status_idx ON ai_jobs(organization_id,company_id,status,created_at DESC);
CREATE INDEX ai_audit_tenant_idx ON ai_audit_events(organization_id,company_id,created_at DESC);
CREATE INDEX ai_usage_tenant_date_idx ON ai_daily_usage(organization_id,company_id,usage_date DESC);
CREATE INDEX ai_memory_tenant_idx ON ai_correction_memory(organization_id,company_id,active);

COMMIT;
