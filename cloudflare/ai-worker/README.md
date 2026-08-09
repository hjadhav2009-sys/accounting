# Phase 5 AI Worker

This Worker is the only permitted Cloudflare Workers AI boundary. It accepts a
small signed schema, rejects arbitrary prompts/models/tools/URLs, requests
structured output, revalidates the result, and logs safe metadata only.

Only the named `development` environment may be deployed for Phase 5B. Configure
`AI_HMAC_SECRET` with `wrangler secret put --env development`; never place it in
this repository. The root configuration keeps `workers_dev` disabled. The
backend must use the exact `/v1/template-proposal` HTTPS URL and the matching
server-side secret.

The default system policy is `AI_BILLING_MODE=FREE_ONLY`; deployment does not
authorize paid usage. Provider token usage and provider-reported neurons remain
distinct from the conservatively over-reserved application estimate.
