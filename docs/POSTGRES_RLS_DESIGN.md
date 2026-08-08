# PostgreSQL RLS Design

Migration 002 creates candidate policies based on
`current_setting('app.organization_id', true)::uuid` for representative tenant
tables. It deliberately does **not** enable RLS. Development validation must set
tenant context with `SET LOCAL app.organization_id = '<uuid>'` inside each
transaction before RLS can be enabled in a later phase.

Application authorization remains mandatory. Normal users receive explicit
company access; administrators are still organization-bound. A narrowly held
migration/service role may bypass RLS only for audited shadow import. Background
jobs must restore the job's organization/company context. Production enablement
requires coverage for every tenant root and parent-inherited table plus negative
cross-tenant tests.

Phase 2B safely enabled and forced the candidate `ledger_mappings` policy only
inside a PostgreSQL test transaction. With `app.organization_id` set, one tenant
could see exactly its own synthetic identical-pattern row. The transaction was
rolled back, restoring RLS to disabled. Production RLS remains disabled.
