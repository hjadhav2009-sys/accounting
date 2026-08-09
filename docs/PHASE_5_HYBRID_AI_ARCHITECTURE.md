# Phase 5 Hybrid AI Architecture

Status: **PARTIAL — architecture implemented; inference runtimes not certified**.

## Authority boundary

AI is an advisory document-intelligence component, not a general chatbot. The
only supported flow is:

`Template Studio → FastAPI → HybridAiService → local runtime OR signed AI Worker → structured proposal → deterministic validation → human review`

`HybridAiService` is the exclusive provider gateway. Business code must not call
local or cloud providers directly. A model may propose allowlisted Template
Action API operations; it cannot approve a template, post a voucher, reconcile a
bank entry, change permissions, execute code, fetch arbitrary URLs, or weaken a
validator. Mixed GST buckets remain distinct and deterministic Decimal
accounting remains authoritative.

## Modes

- `LOCAL_ONLY`: never escalates.
- `HYBRID_PRIVATE` (default): local first; sanitized cloud escalation only for a
  recorded capability/health reason.
- `FULL_CLOUD_DOCUMENT_ANALYSIS`: explicit admin-only opt-in.

Privacy modes are `STRICT`, `BALANCED` (default), and `OFF_ADMIN_ONLY`.
`AI_BILLING_MODE=FREE_ONLY` is the default and blocks before the 95% quota gate.

## Result and trust model

Provider JSON is untrusted. Output is constrained to `AiTemplateProposal`,
unknown fields/actions fail closed, explanatory text is HTML escaped, action
payloads are bounded, and every action goes back through Template Studio's
deterministic schema/revision/permission checks. Confidence is only `HIGH`,
`MEDIUM`, or `LOW`; it never substitutes for validation.

Persisted PostgreSQL records include provider accounts/models, quota usage and
reservations, cancellable jobs, proposals, safe audit metadata, approved
correction memory, prompt versions, and a tenant-scoped response cache. Raw
prompts, raw provider responses, reversible privacy maps, and secrets are not
audit fields.

## Current certification

- Hybrid backend policy/privacy/quota/proposal boundary: locally tested.
- Next.js dashboard and restricted assistant: production build passed.
- AI Worker source: generated bindings, typecheck, and local security tests passed.
- Local model inference: unavailable; no model/runtime was downloaded.
- Cloudflare deployment/inference: not attempted without authorization.
- Therefore Phase 5 is not a full runtime pass.
