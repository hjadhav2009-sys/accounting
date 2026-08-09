BEGIN;

-- Organization names are the human-facing login realm. Prevent case-only
-- duplicates so an email address can safely exist in more than one tenant.
CREATE UNIQUE INDEX IF NOT EXISTS organizations_login_name_uq
    ON organizations (lower(btrim(name)));

COMMIT;
