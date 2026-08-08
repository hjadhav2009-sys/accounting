# PostgreSQL Backup and Restore Design

Future backups should use version-matched `pg_dump` for schema and encrypted
custom-format data backups, with credentials from a secret manager. Restore into
an isolated database, apply no newer migrations automatically, run integrity and
row-count checks, then perform tenant and accounting parity tests.

Tenant-level export is an application feature, not a substitute for a consistent
database backup; it must preserve relationships and audit provenance. Encrypt
backups in transit and at rest, restrict retention/access, record restore drills,
and verify recovery regularly. No production backup migration occurs in Phase 2.
