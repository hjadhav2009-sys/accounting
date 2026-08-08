from __future__ import annotations

from pathlib import Path
from typing import Any


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def apply_migrations(connection: Any, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply immutable numbered SQL files and record checksums in development PostgreSQL."""
    import hashlib

    applied: list[str] = []
    with connection.cursor() as cursor:
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations(
                version text PRIMARY KEY,
                sha256 char(64) NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )"""
        )
        connection.commit()
        for path in sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql")):
            sql = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            cursor.execute("SELECT sha256 FROM schema_migrations WHERE version=%s", (path.name,))
            existing = cursor.fetchone()
            if existing:
                if existing[0] != digest:
                    raise RuntimeError(f"applied migration changed: {path.name}")
                continue
            cursor.execute(sql, prepare=False)
            cursor.execute("INSERT INTO schema_migrations(version,sha256) VALUES(%s,%s)", (path.name, digest))
            connection.commit()
            applied.append(path.name)
    return applied
