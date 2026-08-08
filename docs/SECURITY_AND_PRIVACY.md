# Security and Privacy Audit

## Scope and assurance

A metadata-only local pattern scan was run across readable non-database files; matched secret values were not printed. No private-key marker, AWS access-key pattern, email address, PAN-shaped identifier, or assigned API-token/password pattern was found. A 12–18 digit account-shaped identifier appears in `data/bank_tally_rules.json` and as a default seed in `shared/database.py`.

Phase 0B later found a project-local Python runtime. The requested Phase 0B check was a targeted staged/source-tree privacy review, not a full formal security scan. No vulnerability claim below relies on runtime deployment exposure.

The final source-tree scan found no assigned API token/password pattern, private-key marker, AWS access key, email, or PAN pattern. Shape-valid GSTINs occur only in explicitly synthetic tests. One account-shaped identifier exists in ignored legacy JSON and another in tracked-source candidate `shared/database.py` as a default seed. There are no source-tree PDFs, spreadsheets, CSVs, XML exports, or logs outside `.venv`; the one production DB is ignored. Git has no commits and no staged files.

## Trust boundaries and assets

The current product is intended to bind to localhost and has no authentication/authorization layer. Browser users can upload sensitive PDFs/statements, edit mappings and amounts, download the raw DB, delete companies, and create accounting exports. Assets are customer documents, bank/account identifiers, GST/business identities, mapping rules, production DB, exports, and Tally integrity. Boundaries are browser→Streamlit, uploaded file→PDF parsers, editable UI→database/export, local filesystem→download, and later local→cloud AI.

## Findings and risks

| Priority | Finding | Evidence/impact | Required control |
|---|---|---|---|
| High if network-exposed; low on strict localhost | No user authentication or authorization | Database Pro exposes raw DB download, mutation, cleanup, and deletion to any UI user | Keep localhost-only now; V2 identity, company authorization, CSRF/session controls, and role-gated destructive actions |
| Medium | Sensitive production data and legacy config live inside the source folder | `business_rules.db` plus JSON with account-shaped data can be accidentally copied/published | Separate data root, encrypt/protect backups, public-release gate, synthetic seed values |
| Medium | Uploaded temporary files are retained | Bank uses `NamedTemporaryFile(delete=False)`; marketplace creates an undeleted temp directory | Job-scoped storage, restrictive permissions, guaranteed cleanup/retention policy |
| Medium | Mutating initialization and silent deduplication | Reads call `init_db`, which normalizes/deduplicates and may discard later conflicting rows | Explicit migrations, backup, dry-run diff, transactional audit |
| Medium | No upload size/page/time limits | PDF parsing of untrusted files can exhaust local resources | Size/page limits, timeouts, isolated worker, MIME/signature checks, decompression limits |
| Low/conditional | Stored regex patterns can consume excessive CPU | Company-configured patterns execute with Python `re` | Authorized editors, regex length/feature policy, timeout-safe engine |
| Low | Dynamic `exec` composes PDF Core | Fixed local file is compiled/executed; compromise of that file becomes code execution | Replace later with normal package import after regression parity |
| Integrity risk | Missing invoice dates default to current date | Marketplace parser can emit plausible wrong accounting metadata | Block export on missing date; require review |
| Integrity risk | Bank ledger selection ignores parsed account text | UI selects first configured bank account | Deterministic account match and ambiguity blocking |

XML fields are escaped. Table-name SQL interpolation is allowlisted in the effective helper. Parameterized queries are used for user values. No external network call or cloud credential handling exists in the current application.

## Privacy design requirements

- Move runtime data outside the source checkout with least-privilege filesystem access.
- Encrypt sensitive storage/backups where appropriate; never log raw account/PAN/contact values.
- Separate operational metadata from payload logs and disable cloud prompt/response retention.
- Use local deterministic tokenization with a company-scoped encrypted mapping vault.
- Apply explicit retention/deletion to originals, extracts, temporary files, exports, and backups.
- Audit every view/download/mutation/approval/override in V2.
- Reverify Cloudflare terms, logging defaults, models, pricing, and quotas against official documentation immediately before implementation; these facts can change.

## Dependency review

Dependencies are broad lower bounds without a lock file or integrity hashes. This makes builds non-reproducible and allows breaking/security changes on reinstall. `lxml` and `python-dateutil` are declared but no current import was found; pdfplumber is used by bank parsing and optional table reading; Pillow is transitive/optional in visible source. Phase 1 should create a reproducible lock, run an advisory audit with network access, and remove dependencies only after import/runtime coverage.

Phase 0B verified all declared packages are installed in `.venv`, and `pip check` reported no broken requirements. Installed versions are recorded in `PHASE_0_EXECUTION_REPORT.md`. No packages were installed or upgraded.

## Dead and duplicate code observations

- The first half of `shared/database.py` is superseded by later definitions.
- `shared/json_store.py`, bank JSON mapping helpers, PDF `read_tables`, and OCR placeholder have no current caller.
- `app.py` and `app_embedded.py` substantially duplicate PDF UI code.
- Legacy JSON rule files are not referenced by the current UI.

These are maintainability and confusion risks, not authorization to delete them. Protect behavior first, then deprecate with telemetry/golden tests.
