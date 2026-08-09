from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from decimal import Decimal


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STORAGE_ROOT = REPOSITORY_ROOT / "v2_data" / "documents"
CLOUDFLARE_MODEL_ALLOWLIST = frozenset({
    "@cf/zai-org/glm-4.7-flash",
    "@cf/google/gemma-4-26b-a4b-it",
})


@dataclass(frozen=True)
class Settings:
    app_name: str = "Business Automation Platform"
    api_version: str = "2.0-phase5-hybrid-ai"
    environment: str = "development"
    database_adapter_mode: str = "LEGACY_SQLITE"
    database_url: str = ""
    postgres_url: str = ""
    storage_mode: str = "local"
    storage_root: Path = DEFAULT_STORAGE_ROOT
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_ai_gateway_id: str = ""
    ai_mode: str = "HYBRID_PRIVATE"
    ai_billing_mode: str = "FREE_ONLY"
    ai_privacy_mode: str = "BALANCED"
    local_ai_endpoint: str = "http://127.0.0.1:8080/v1/chat/completions"
    local_ai_model: str = ""
    local_ai_api_key: str = ""
    local_ai_api_key_file: str = ""
    cloudflare_ai_worker_url: str = ""
    cloudflare_ai_worker_hmac_secret: str = ""
    cloudflare_ai_worker_hmac_secret_file: str = ""
    cloudflare_ai_model: str = "@cf/zai-org/glm-4.7-flash"
    cloudflare_ai_vision_model: str = "@cf/google/gemma-4-26b-a4b-it"
    ai_phase5_runtime_certified: bool = False
    ai_daily_free_neurons: int = 10000
    postgres_shadow_enabled: bool = False
    dev_endpoints_enabled: bool = False
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    tesseract_cmd: str = ""
    ocr_max_concurrency: int = 1
    ocr_timeout_seconds: int = 120
    ocr_max_pages: int = 50
    production_auth_enabled: bool = False
    session_cookie_name: str = "ba_session"
    session_cookie_secure: bool = False
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    durable_worker_enabled: bool = True
    durable_worker_poll_seconds: float = 0.5
    durable_stale_seconds: int = 120
    frontend_port: int = 3000
    backend_port: int = 8000
    local_ai_port: int = 8080
    postgres_port: int = 5432
    legacy_port: int = 8501
    bank_reconciliation_tolerance: Decimal = Decimal("0.01")
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 10
    postgres_pool_timeout_seconds: int = 10
    log_max_bytes: int = 5*1024*1024
    log_backup_count: int = 5
    temp_retention_days: int = 7
    source_retention_days: int = 0
    export_retention_days: int = 90
    ai_temp_retention_hours: int = 24

    @classmethod
    def from_environment(cls) -> "Settings":
        key_file = os.getenv("LOCAL_AI_API_KEY_FILE", "").strip()
        local_key = os.getenv("LOCAL_AI_API_KEY", "").strip()
        if not local_key and key_file:
            try: local_key = Path(key_file).read_text(encoding="utf-8").strip()
            except OSError: local_key = ""
        cloud_secret_file = os.getenv("CLOUDFLARE_AI_WORKER_HMAC_SECRET_FILE", "").strip()
        cloud_secret = os.getenv("CLOUDFLARE_AI_WORKER_HMAC_SECRET", "").strip()
        if not cloud_secret and cloud_secret_file:
            try: cloud_secret = Path(cloud_secret_file).read_text(encoding="utf-8").strip()
            except OSError: cloud_secret = ""
        text_model=os.getenv("CLOUDFLARE_AI_MODEL", "@cf/zai-org/glm-4.7-flash").strip()
        vision_model=os.getenv("CLOUDFLARE_AI_VISION_MODEL", "@cf/google/gemma-4-26b-a4b-it").strip()
        if text_model not in CLOUDFLARE_MODEL_ALLOWLIST or vision_model not in CLOUDFLARE_MODEL_ALLOWLIST:
            raise ValueError("configured Cloudflare model is not allowlisted by this release")
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
            ai_mode=os.getenv("AI_MODE", "HYBRID_PRIVATE").strip().upper(),
            ai_billing_mode=os.getenv("AI_BILLING_MODE", "FREE_ONLY").strip().upper(),
            ai_privacy_mode=os.getenv("AI_PRIVACY_MODE", "BALANCED").strip().upper(),
            local_ai_endpoint=os.getenv("LOCAL_AI_ENDPOINT", "http://127.0.0.1:8080/v1/chat/completions").strip(),
            local_ai_model=os.getenv("LOCAL_AI_MODEL", "").strip(),
            local_ai_api_key=local_key,
            local_ai_api_key_file=key_file,
            cloudflare_ai_worker_url=os.getenv("CLOUDFLARE_AI_WORKER_URL", "").strip(),
            cloudflare_ai_worker_hmac_secret=cloud_secret,
            cloudflare_ai_worker_hmac_secret_file=cloud_secret_file,
            cloudflare_ai_model=text_model,
            cloudflare_ai_vision_model=vision_model,
            ai_phase5_runtime_certified=os.getenv("AI_PHASE5_RUNTIME_CERTIFIED", "").strip().lower() in {"1", "true", "yes"},
            ai_daily_free_neurons=max(1, int(os.getenv("AI_DAILY_FREE_NEURONS", "10000"))),
            postgres_shadow_enabled=os.getenv("POSTGRES_SHADOW_ENABLED", "").strip().lower() in {"1", "true", "yes"},
            dev_endpoints_enabled=os.getenv("V2_DEV_ENDPOINTS_ENABLED", "").strip().lower() in {"1", "true", "yes"},
            cors_origins=tuple(origin.strip() for origin in os.getenv(
                "V2_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
            ).split(",") if origin.strip()),
            tesseract_cmd=os.getenv("TESSERACT_CMD", "").strip(),
            ocr_max_concurrency=max(1, min(4, int(os.getenv("OCR_MAX_CONCURRENCY", "1")))),
            ocr_timeout_seconds=max(10, min(600, int(os.getenv("OCR_TIMEOUT_SECONDS", "120")))),
            ocr_max_pages=max(1, min(200, int(os.getenv("OCR_MAX_PAGES", "50")))),
            production_auth_enabled=os.getenv("PRODUCTION_AUTH_ENABLED", "").strip().lower() in {"1", "true", "yes"},
            session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "ba_session").strip() or "ba_session",
            session_cookie_secure=os.getenv("SESSION_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"},
            session_idle_minutes=max(5, min(240, int(os.getenv("SESSION_IDLE_MINUTES", "30")))),
            session_absolute_hours=max(1, min(168, int(os.getenv("SESSION_ABSOLUTE_HOURS", "12")))),
            durable_worker_enabled=os.getenv("DURABLE_WORKER_ENABLED", "true").strip().lower() in {"1", "true", "yes"},
            durable_worker_poll_seconds=max(0.1,min(10.0,float(os.getenv("DURABLE_WORKER_POLL_SECONDS","0.5")))),
            durable_stale_seconds=max(1,min(3600,int(os.getenv("DURABLE_STALE_SECONDS","120")))),
            frontend_port=int(os.getenv("FRONTEND_PORT","3000")),
            backend_port=int(os.getenv("BACKEND_PORT","8000")),
            local_ai_port=int(os.getenv("LOCAL_AI_PORT","8080")),
            postgres_port=int(os.getenv("POSTGRES_PORT","5432") or "5432"),
            legacy_port=int(os.getenv("LEGACY_PORT","8501")),
            bank_reconciliation_tolerance=Decimal(os.getenv("BANK_RECONCILIATION_TOLERANCE","0.01")),
            postgres_pool_min_size=max(0,int(os.getenv("POSTGRES_POOL_MIN_SIZE","1"))),
            postgres_pool_max_size=max(1,int(os.getenv("POSTGRES_POOL_MAX_SIZE","10"))),
            postgres_pool_timeout_seconds=max(1,int(os.getenv("POSTGRES_POOL_TIMEOUT_SECONDS","10"))),
            log_max_bytes=max(1024*1024,int(os.getenv("LOG_MAX_BYTES",str(5*1024*1024)))),
            log_backup_count=max(1,min(20,int(os.getenv("LOG_BACKUP_COUNT","5")))),
            temp_retention_days=max(1,int(os.getenv("TEMP_RETENTION_DAYS","7"))),
            source_retention_days=max(0,int(os.getenv("SOURCE_RETENTION_DAYS","0"))),
            export_retention_days=max(1,int(os.getenv("EXPORT_RETENTION_DAYS","90"))),
            ai_temp_retention_hours=max(1,int(os.getenv("AI_TEMP_RETENTION_HOURS","24"))),
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
            # Public system information never discloses configured inference
            # providers. Authorized administrators use the health endpoint.
            "ai_inference": "disabled",
            "ai_mode": self.ai_mode,
            "ai_billing_mode": self.ai_billing_mode,
            "sqlite_authoritative": "true",
            "postgres_connected": "unknown" if (self.database_url or self.postgres_url) else "false",
            "shadow_mode": "true" if self.postgres_shadow_enabled else "false",
        }

    def validate_runtime_security(self) -> None:
        if self.environment in {"development","test"}: return
        problems=[]
        if not self.production_auth_enabled:problems.append("PRODUCTION_AUTH_ENABLED must be true")
        if not self.session_cookie_secure:problems.append("SESSION_COOKIE_SECURE must be true")
        if not (self.database_url or self.postgres_url):problems.append("PostgreSQL authentication database is required")
        if any(origin=="*" for origin in self.cors_origins):problems.append("wildcard CORS is forbidden")
        if problems:raise RuntimeError("unsafe runtime configuration: "+"; ".join(problems))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()
