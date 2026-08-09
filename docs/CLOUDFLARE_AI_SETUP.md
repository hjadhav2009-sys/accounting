# Cloudflare AI Development Runtime

Phase 5B uses the named development Worker in `cloudflare/ai-worker`:

`https://business-automation-ai-worker-development.business-automation-ai-worker.workers.dev`

The root configuration has `workers_dev = false`; only `env.development` is enabled and
there is no production custom route. The Worker binds directly to Workers AI and a
sharded SQLite Durable Object replay guard. AI Gateway is not used.

Model roles are server-owned:

- `TEXT_TOOL_MODEL` → `@cf/zai-org/glm-4.7-flash`
- `VISION_DOCUMENT_MODEL` → `@cf/google/gemma-4-26b-a4b-it`

Clients cannot choose provider URLs, model IDs, system prompts, schemas, or tools.
FastAPI signs the exact canonical body with `AI_HMAC_SECRET`; the matching backend secret
is loaded from the ignored `CLOUDFLARE_AI_WORKER_HMAC_SECRET_FILE`. Never put the value in
source, frontend configuration, logs, documentation, or `wrangler.jsonc`.

The backend development environment uses:

```text
CLOUDFLARE_AI_WORKER_URL=https://business-automation-ai-worker-development.business-automation-ai-worker.workers.dev
CLOUDFLARE_AI_WORKER_HMAC_SECRET_FILE=<ignored local secret file>
AI_BILLING_MODE=FREE_ONLY
AI_PHASE5_RUNTIME_CERTIFIED=true
```

Set the certification flag only after the live HMAC, replay, text, vision, privacy, DRAFT,
and deterministic-validation checks pass. Raw request/response retention remains off;
logs contain request ID, resolved model role, status, duration, and safe usage metadata.
Provider neuron use is currently unavailable, so application estimates are explicitly
non-authoritative and conservatively accounted.

Useful non-inference checks:

```powershell
npm.cmd test
npm.cmd run check
npx.cmd wrangler deploy --env development --dry-run
npx.cmd wrangler secret list --env development
```

References: [Workers.dev](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/),
[Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/), and
[Workers AI bindings](https://developers.cloudflare.com/workers-ai/configuration/bindings/).
