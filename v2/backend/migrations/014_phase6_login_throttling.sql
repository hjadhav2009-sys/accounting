BEGIN;

CREATE TABLE auth_login_throttles (
    key_sha256 char(64) PRIMARY KEY,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    window_started_at timestamptz NOT NULL DEFAULT now(),
    blocked_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auth_login_throttles_cleanup_idx ON auth_login_throttles(updated_at);

COMMIT;
