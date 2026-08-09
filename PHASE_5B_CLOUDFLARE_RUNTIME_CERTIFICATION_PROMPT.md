# Codex Prompt — Phase 5B Cloudflare Runtime Certification

This repository copy preserves the operational Phase 5B runbook supplied for the
2026-08-09 certification. Its objective is to certify the real development-only
Cloudflare half while preserving the certified local llama.cpp/Qwen route.

Hard boundaries: do not start Phase 6; do not modify production SQLite or certified
accounting/GST/XML/Excel behavior; use synthetic/sanitized inputs only; do not expose or
commit credentials, secrets, private documents, raw cloud payloads, restoration maps, or
GGUF files; do not enable paid AI or change billing. Known formats remain deterministic
with zero AI. Unknown formats try local AI first, and cloud escalation requires a recorded
reason plus FREE_ONLY quota approval. AI can propose only allowlisted Template Actions to
a DRAFT. Deterministic validation and human approval remain mandatory.

The certification covers Wrangler identity, Worker tests/typecheck, development deploy,
HMAC/timestamp/body-hash/replay enforcement, fixed model roles, payload limits, privacy
logging, irreversible image redaction, payload preview, live GLM text and Gemma vision
structured requests, local-first routing, quota thresholds and reset queue, unknown-format
and format-variation DRAFTs, bounded multi-PDF refinement, scoped correction memory,
assistant safety, prompt injection, tenant isolation, mixed GST, bank reconciliation,
full regression, repository secret audit, network binding, and immutable SQLite hash.

The detailed executed evidence and final values are recorded in
`docs/PHASE_5B_CLOUDFLARE_RUNTIME_CERTIFICATION.md`.
