# PostgreSQL Migration Dry Run

The verifier opens SQLite with `mode=ro&immutable=1` and `PRAGMA query_only=ON`. With no arguments or `--dry-run`, it reports source counts, candidate target counts, duplicate rows, whitespace-normalization conflicts, unsupported rows, and warnings.

```powershell
.\.venv\Scripts\python.exe -m v2.backend.app.infrastructure.migration_verifier --dry-run
```

`--execute` exists only as an explicit refusal and exits with an error in Phase 1. It contains no PostgreSQL connection or insert path.

Certified dry-run counts: companies 3, bank accounts 4, party ledgers 26, ledger mappings 144, voucher rules 42. No duplicates or unsupported rows were found; one normalization conflict was reported in mapping row values. Production DB hashes before and after were identical.
