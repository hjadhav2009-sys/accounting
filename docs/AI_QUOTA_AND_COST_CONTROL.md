# AI Quota and Cost Control

The default is `AI_BILLING_MODE=FREE_ONLY`. As verified on 2026-08-08, Workers AI
provides 10,000 free Neurons per day and resets at 00:00 UTC. A paid Workers plan
can charge for use over that allocation, so provider-side behavior alone is not
the cost boundary.

The local ledger tracks used, reserved, remaining, tenant allocation, provider
account, and UTC reset metadata. Cloud batches reserve estimated units before a
request and reconcile actual use afterward. Failed/cancelled work releases its
reservation. Thresholds default to:

- below 85%: normal
- 85%: warning
- 93%: critical
- 95%: hard stop

Threshold behavior is tested at 10, 84, 85, 92, 93, 94, 95, and 100 percent.
When quota cannot be verified, cloud inference fails safe or remains queued; paid
fallback is never automatic.

Source: https://developers.cloudflare.com/workers-ai/platform/pricing/

## Phase 5B reset dispatcher

The dispatcher is runtime-tested with an injected UTC clock. A queued job resumes
only after its persisted reset time and only when its document still exists, its
template revision still matches, it was not cancelled, policy still permits cloud
use, and quota is verifiable. PostgreSQL claims the job atomically after rechecking
document and template tenant scope.
