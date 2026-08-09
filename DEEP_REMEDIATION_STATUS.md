# Deep remediation status

Branch: `audit/deep-remediation`

This is a remediation review checkpoint, not a cutover certificate. Legacy and the authoritative SQLite database remain intact.

| ID | Status | Changed area | Regression evidence | Before | After / remaining risk |
|---|---|---|---|---|---|
| A1 migration company refresh | FIXED | phase6c migration API, company switcher, migration and Masters UI | `test_phase6c` migration/UI contracts | Apply cleared context and Masters could appear empty | Apply result persists, companies refetch, imported company IDs/names/counts display, one-click switch |
| A2 source mapping partition | FIXED | migration reporting/tests | authoritative read-only preview test | Imported ownership was not visible | 51/28/65 mappings are asserted for the three source companies |
| A3 preview/apply binding | FIXED | sqlite migration | preview hash regression | Historical customer hash acted like a product rule | Apply is bound to the hash captured by its preview |
| B1 route authorization | FIXED | API route dependencies and permission matrix | exhaustive OpenAPI matrix; Viewer denial | Sensitive routes had implicit or missing capability gates | Every protected V2 route is catalogued; upload/review/AI/download gates are explicit |
| B2 fail-closed deployment | FIXED | settings, request identity, startup | production configuration regression | Client identity headers could be trusted with auth disabled | Non-development startup rejects insecure auth/session/database/CORS configuration |
| B3 login DoS/throttling | FIXED | passwords and sessions | dummy-hash and live login throttle tests | Unknown users could trigger fresh Argon2 work; throttle keyed mainly by identity | One precomputed dummy hash plus identity and network/global throttles |
| B4 bounded upload | FIXED | document routes | bounded reader regression | Body could be fully read before limit enforcement | Chunked bounded reads, file/batch caps, file-count and rate limits |
| B5 browser headers | FIXED | Next configuration | frontend build and header regression | Backend headers did not protect the Next document | CSP, frame, MIME, referrer and permissions headers on Next responses |
| C1 strict money | FIXED | accounting workflows | strict money regression | Malformed nonblank values became zero | Raw value and structured `MALFORMED_MONEY` block export |
| C2 marketplace validation | FIXED | accounting workflows | marketplace XML/accounting tests | Mapping status could authorize XML without canonical totals | Required total, classification and canonical accounting validation gate XML |
| C3 bank continuity | FIXED | accounting workflows | continuity/debit-credit/narration tests | Only overall closing balance was checked | Canonical bank validator enforces row continuity and row policy |
| C4 taxable partitions | FIXED | validation, repository, migration 021 | identical-line and CGST/SGST tests | Identical bases could collapse or be double-counted | Explicit base partition identity and occurrence pairing preserve bases once |
| D1 anchor geometry | FIXED | Template Rule Engine | two-document anchor leakage test | Anchor extraction could return `sample_value` | Geometric relationships select real neighboring source blocks |
| D2 table boundaries | FIXED | Template Rule Engine/schema | movable boundary regression | Visual boundaries did not control assignment | Bounding-box centers and stored boundaries drive column assignment |
| D3 ignore/region matching | FIXED | Template Rule Engine | ignore and region tests | Intersection confidence dominated; ignore behavior was inconsistent | Containment/overlap/distance scoring and consistent ignore filtering |
| D4 approval validation | FIXED | Template Studio service | profile validator tests | Studio used a lightweight validator path | Canonical accounting validation and profile-required fields gate approval evidence |
| E1 shared matcher/normalization | FIXED | domain mapping module and repositories/imports | all-five-mode matcher tests | Match behavior and normalization differed by path | One matcher implements contains/smart/equals/starts/regex using certified normalization |
| E2 Default Company/RLS | FIXED | PostgreSQL repository | live forced-RLS fallback test | Code attempted cross-company fallback reads | Runtime lookup is company-local; inheritance requires explicit copy/import, never accidental reads |
| F1 persisted quota/status | FIXED | AI API/quota | live PostgreSQL quota tests | Status could report a fresh in-memory ledger | Tenant status uses persisted PostgreSQL quota when configured |
| F2 bounded quota accounting | FIXED | hybrid AI service/Worker | payload-size/version tests | Fixed reservation could underbound a request | Conservative pre-request bound uses payload, output, image and versioned rates |
| F3 local failover | FIXED | providers/service | unhealthy local single-escalation test | Configured was treated as healthy | Real `/health` probe and one policy/quota-bounded HYBRID escalation |
| F4 vision privacy/schema | FIXED | AI API/privacy/Worker | local OCR redaction and vision security tests; Worker 7/7 | Client claim could enable vision and table columns were guessed | Tenant-owned server crop, local OCR redaction, bounded data URL, unknown columns remain unmapped |
| F5 AI IDs/prompts/models | FIXED | AI service/settings | AI orchestrator tests | IDs/prompts/selections/models were weakly bounded | UUID requests, JSON prompt serialization, typed bounded selection, server model allowlist |
| G1 launcher/runtime | FIXED | runtime scripts/env example | PowerShell parse and ownership contract test | Certified llama flags and health polling were absent | Loopback, API key, context/threads/GPU/UI flags and real health polling |
| G2 PID reuse | FIXED | stop script | ownership contract test | Executable equality could authorize a stale Node PID | Executable, creation time, project marker and command hash must all match |
| G3 frontend API/encoding | FIXED | API client and components | frontend production build and mojibake scan | Error/CSRF/correlation behavior was fragmented; strings were corrupt | Typed error client, request IDs, CSRF handling and corrected UTF-8 UI strings |
| G4 page rendering/duplicates | FIXED | document routes/repository, migration 022 | compile/live migration and route tests | Repeated renders were expensive; duplicate attempts left no audit row | Tenant-keyed bounded render cache/rate limit; audit evidence without duplicate source storage |
| G5 unknown format flow | FIXED | native intake/Template Studio draft | PostgreSQL/Tesseract intake tests | Normal route silently relied on reference parsing | Unknown native formats enter REVIEW with a company-scoped V2 draft |
| G6 V2/reference boundary | FIXED | routing, intake and accounting exports/workflows | zero-reference-import regression | Normal V2 product path imported legacy parsers | Product path uses only approved V2 templates; reference parser remains in explicit reference modules |
| V1 live isolated restore | DEFERRED | external runtime credential | restore test is present but skipped | No restore-admin credential is configured in this environment | Must pass before Phase 6 certification or cutover |
| V2 browser migration E2E | DEFERRED | external browser rehearsal | backend/UI contracts and live migration integration pass | No clean browser rehearsal was run during this code-only remediation | Run preview/apply/company-switch/Masters on an isolated test tenant before certification |
| V3 clean-machine launcher | DEFERRED | external machine acceptance | script parse/static ownership and health tests pass | Current machine is not a clean acceptance target | Rehearse start/health/stop on a clean machine before release |

## Validation checkpoint

- Python: 198 V2 tests; PostgreSQL 18 and Tesseract enabled; isolated restore is the only environmental skip.
- Frontend: Next.js production build and TypeScript pass.
- Worker: TypeScript passes; 7/7 Worker runtime tests pass.
- Dependencies: `npm audit` (frontend and Worker) and `pip-audit` report zero known vulnerabilities; `pip check` passes.
- SQLite SHA-256 remains `87E55412BB10C7D953E3F971F45F455E3A7769D179C9DE2D84575BF47616AE5E`.
- No cutover, merge, legacy deletion, SQLite modification, or production release was performed.
