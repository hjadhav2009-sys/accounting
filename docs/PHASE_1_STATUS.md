# Phase 1 Status

## Status: PASS

The certified legacy application remains authoritative and operational. Phase 1 added a removable, non-authoritative V2 foundation beside it. No production parser, accounting, XML, Excel, mapping, or SQLite schema/data behavior was intentionally changed.

## Legacy certification

- Original Phase 0 tests: 21/21 passed.
- Combined suite: 36/36 passed in 5.973 seconds (15 new foundation tests).
- Python compilation: 73 files, 0 errors.
- `pip check`: no broken requirements.
- Legacy Streamlit: started on localhost:8501; health returned HTTP 200/`ok`.
- PDF quantity 420, mixed 3%/18%, marketplace Purchase/Debit Note, bank XML, Excel, XML escaping, and mappings remain protected.
- DB hash before and after: `87E55412BB10C7D953E3F971F45F455E3A7769D179C9DE2D84575BF47616AE5E`.

## V2 foundation

- Framework-independent Decimal domain and native multi-tax-bucket model.
- Application repository protocols and certified SQLite compatibility facade.
- Legacy parser, marketplace, bank, Tally XML, and Excel adapters delegate to existing engines.
- FastAPI 0.141.1 health/system foundation: live smoke PASS on port 8000.
- Next.js 16.3.0/TypeScript shell: typecheck PASS, production build PASS, live HTTP 200 on port 3000, npm audit 0 vulnerabilities.
- PostgreSQL design migration with tenant columns, constraints, indexes, and deferred RLS; not run and not authoritative.
- Immutable SQLite migration planner: dry-run PASS; `--execute` refused with exit 2.
- Local storage path containment, SHA-256 and accounting duplicate signatures.
- In-process job transitions, centralized permissions, append-only development audit store.
- Validation and future OCR/local/cloud/privacy/quota/template-service protocols only; no inference.
- Configuration starts without PostgreSQL or Cloudflare credentials.

## Public repository

**SAFE TO PUSH PUBLICLY: NO.** No files were staged or pushed. Ignore checks passed, and no assigned credentials/private keys were found. The account-shaped default seed in `shared/database.py` requires a separately approved compatibility-safe sanitization before public staging. The ignored production DB and legacy JSON remain locally usable.

## Dependency decisions

Legacy versions were not changed. FastAPI/Pydantic were added inside `.venv`. The initial Next.js 15.5.7 pin surfaced high-severity advisories; it was narrowly replaced with patched stable Next.js 16.3.0, after which npm audit reported zero vulnerabilities. `package-lock.json` is the frontend reproducibility source. Python requirement layers and tested versions are documented; a full hash-locked Python set remains future maintenance.

## Known limitations

- The pre-existing SQLite connection `ResourceWarning` remains documented and unfixed.
- No PostgreSQL server/`psql` exists locally, so migration validation was static plus safety tests rather than execution against PostgreSQL.
- Real private PDF goldens remain unavailable.
- In-memory job/audit implementations are development-only.
- Authentication, RLS, persistent jobs, OCR, Template Studio, AI, and production cutover remain disabled.
- Public Git baseline commit/tag is blocked on source-seed sanitization and explicit user approval.

## Architecture decisions

1. Strangler architecture: V2 calls legacy through adapters; legacy never depends on V2.
2. SQLite and Streamlit remain production authorities.
3. Decimal applies to new domain models only; legacy floats are untouched.
4. UUID-compatible public IDs and organization/company scope are designed from the start.
5. PostgreSQL migration files and verifier have no enabled write/cutover path.
6. Documents stay in storage; PostgreSQL stores metadata and keys.
7. AI/OCR/cloud are protocol boundaries with no credentials or execution.
8. Green/yellow/red language is VERIFIED/REVIEW/BLOCKED across the frontend and API contracts.

## Phase 2 recommendation

Phase 2 should remain a shadow PostgreSQL migration phase: provision a development-only database, validate migration SQL, implement PostgreSQL repositories behind current protocols, compare them read-only against SQLite, add tenant-isolation tests, and keep SQLite authoritative until explicit cutover approval. Do not add AI, OCR, or Template Studio in that phase.
