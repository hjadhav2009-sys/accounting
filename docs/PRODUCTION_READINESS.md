# Phase 6 Production Readiness

Status: **PARTIAL**
Assessment date: 2026-08-09
Final production cutover performed: **No**

Phase 5 remains certified at commit `5af36538272aadf961870c7310b053ccabde8521` and tag `v2-phase5-certified`. Phase 6 changes remain local and uncommitted. The legacy application and production SQLite database remain present and authoritative.

## Current certification evidence

| Check | Result |
| --- | --- |
| Python unittest discovery | 197 passed; 0 failed; 1 skipped |
| Python compilation | Passed |
| Python dependency check | Passed; no broken requirements |
| PostgreSQL integration and forced-RLS tests | Passed on local PostgreSQL 18.4 |
| Next.js typecheck and production build | Passed; 20 pages generated |
| Cloudflare Worker typecheck | Passed |
| Cloudflare Worker tests | 7/7 passed |
| Ten-document kill/restart recovery rehearsal | Passed; 10/10 completed after restart, 0 AI calls, 0 exports |
| Local launcher start/health/stop acceptance | Passed; loopback-only and PostgreSQL remained running |
| Secret scan | 370 files; no sensitive filenames or credential values found |
| Production SQLite SHA-256 | `87E55412BB10C7D953E3F971F45F455E3A7769D179C9DE2D84575BF47616AE5E` (unchanged) |

The single skipped test is the destructive isolated PostgreSQL restore certification. It requires a separate restore-administrator connection because the application role correctly has neither `CREATEDB` nor RLS-bypass privileges. The remaining secret-scan heuristic is a GitHub Actions secret-expression placeholder, not a stored credential.

## Completed Phase 6 foundations

- Argon2id authentication, organization-scoped login, server-side opaque sessions, CSRF protection, idle/absolute expiry, revocation, lockout, and secure owner bootstrap.
- Permission-gated user administration and company selection with server-side company authorization.
- Forced PostgreSQL RLS on tenant-bearing V2 tables, transaction-local tenant context, adversarial isolation tests, and a bounded connection pool that clears tenant state before reuse.
- Durable PostgreSQL jobs with persisted source storage, exclusive claims, heartbeat, bounded retry, cancellation, stale recovery, and graceful shutdown.
- Authenticated health/system reporting without cloud inference or secret disclosure.
- Encrypted PostgreSQL/source backup creation and integrity verification, with restore targets restricted to empty `phase6_restore_*` databases.
- Rotating structured JSON logs with sensitive-field redaction and an explicit retention policy that never automatically deletes source originals, exports, or audit evidence.
- Loopback-only Windows start/stop launchers with owned process-tree shutdown. Local start, health, frontend login-page response, and stop behavior passed; PostgreSQL was not stopped.

## Completed V2 application work

- PDF-to-Excel preview and deterministic workbook export using the certified legacy parser/export adapter, with PostgreSQL export history and evidence hashes.
- Invoice Converter routes and production UI, sharing deterministic accounting export controls.
- Marketplace preview, PostgreSQL-controlled mappings and masters, Purchase XML, Debit Note XML, review blocking, and export history.
- Bank statement preview, mappings, masked account display, reconciliation totals, mismatch blocking, and Receipt/Payment XML.
- Masters pages for bank accounts, parties, GST, voucher types, and mappings.
- Mapping workbook export plus validated preview/apply, conflict reporting, and pre-apply backup snapshots; blind apply is prohibited.
- Financial-year persistence and selection based on invoice date, including the April-to-March boundary.
- Expanded production reporting for document, user, AI, and export activity.
- Endpoint-level cross-tenant and cross-company download/export IDOR tests, plus permission-denial coverage.

These features pass synthetic and semantic integration tests. That is not the same as certifying every accounting variant against private production-like fixtures.

## Restart recovery evidence

The isolated rehearsal launched the backend with a temporary storage root and test PostgreSQL data, queued ten documents, terminated only the owned backend process while two jobs were running, restarted it, and waited for recovery.

```text
batch_id: e1a9e600-636c-449d-b4f0-6fd1ceb87637
interrupted state: QUEUED=8, RUNNING=2
final state: COMPLETED=10
documents: 10
AI calls: 0
exports: 0
result: PASS
```

## Backup and restore posture

Backup creation, AES-256-GCM encryption, manifest hashing, and bundle verification pass. Restore remains deliberately unexecuted: the normal application role must not be granted database-creation authority. Runtime certification requires a private `POSTGRES_RESTORE_ADMIN_URL` supplied outside Git, followed by restore into a new isolated `phase6_restore_*` database and application-level verification.

## Accounting certification boundary

The following still require real/private fixtures before they can be called runtime-certified:

- Tax Invoice, Credit Note, Stock Transfer, and Custom Invoice Converter variants.
- PDF-to-Excel golden comparison against the certified legacy output.
- Marketplace Purchase and Debit Note parser-to-XML parity.
- Bank statement parsing, mapping, reconciliation, and XML parity.

No private fixtures are present under `tests/private_fixtures`; only the fixture instructions are available. Existing synthetic tests must not be represented as production accounting parity.

## Phase 6C independent execution and data migration

Three explicit execution modes now exist:

- `LEGACY_REFERENCE` invokes the certified parser only as read-only comparison evidence.
- `V2_NATIVE` uses native extraction, selective OCR capability, fingerprint lookup, approved V2 visual templates, and deterministic validation. Its module has no legacy/reference parser import, reports zero reference calls, and accepts no reference-result hint.
- `COMPARE` executes both paths independently and records field-level `MATCH`, `DIFFERENCE`, `MISSING_LEGACY`, `MISSING_V2`, or `BLOCKED` evidence.

Excel comparison checks schema and normalized values. XML comparison extracts semantic voucher content and ignores harmless formatting and voucher-order differences. A new native fingerprint creates one idempotent DRAFT visual-template shell with its sample. It is never auto-approved, and reference values are not used to repair it.

The Data Migration screen is preview-first and fixes the source path to `data/business_rules.db`. SQLite is opened with `mode=ro`, `immutable=1`, and `query_only`. Deterministic legacy identities support repeat runs, and synthetic PostgreSQL certification proves that two consecutive imports produce no duplicate rows and that identical patterns in two companies resolve to different ledgers.

The real preview produced:

| Source category | Rows |
| --- | ---: |
| Companies | 3 |
| Bank accounts | 4 |
| Party ledgers | 26 |
| Ledger mappings | 144 |
| Voucher rules | 42 |

The source preview used an isolated empty target tenant, reported no blockers, and preserved the certified hash. The authenticated destination-organization preview must still be run because it may reveal collisions with existing PostgreSQL masters. The real import was deliberately not confirmed or applied.

Adversarial testing found that the earlier generic RLS policy-discovery query enforced organization but not company on some tables. Corrective migrations now discover both columns. A live `business_automation_app` test proves Company A and Company B see only their own mapping when pattern text is identical. Durable job payload and scheduling metadata retain forced RLS; the worker enumerates tenant IDs and enters each RLS context before queue access.

## Browser and clean-machine acceptance

Browser E2E could not run because the in-app browser service reported no available browser. The isolated backend and frontend used for the attempted run were stopped and their ports were verified closed. Critical login, company selection, upload, review, export, CSRF, session, and multi-user browser journeys remain required.

The launcher passed local-machine acceptance. A separate clean Windows machine with the documented prerequisites is still required for clean-machine/installer acceptance.

## Migration, rollback, and legacy safety

- Production SQLite remains unchanged and protected.
- PostgreSQL 18 migrations, Decimal/NUMERIC behavior, UUIDs, constraints, repositories, multi-GST persistence, tenant isolation, and RLS pass locally.
- No authority switch, legacy deletion, Streamlit deletion, release push, or final cutover occurred.
- A complete migration rehearsal, restored-database verification, legacy/V2 private-fixture comparison, and executed rollback rehearsal remain required.

Current operational rollback remains: stop V2 with `STOP_BUSINESS_AUTOMATION.bat`, retain PostgreSQL and V2 storage for investigation, start the certified legacy application, verify the production SQLite hash, and do not replay uncertain exports without duplicate review.

## Remaining blockers

1. Provide a private restore-only administrator connection and pass the isolated live restore certification.
2. Supply approved private/sanitized fixtures and pass golden legacy-versus-V2 accounting parity for all required workflows and invoice variants.
3. Confirm the real SQLite preview, apply it once, run a second real preview/import idempotency check, and certify zero unexplained database parity differences.
4. Make a browser backend available and pass critical browser E2E, including session/CSRF and multi-user authorization journeys.
5. Pass launcher acceptance on a clean Windows machine.
6. Execute the complete migration and rollback rehearsal against isolated/restored data.
7. Complete any still-required product surfaces not covered by the present workflow set, including the final duplicate/notification/audit exploration acceptance if those remain Phase 6 cutover criteria.

## Cutover recommendation

Do **not** certify Phase 6 or perform final cutover. Continue in legacy-authoritative/V2-shadow mode. Preserve Streamlit and SQLite, keep `.env.local` ignored, do not push automatically, and require all blockers above to pass before creating a Phase 6 certification tag.
