# Phase 0 Status

## Status: PASS

Architecture discovery, database/parser/accounting/XML/Excel/template documentation, V2 planning, privacy review, repository-safety hardening, and runtime certification are complete. Final execution passed 21/21 tests, 42 Python files compiled, required imports succeeded, live SQLite metadata was inspected immutably, and the production DB SHA-256 remained `87E55412BB10C7D953E3F971F45F455E3A7769D179C9DE2D84575BF47616AE5E`.

The runtime is `.venv/Scripts/python.exe` (Python 3.14.3); PATH-level `python` and `py` remain unavailable. SQLite 3.50.4 was accessed through Python in immutable read-only mode, so no standalone CLI was required. The private historical PDF fixture set remains absent, so claims based on those PDFs remain historical rather than newly reproduced.

## Deliverables completed

- Repository/module/runtime flow and preservation boundaries.
- Code-derived six-table SQLite model, indexes, access map, normalization, cache, backup/import/repair behavior, risks, and PostgreSQL mapping.
- Parser format matrix, detection/call/export paths, assumptions, and weaknesses.
- Deterministic accounting and export invariants.
- Twenty-one passing synthetic unit/parser/database/marketplace/bank/XML/integration regression tests.
- Duplicate detection, hybrid privacy/AI, quota, Template Studio, reporting/platform architecture, dependency map, and migration order.
- Privacy/secret metadata scan and public-repository checklist.
- Stronger `.gitignore` and empty-value `.env.example`.

## Remaining non-blocking issues

- Git has no baseline commit and all files are currently untracked; nothing is staged or pushed.
- PATH-level Python tooling is unavailable; use the project interpreter directly.
- `shared/database.py` has duplicate old/effective implementations.
- Initialization mutates production data by seeding/normalizing/deduplicating.
- No foreign keys, auth, roles, tenant boundary, duplicate control, or bank reconciliation.
- OCR is a stub; template JSON does not drive parsing or preserve versions.
- Missing marketplace dates default to today; bank export selects the first account.
- Uploaded temp files are not cleaned up.
- SQLite connections are not explicitly closed and emit `ResourceWarning`; see `PHASE_0_DISCOVERED_DEFECTS.md`.
- Source contains mojibake currency/arrow characters.
- Legacy local JSON and historical reports contain sensitive/business-shaped identifiers.

## Required gate before Phase 1 implementation

1. Curate the first Git baseline commit: do not stage ignored production data/reports, and review the account-shaped default seed before any public push.
2. Preferably add sanitized real-layout samples for Sujal, both Flipkart stock-transfer layouts, marketplace families, and bank inputs as coverage grows.
3. Run a dependency advisory scan and full formal security scan before public deployment.
4. Preserve the certified DB hash and test suite throughout Phase 1.

Baseline is certified. Phase 1 may begin.
