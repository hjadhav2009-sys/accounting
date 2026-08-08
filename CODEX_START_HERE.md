# Codex Start Here — Non-Breaking V2 Upgrade Rules

## Goal
Evolve the current working Business Automation Suite into a multi-user document/accounting intelligence platform without breaking current accounting logic.

## Preserve first
Before replacing any module, create regression tests from the current engines for:
1. PDF to Excel Core
2. Marketplace XML
3. Bank Statement XML
4. Shared ledger/company mappings
5. GST/tax calculations
6. Voucher numbering fields
7. Existing known PDF formats

## V2 target architecture
- Frontend: React / Next.js
- API: FastAPI
- Database: PostgreSQL
- Local document services: native PDF text/layout + OCR fallback
- AI router: local model first for privacy/masking and simple tasks; optional Cloudflare Workers AI for difficult format understanding
- Validation engine: deterministic and authoritative for accounting numbers
- Template Studio: visual PDF canvas + field/table overlays + chat corrections + versioned templates
- Review Queue: all low-confidence/new-format/accounting-mismatch cases

## Critical accounting rule
AI can suggest extraction or mappings. AI must never be the final authority for totals, GST, debit/credit reconciliation, duplicate detection, or XML export eligibility.

Every export must pass deterministic checks. If reconciliation fails, block export and send the item to Review Queue.

## Privacy rule for cloud AI
Never send the original document by default.
The local privacy layer should create a redacted/minimized representation and keep the token-to-original mapping only on the local machine.
Cloud responses must refer to placeholders, which the local system resolves after return.

## Migration strategy
1. Freeze this baseline.
2. Add automated regression fixtures.
3. Add PostgreSQL behind repository/service interfaces.
4. Migrate one tool at a time.
5. Add document intelligence and Template Studio.
6. Add hybrid local/cloud AI only after deterministic validation is stable.
