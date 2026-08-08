# CI Design

`.github/workflows/ci.yml` uses synthetic fixtures and a disposable PostgreSQL
18 service. It runs Python compilation, the full unittest suite (including real
PostgreSQL migration/integration tests), `pip check`, immutable migration dry
run, frontend type checking/build, and a tracked-file privacy gate.

CI never requires the ignored production SQLite database or private PDFs. The
workflow creates a minimal synthetic legacy database for dry-run verification.
