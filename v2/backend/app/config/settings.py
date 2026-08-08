from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STORAGE_ROOT = REPOSITORY_ROOT / "v2_data" / "documents"


@dataclass(frozen=True)
class Settings:
    app_name: str = "Business Automation Platform"
    api_version: str = "2.0-foundation"
    environment: str = "development"
    database_adapter_mode: str = "LEGACY_SQLITE"
    database_url: str = ""
    postgres_url: str = ""
    storage_mode: str = "local"
    storage_root: Path = DEFAULT_STORAGE_ROOT
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_ai_gateway_id: str = ""
    postgres_shadow_enabled: bool = False
    dev_endpoints_enabled: bool = False

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            environment=os.getenv("APP_ENV", "development").strip().lower(),
            database_adapter_mode=os.getenv("DATABASE_ADAPTER_MODE", "LEGACY_SQLITE").strip().upper(),
            database_url=os.getenv("DATABASE_URL", ""),
            postgres_url=os.getenv("POSTGRES_URL", ""),
            storage_mode=os.getenv("STORAGE_MODE", "local"),
            storage_root=Path(os.getenv("STORAGE_ROOT") or DEFAULT_STORAGE_ROOT),
            cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
            cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", ""),
            cloudflare_ai_gateway_id=os.getenv("CLOUDFLARE_AI_GATEWAY_ID", ""),
            postgres_shadow_enabled=os.getenv("POSTGRES_SHADOW_ENABLED", "").strip().lower() in {"1", "true", "yes"},
            dev_endpoints_enabled=os.getenv("V2_DEV_ENDPOINTS_ENABLED", "").strip().lower() in {"1", "true", "yes"},
        )

    def public_info(self) -> dict[str, str]:
        return {
            "application": self.app_name,
            "api_version": self.api_version,
            "environment": self.environment,
            "database_adapter_mode": self.database_adapter_mode,
            "storage_mode": self.storage_mode,
            "legacy_authority": "enabled",
            "postgres_cutover": "disabled",
            "ai_inference": "disabled",
            "sqlite_authoritative": "true",
            "postgres_connected": "unknown" if (self.database_url or self.postgres_url) else "false",
            "shadow_mode": "true" if self.postgres_shadow_enabled else "false",
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()
