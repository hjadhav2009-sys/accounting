from __future__ import annotations

from uuid import UUID

from ..config.settings import Settings
from ..infrastructure.postgres import PostgresRepositories, psycopg_connection_factory
from ..infrastructure.sqlite_repositories import LegacySQLiteRepositories
from ..services.parity import ParityRecorder, ShadowRepositories


ALLOWED_MODES = {"LEGACY_SQLITE", "POSTGRES_SHADOW", "POSTGRES_TEST"}


def build_repositories(settings: Settings, organization_id: UUID | None = None):
    mode = settings.database_adapter_mode
    if mode not in ALLOWED_MODES:
        raise ValueError(f"unsupported/non-authoritative database mode: {mode}")
    sqlite = LegacySQLiteRepositories()
    if mode == "LEGACY_SQLITE":
        return sqlite
    if organization_id is None:
        raise ValueError("organization_id is required for PostgreSQL modes")
    postgres = PostgresRepositories(
        psycopg_connection_factory(settings.database_url or settings.postgres_url), organization_id
    )
    if mode == "POSTGRES_TEST":
        if settings.environment == "production":
            raise ValueError("POSTGRES_TEST is forbidden in production")
        return postgres
    return ShadowRepositories(sqlite, postgres, ParityRecorder())
