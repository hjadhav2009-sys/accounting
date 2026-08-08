from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..config.settings import Settings


@dataclass
class DevelopmentRuntimeStatus:
    postgres_connected: bool = False
    shadow_mode: bool = False
    last_migration_run: datetime | None = None
    parity_comparisons: int = 0
    parity_mismatches: int = 0
    normalization_conflicts: int = 0

    def public(self) -> dict:
        return {
            "sqlite_authoritative": True,
            "postgres_connected": self.postgres_connected,
            "shadow_mode": self.shadow_mode,
            "last_migration_run": self.last_migration_run,
            "parity_comparisons": self.parity_comparisons,
            "parity_mismatches": self.parity_mismatches,
            "normalization_conflicts": self.normalization_conflicts,
        }


runtime_status = DevelopmentRuntimeStatus()


def refresh_runtime_status(settings: Settings) -> DevelopmentRuntimeStatus:
    """Refresh safe aggregate health from PostgreSQL without exposing its DSN."""
    url = settings.database_url or settings.postgres_url
    runtime_status.shadow_mode = settings.postgres_shadow_enabled
    if not url:
        runtime_status.postgres_connected = False
        return runtime_status
    try:
        from .postgres import psycopg_connection_factory

        connection = psycopg_connection_factory(url)()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT max(applied_at) FROM schema_migrations")
                runtime_status.last_migration_run = cursor.fetchone()[0]
                cursor.execute("SELECT count(*), count(*) FILTER (WHERE result <> 'MATCH'), count(*) FILTER (WHERE result='NORMALIZATION_DIFFERENCE') FROM parity_observations")
                comparisons, mismatches, normalizations = cursor.fetchone()
                runtime_status.parity_comparisons = comparisons
                runtime_status.parity_mismatches = mismatches
                runtime_status.normalization_conflicts = normalizations
            runtime_status.postgres_connected = True
        finally:
            connection.close()
    except Exception:
        runtime_status.postgres_connected = False
    return runtime_status
