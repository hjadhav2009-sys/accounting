# Hybrid AI and Privacy Design

## Processing modes

| Mode | External processing | Default behavior |
|---|---|---|
| Local Only | None | Native extraction/OCR/local tools; unknowns queue for human review |
| Hybrid Private | Minimized/redacted structural representation | Default; local validation and approval remain authoritative |
| Full Cloud Document Analysis | Authorized document/page payload | Administrator opt-in per policy/job; fully audited |

## Deterministic privacy filter

Run local detectors over text and coordinates for bank accounts, PAN, email, phone, GSTIN/other sensitive identifiers, and configurable name/address regions. Replace matches with typed stable tokens such as `<PHONE_001>`. Store token-to-original mappings only in an encrypted local/company-scoped vault with short retention and strict access. Preserve amounts, quantities, rates, HSN, labels, table geometry, and only the context needed for format discovery.

Detection order is important: extract candidates, resolve overlaps, tokenize longest/highest-sensitivity spans, preserve coordinates, and produce a manifest of detector/version/action. False-positive-sensitive entity types such as names/addresses should be configurable. Logs contain token IDs and metadata, never original values.

## AI router and trust rules

Input policy evaluates processing mode, company policy, user authorization, sensitivity result, provider availability, and quota. Output is schema-validated as a candidate template/extraction with confidence and provenance. Reject unknown fields, executable content, instructions to bypass validation, or irreversible actions. Locally resolve placeholders only after response validation.

AI has no direct database mutation, template approval, accounting override, or export capability. All values pass deterministic local accounting checks. Low confidence, failed schemas, provider errors, and invariant failures route to review.

## Cloud controls

- Disable request/response payload retention in AI Gateway; retain only approved operational metadata.
- Never place API tokens in code, browser bundles, document metadata, or logs.
- Use server-side secret storage, egress allowlists, timeouts, size limits, retries with idempotency, and provider response limits.
- Record provider/model/policy version, minimized payload hash, usage, outcome, and reset/remaining quota.
- Fail closed for cost: never automatically enable paid processing; at threshold use local fallback or queue-until-reset.
- Treat provider terms, pricing, free allocation, and logging defaults as externally changing facts that must be reverified before implementation/release.

## Retention and deletion

Define independent retention for original blobs, extracted text, redacted payloads, token vaults, AI metadata, audit events, and backups. Deletion must cover derived objects while preserving legally required immutable audit facts. Do not reuse customer content for model training unless a separate explicit policy and consent flow exists.
