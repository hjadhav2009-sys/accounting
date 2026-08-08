from fastapi import APIRouter

from ..config import get_settings
from .schemas import DevelopmentStatusResponse, HealthResponse, SystemInfoResponse
from ..infrastructure.runtime_status import refresh_runtime_status, runtime_status


router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        api_version=settings.api_version,
        database_adapter_mode=settings.database_adapter_mode,
    )


@router.get("/api/v2/system/info", response_model=SystemInfoResponse, tags=["system"])
def system_info() -> SystemInfoResponse:
    settings = get_settings()
    info = settings.public_info()
    status = refresh_runtime_status(settings)
    info["postgres_connected"] = "true" if status.postgres_connected else "false"
    info["shadow_mode"] = "true" if status.shadow_mode else "false"
    return SystemInfoResponse(**info)


if get_settings().environment != "production" and get_settings().dev_endpoints_enabled:
    @router.get("/api/v2/dev/migration/status", response_model=DevelopmentStatusResponse, tags=["development"])
    def migration_status() -> DevelopmentStatusResponse:
        return DevelopmentStatusResponse(**refresh_runtime_status(get_settings()).public())

    @router.get("/api/v2/dev/parity/summary", response_model=DevelopmentStatusResponse, tags=["development"])
    def parity_summary() -> DevelopmentStatusResponse:
        return DevelopmentStatusResponse(**refresh_runtime_status(get_settings()).public())


for prefix, tag in (
    ("/api/v2/organizations", "organizations"),
    ("/api/v2/companies", "companies"),
    ("/api/v2/documents", "documents"),
    ("/api/v2/templates", "templates"),
    ("/api/v2/reviews", "reviews"),
    ("/api/v2/bank", "bank"),
    ("/api/v2/marketplace", "marketplace"),
    ("/api/v2/reports", "reports"),
    ("/api/v2/admin", "admin"),
):
    future_router = APIRouter(prefix=prefix, tags=[tag])
    router.include_router(future_router)
