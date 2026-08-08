# Document intake pipeline

1. Validate filename, extension, MIME, magic bytes, non-empty content, and size.
2. Compute tenant/company-scoped SHA-256 duplicate lookup before storage.
3. Store bytes under an opaque tenant/document key and register metadata.
4. Extract native pages and assess quality.
5. Persist pages/fingerprint; invoke page-level local OCR only when required.
6. Route approved legacy formats or send unknown/uncertain evidence to review.
7. Run accounting duplicate detection after sufficient fields exist.
8. Run deterministic validators and persist VERIFIED/REVIEW/BLOCKED.

Batch API limits input to 50 files and catches each file independently.
