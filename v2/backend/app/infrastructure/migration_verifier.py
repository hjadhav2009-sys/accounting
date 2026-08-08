from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SQLITE = REPOSITORY_ROOT / "data" / "business_rules.db"
SOURCE_TABLES = ("companies", "bank_accounts", "party_ledgers", "ledger_mappings", "voucher_rules")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def inspect_sqlite(path: str | Path = DEFAULT_SQLITE) -> dict[str, Any]:
    source = Path(path).resolve()
    before = hashlib.sha256(source.read_bytes()).hexdigest().upper()
    connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    report: dict[str, Any] = {
        "mode": "dry-run",
        "source": "sqlite-read-only",
        "target": "postgresql-disabled",
        "tables": {},
        "warnings": [],
        "sha256_before": before,
    }
    for table in SOURCE_TABLES:
        if table not in existing:
            report["tables"][table] = {"source_count": 0, "candidate_target_count": 0, "duplicates": 0, "normalization_conflicts": 0, "unsupported_rows": 0}
            report["warnings"].append(f"missing source table: {table}")
            continue
        rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
        normalized = [tuple(normalize_text(value).casefold() for value in row.values()) for row in rows]
        duplicates = len(normalized) - len(set(normalized))
        normalization_conflicts = sum(
            1 for row in rows for value in row.values()
            if isinstance(value, str) and value != normalize_text(value)
        )
        report["tables"][table] = {
            "source_count": len(rows),
            "candidate_target_count": len(rows) - duplicates,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "duplicates": duplicates,
            "normalization_conflicts": normalization_conflicts,
            "invalid_rows": 0,
            "warnings": [],
        }
    connection.close()
    report["sha256_after"] = hashlib.sha256(source.read_bytes()).hexdigest().upper()
    if report["sha256_before"] != report["sha256_after"]:
        raise RuntimeError("SQLite changed during read-only inspection")
    return report


def _development_database_url() -> str:
    value = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""
    environment = os.getenv("APP_ENV", "").strip().lower()
    db_name = value.rsplit("/", 1)[-1].split("?", 1)[0].lower()
    if environment not in {"development", "test"}:
        raise RuntimeError("APP_ENV must explicitly be development or test")
    if not any(marker in db_name for marker in ("_dev", "_test", "development", "test")):
        raise RuntimeError("target PostgreSQL database name must be visibly development/test scoped")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only audit or development-only PostgreSQL shadow import.")
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE)
    parser.add_argument("--dry-run", action="store_true", help="Explicitly select the default read-only mode.")
    parser.add_argument("--migrate-dev", action="store_true", help="Apply migrations only to a visibly named development/test PostgreSQL DB.")
    parser.add_argument("--shadow-import", action="store_true", help="Import immutable SQLite rows into development PostgreSQL.")
    parser.add_argument("--organization-id", help="Required stable tenant UUID for --shadow-import.")
    parser.add_argument("--execute", action="store_true", help="Forbidden production/cutover command retained as a hard stop.")
    args = parser.parse_args()
    if args.execute:
        parser.error("--execute is forbidden; PostgreSQL cutover is not authorized")
    if args.migrate_dev or args.shadow_import:
        from uuid import UUID
        from .postgres_migrations import apply_migrations
        from .shadow_migration import ShadowImporter
        from .postgres import psycopg_connection_factory

        url = _development_database_url()
        connection = psycopg_connection_factory(url)()
        try:
            applied = apply_migrations(connection)
            if args.shadow_import:
                if not args.organization_id:
                    parser.error("--organization-id is required for --shadow-import")
                report = ShadowImporter(connection, UUID(args.organization_id)).import_sqlite(args.sqlite)
                report["migrations_applied"] = applied
            else:
                report = {"mode": "migrate-dev", "migrations_applied": applied}
        finally:
            connection.close()
        print(json.dumps(report, indent=2, default=str))
        return 0
    print(json.dumps(inspect_sqlite(args.sqlite), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
