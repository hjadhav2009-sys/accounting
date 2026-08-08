# Duplicate Detection Design

## Two-layer identity

1. **Byte duplicate:** SHA-256 of the exact uploaded document bytes. This is deterministic and checked before expensive processing.
2. **Accounting duplicate:** normalized tuple of company, supplier, document type, invoice/reference number, date, currency, and amount. The prompt's required tuple is preserved; currency is added to prevent cross-currency collisions.

Store both raw entered/extracted identity and normalized comparison values. A byte match is exact. An accounting-key match is a probable business duplicate and may also identify rescans or visually different copies.

## Records and states

`documents` stores organization/company, hash, size, storage key, uploader, timestamp, and canonical/original relationship. `duplicate_attempts` stores attempted upload, matched document, detection rule, evidence, actor, time, decision, and reason. States: accepted, blocked exact duplicate, review probable duplicate, intentional override, and rejected override.

Use a unique organization/company/hash constraint for race-safe exact detection and a separately indexed normalized accounting key. Compute hash while streaming with file size/type limits; do not trust client hashes.

## UI and overrides

Show original upload, duplicate attempt, uploader, timestamps, matching reason/fields, processing/export status, and safe preview. Only authorized roles may override. Override requires a reason and creates an immutable audit event linking both documents. Never delete or silently replace the original; template/extraction corrections create versions.

## Edge cases and tests

- Same invoice legitimately uploaded to two companies.
- Credit note shares reference with invoice.
- Scanner metadata changes bytes but accounting identity matches.
- Missing/ambiguous invoice number or date routes to review rather than false certainty.
- Concurrent identical uploads produce one canonical record.
- Hashing failure or partial upload never creates a completed document.
- Re-export of an existing accepted document is separately controlled by export idempotency.
