# Phase 5B Cloudflare Runtime Certification

Certification date: 2026-08-09

Scope: development runtime, synthetic data, FREE_ONLY

Result: **PASS**

## Cloudflare boundary

- Wrangler 4.120.0 authenticated by OAuth to the intended account.
- Development Worker deployed; latest certified code version:
  `67e56b7d-a87e-469e-b3c8-f1d6d5d3fb65`.
- `AI_HMAC_SECRET` exists in Cloudflare secret storage; its value was never captured.
- Missing, incorrect, stale, and tampered signatures returned 401.
- An exact signed replay returned 409 through the Durable Object replay guard.
- Arbitrary model and SQL/shell task contracts returned 422; an oversized body returned 413.
- No custom production route, paid fallback, credit purchase, or billing change was made.

## Live models and usage

- GLM text request: HTTP 200; structured proposal; 143 input tokens, 339 output tokens;
  conservative application estimate 28 neurons; provider-reported neurons unavailable.
- Gemma sanitized-image request: HTTP 200; structured result; 390 input tokens,
  271 output tokens; conservative application estimate 25 neurons; provider-reported
  neurons unavailable.
- One cloud proposal passed strict validation, created only a PostgreSQL DRAFT revision,
  and produced a VERIFIED deterministic preview with human approval still required.
- Two earlier Gemma schema experiments returned controlled invalid-model-output errors.
  Their historical provider use is unknown because the previous response contract did not
  expose it. The corrected code now accounts known estimates and charges the full reserved
  amount when failure usage is ambiguous.

## Privacy and local-first route

- Synthetic image contained name, phone, email, account-shaped value, PAN-shaped value,
  and UPI-shaped value. Six opaque masks were burned into a metadata-free raster PNG.
- Independent Tesseract OCR recovered zero private values; the restoration map was not
  embedded or transmitted. Sanitized image SHA-256:
  `1b4701ccbc25a98d2af4ef91a2a27c551309b0be652977836057c6505cac2d31`.
- Local Qwen benchmark: bank, marketplace, and correction cases SUFFICIENT; simple invoice,
  mixed GST, and unknown-format anchor NEEDS_CLOUD. All 6 results were schema-valid.
- Local endpoint is authenticated, Web UI disabled, CPU-only, and bound to `127.0.0.1:8080`.

## Regression and integrity

- Python: 161/161 passed.
- Worker: 7/7 passed; TypeScript, zero-vulnerability audit, and Wrangler dry-run passed.
- Next.js: typecheck and production build passed.
- Python compile and `pip check`: passed.
- PostgreSQL 18, FastAPI, Tesseract 5.4.0, Template Studio, privacy, quota/reset,
  prompt-injection, tenant isolation, mixed GST, bank, and legacy regressions passed.
- Git audit: zero tracked sensitive candidates, zero staged files, zero tracked secret
  signature matches. Runtime secrets, GGUF, `.env`, and production SQLite are ignored.
- Production SQLite before/after SHA-256:
  `87E55412BB10C7D953E3F971F45F455E3A7769D179C9DE2D84575BF47616AE5E`.

Phase 5 Hybrid AI is runtime-certified. Do not start Phase 6 automatically.
