-- Phase 6 production authentication. Legacy SQLite remains untouched and authoritative.
BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count integer NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0);
ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password boolean NOT NULL DEFAULT false;

CREATE TABLE user_credentials (
    user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    password_hash text NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
    password_version integer NOT NULL DEFAULT 1 CHECK (password_version > 0),
    updated_by uuid REFERENCES users(id),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_sha256 char(64) NOT NULL UNIQUE,
    csrf_sha256 char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    idle_expires_at timestamptz NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revoked_by uuid REFERENCES users(id),
    user_agent_hash char(64),
    CHECK (idle_expires_at <= absolute_expires_at)
);

CREATE INDEX auth_sessions_active_user_idx ON auth_sessions(user_id, absolute_expires_at)
    WHERE revoked_at IS NULL;
CREATE INDEX auth_sessions_token_idx ON auth_sessions(token_sha256);

CREATE TABLE auth_security_events (
    id uuid PRIMARY KEY,
    organization_id uuid REFERENCES organizations(id),
    user_id uuid REFERENCES users(id),
    event_type text NOT NULL CHECK (event_type IN (
        'LOGIN_SUCCEEDED','LOGIN_FAILED','ACCOUNT_LOCKED','LOGOUT','SESSION_REVOKED',
        'PASSWORD_SET','PASSWORD_RESET','USER_CREATED','USER_DISABLED','USER_REACTIVATED','ROLE_CHANGED'
    )),
    remote_address_hash char(64),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auth_security_events_tenant_idx ON auth_security_events(organization_id, created_at DESC);

COMMIT;
