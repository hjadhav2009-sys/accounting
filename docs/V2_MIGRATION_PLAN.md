# V2 Migration Plan

## Dependency map

```text
Regression fixtures
  → domain contracts/invariants
    → repository interfaces
      → PostgreSQL shadow implementation
        → company/identity authorization
          → job/storage pipeline
            → migrate one parser/export workflow at a time
              → Template runtime and Studio
                → privacy/AI routing
                  → reporting and final legacy retirement
```

## Recommended order

1. **Finish baseline protection.** Install/recover Python, run all Phase 0 tests, obtain sanitized real-layout fixtures, certify live DB schema and counts, and record golden structured outputs.
2. **Extract contracts without behavior changes.** Define document rows, mapping results, vouchers, validation results, and repository protocols around existing code. Keep Streamlit and SQLite active.
3. **Platform foundation.** Create FastAPI health/auth skeleton, Next.js shell, job model, storage interface, audit event model, and CI. Do not add AI.
4. **PostgreSQL shadow store.** Add migrations and repositories; import a copy of SQLite; compare row counts, normalized keys, mapping decisions, and exports. SQLite remains production authority.
5. **Identity and tenant boundaries.** Organizations, companies, memberships, permissions, and tested company isolation; then enable RLS.
6. **Migrate Database Pro.** Dual-read comparison, controlled writes, backups, reversible cutover.
7. **Migrate workflows one at a time.** Prefer PDF-to-Excel, then marketplace, then bank after reconciliation is specified. Each cutover requires golden parity and rollback.
8. **Versioned templates/document representation.** Introduce fingerprints, immutable versions, provenance, and multi-sample tests before visual Studio work.
9. **Template Studio.** Build draft/review/version UX over stable APIs.
10. **Hybrid privacy and AI.** Add deterministic redaction, token vault, quota enforcement, AI draft generation, and fail-closed policies.
11. **Reporting and decommission.** Validate read models, retain export history, then retire legacy paths only after an agreed parallel-run period.

## Migration gates

- No live DB migration without verified backup/restore and reconciliation report.
- No parser replacement without real sanitized golden fixtures and equal-or-better validator results.
- No export path without balanced-voucher and reference-field tests.
- No multi-user release without negative cross-company authorization tests.
- No cloud AI until privacy modes, payload logging policy, quota fail-closed behavior, and administrator controls are tested.

## Phase 1 exact scope

1. Restore a supported Python environment and make Phase 0 tests/compile/import checks pass.
2. Add sanitized golden fixtures for the historical Sujal, marketplace, Flipkart, and bank layouts.
3. Establish Git/CI and verify ignores before the first commit.
4. Introduce domain/repository interfaces around SQLite without changing UI or outputs.
5. Scaffold FastAPI, Next.js, PostgreSQL migrations, storage, job, identity, and audit models behind disabled/non-production entry points.
6. Build a read-only SQLite-to-PostgreSQL migration verifier; do not cut over production data.
