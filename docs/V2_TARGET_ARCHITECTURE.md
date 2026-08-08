# V2 Target Architecture

## Boundaries

```text
Next.js web client
  └── FastAPI API (identity, authorization, jobs, review, exports)
      ├── PostgreSQL repositories + audit/outbox
      ├── object storage abstraction (local/NAS/R2-compatible)
      ├── document pipeline orchestrator
      │   ├── native PDF/layout extraction
      │   ├── OCR fallback
      │   ├── format detector + immutable template versions
      │   ├── deterministic privacy filter
      │   └── optional AI router/quota manager
      ├── deterministic accounting validation engine
      └── legacy adapters (current parsers, Excel, Tally XML)
```

The validation engine, not AI or UI, owns export eligibility. Legacy adapters remain available until fixture-by-fixture parity is proven.

## Recommended directory structure

```text
apps/
  web/                         # Next.js
  api/                         # FastAPI composition and routes
packages/
  domain/                      # document/accounting value objects and invariants
  application/                 # use cases, jobs, review, approvals
  persistence/                 # repository interfaces
  postgres/                    # PostgreSQL implementations/migrations
  storage/                     # local/NAS/object implementations
  document_core/               # normalized document representation
  privacy/                     # detectors, token vault, policies
  templates/                   # family/version/fingerprint runtime
  accounting_validation/      # deterministic calculations
  exports/                     # Excel/Tally adapters
  ai_router/                   # local/cloud policy and quota; no accounting authority
legacy/
  streamlit_baseline/          # initially imports existing modules in place
tests/
  fixtures/synthetic/
  golden/
  contract/
  integration/
  migration/
infra/
  migrations/
  deployment/
docs/
```

## Core model

- Organization → companies → users/memberships/roles.
- Document → immutable blob/version → pages/regions/text/tables.
- Format family → immutable template versions → fingerprints and test corpus.
- Processing job → stages/attempts/provenance/confidence.
- Extracted field/line → source region, normalized value, correction history.
- Validation run → invariant results and export gate.
- Mapping rule → company scope, priority, match method, history.
- Export → deterministic payload/hash/status.
- Audit event → actor, organization, company, action, before/after, correlation ID.

PostgreSQL Row-Level Security is added only after identity/company ownership is modeled and tested. Background jobs must carry explicit organization/company context.

## Document pipeline

Upload → SHA-256 → duplicate decision → native extraction → detection/fingerprint → immutable known template → deterministic extraction → validation. Unknown/changed formats proceed through OCR if needed, local privacy minimization, policy/quota decision, optional AI draft, Template Studio review, deterministic validation, approval, and a new immutable template version.

## Reporting design

Operational events and validated accounting facts feed read models for document, invoice, marketplace, bank, and user dashboards. Reporting must never recompute accounting from unvalidated AI output. Store durations, correction events, template version, validator version, and export outcome for every job.

## Cloudflare quota component

Record calls, estimated/actual neurons, model, byte/token sizes, job, company, user, outcome, remaining allowance, and reset time. States are Normal, Warning, Critical, Local-only fallback, and Queue-until-reset. Paid mode is disabled by default and requires an explicit administrator setting plus audit event. No credentials belong in source or templates.
