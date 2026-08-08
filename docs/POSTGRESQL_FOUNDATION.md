# PostgreSQL Foundation

The certified development target is PostgreSQL **18**. Phase 2B executed both
existing migrations unchanged on PostgreSQL 18.4 x64, proving compatibility for
UUID, JSONB, NUMERIC, timestamps, constraints, indexes, and tenant columns.

The live schema contains 38 tables including migration history, 67 indexes, 114
UUID columns, 18 NUMERIC columns, 22 timestamp columns, 25 organization scopes,
and 20 company scopes. Accounting totals use `numeric(18,2)` and tax rates use
`numeric(9,4)`; Python receives `Decimal`, never binary floating-point.

`docker-compose.postgres.yml` and CI now target `postgres:18-alpine`. Local
credentials remain outside Git in libpq `pgpass.conf`; the ignored `.env`
contains password-free local URLs. PostgreSQL is development/shadow only and no
authoritative mode exists.

The Compose volume targets `/var/lib/postgresql`, matching the PostgreSQL 18+
official image's versioned `PGDATA` layout.
