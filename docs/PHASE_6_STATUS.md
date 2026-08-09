# Phase 6 Status

Status: **PARTIAL**
Updated: 2026-08-09

Phase 6 implementation is locally approved but is not certified and has not been cut over.

## Closed in the current working tree

- 197 Python tests passed, 0 failed, 1 restore test skipped.
- PostgreSQL 18.4 integration, forced RLS, pooling, tenant isolation, and IDOR tests passed.
- PDF-to-Excel, Invoice Converter, Marketplace XML, Bank Statement XML, Masters/mapping import, financial years, and expanded reports are implemented.
- Structured rotating logs and retention protections are implemented.
- The real isolated ten-document backend kill/restart rehearsal passed 10/10.
- Next.js typecheck/build and Cloudflare Worker typecheck/tests passed.
- Local loopback launcher start/health/stop acceptance passed without stopping PostgreSQL.
- Production SQLite remains unchanged at SHA-256 `87E55412BB10C7D953E3F971F45F455E3A7769D179C9DE2D84575BF47616AE5E`.
- `.env.local` remains ignored and is not tracked by Git.
- Phase 6C has explicit `LEGACY_REFERENCE`, `V2_NATIVE`, and `COMPARE` modes. Tests prove the native module neither imports the certified parser nor receives its result as a hint.
- Unknown native fingerprints create one idempotent, unapproved V2 visual-template draft and sample for Template Studio. Reference values are not copied; AI actions remain proposals and human approval is mandatory.
- An immutable source preview against an isolated empty target tenant found 3 companies, 4 bank accounts, 26 party ledgers, 144 ledger mappings, and 42 voucher rules. It reported no source duplicates, invalid ownership, or target conflicts and did not change SQLite. The authenticated destination-organization preview and real import were not applied because confirmation must follow preview.
- A company-level RLS discovery defect was found and corrected. A non-superuser application-role test now proves identical pattern text resolves to different company-owned ledgers without cross-company visibility.

## Open certification blockers

1. Live isolated PostgreSQL restore using a separate restore-administrator credential.
2. Confirm/apply the real SQLite migration preview, then run the real second-pass idempotency and database-parity report. Synthetic two-company migration/idempotency/isolation passes.
3. Private-fixture/golden legacy-versus-V2 parity for PDF-to-Excel, every Invoice Converter variant, Marketplace XML, and Bank XML. No real V2-native document has yet reached accounting parity because approved independent V2 templates/private PDFs are unavailable.
4. Critical browser E2E; the current environment exposes no in-app browser backend.
5. Clean-machine Windows launcher acceptance.
6. Full isolated migration and rollback rehearsal.
7. Final acceptance of any remaining cutover surfaces such as duplicate handling, notifications, and audit exploration.

Do not create `v2-phase6-certified`, call Phase 6 `PASS`, delete legacy/Streamlit/SQLite, perform final cutover, or push a production release until every blocker is runtime-certified.

See `docs/PRODUCTION_READINESS.md` for the detailed evidence and boundaries.
