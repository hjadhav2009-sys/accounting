# PostgreSQL Migration Execution

Phase 2B executed `001_v2_foundation.sql` and `002_phase2_shadow.sql` without
modification against both `business_automation_dev` and
`business_automation_test` on PostgreSQL 18.4. The checksum migration history
then returned an empty applied list on repeat execution, proving migration
idempotency.

Development command:

```powershell
$env:APP_ENV='development'
$env:DATABASE_URL='postgresql://business_automation_app@localhost:5432/business_automation_dev'
python -m v2.backend.app.infrastructure.migration_verifier --migrate-dev
```

The command refuses non-development/test database names and `--execute` remains
a hard cutover refusal. SQLite extraction uses `mode=ro&immutable=1` and hashes
the source before and after every import.
