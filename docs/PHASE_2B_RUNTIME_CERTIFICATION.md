# Phase 2B Runtime Certification

## Runtime

- Server/client: PostgreSQL 18.4 x64 for Windows
- Host/port: localhost:5432
- Service: `postgresql-x64-18`, running automatically
- Development DB: `business_automation_dev`
- Test DB: `business_automation_test`
- Application role: `business_automation_app`
- Credential storage: user-local libpq password file, outside repository

## Migration metadata

Both numbered migrations executed in both databases with zero errors. Live
development metadata reports 38 tables, 67 indexes, 38 primary keys, 80 foreign
keys, 18 unique constraints, 255 checks, 114 UUID columns, 18 NUMERIC columns,
22 timestamp columns, 25 `organization_id` columns, and 20 `company_id` columns.

## Import and identity

Run 1 inserted 3 companies, 4 bank accounts, 26 party ledgers, 144 ledger
mappings, and 42 voucher rules. Run 2 inserted zero and updated the same counts.
All categories have equal identity-row and distinct-UUID counts. Duplicates,
invalid rows, skipped rows, and relationship remaps are zero. SQLite hashes
before/after both runs were identical to the certified hash.

## Runtime tests

60/60 tests passed in 13.332 seconds with zero required skips. PostgreSQL tests
cover migration execution, repeat import, repository parity, tenant-identical
mapping isolation, exact multi-GST retrieval, NUMERIC/Decimal values, same-tenant
and cross-tenant document hashes, repository-reloaded job state transitions,
append-oriented audit reload, document/invoice/bank/marketplace reporting, and a
candidate RLS policy inside a rolled-back test transaction.

FastAPI live health reported PostgreSQL connected and shadow mode enabled with
248 parity comparisons and zero mismatches. Next.js and Streamlit smokes passed.
Public safety remained YES and no files were staged or pushed.
