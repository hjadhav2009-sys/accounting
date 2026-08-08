# PostgreSQL Shadow Mode

SQLite remains authoritative. Modes remain `LEGACY_SQLITE`, `POSTGRES_SHADOW`,
and test-only `POSTGRES_TEST`; `POSTGRES_AUTHORITATIVE` is rejected.

The first live import inserted 3/4/26/144/42 source rows. The mandatory second
run inserted zero and updated those same UUIDv5-backed rows. Identity counts and
distinct UUID counts are equal for every category, proving no duplicate or
identity remapping.

The live shadow comparator returned SQLite answers while observing PostgreSQL.
All 248 comparisons matched. Development endpoints refresh aggregate migration
and parity status from PostgreSQL; they are registered only outside production
when explicitly enabled and never return DSNs, credentials, mappings, or account
values.
