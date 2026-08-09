from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import threading
from starlette.middleware.base import BaseHTTPMiddleware

from .api.routes import router
from .config import get_settings
from .document_intelligence.repository import DocumentRepository
from .infrastructure.postgres import close_connection_pools,psycopg_connection_factory
from .jobs.durable import DurableJobRepository
from .api.document_routes import process_next_durable_job
from .infrastructure.logging_config import configure_logging
from .config.settings import REPOSITORY_ROOT


settings = get_settings()
settings.validate_runtime_security()
configure_logging(REPOSITORY_ROOT,settings.log_max_bytes,settings.log_backup_count)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="same-origin"
        response.headers["X-Frame-Options"]="DENY"
        response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"]=(
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self' http://127.0.0.1:8000 http://localhost:8000; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        response.headers["Cache-Control"]="no-store" if request.url.path.startswith("/api/v2/auth") else response.headers.get("Cache-Control","private")
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    runtime = get_settings(); url = runtime.postgres_url or runtime.database_url
    stop=threading.Event();worker=None
    if url:
        try:
            DocumentRepository(psycopg_connection_factory(url)).mark_interrupted_batches()
        except Exception:
            logging.getLogger("v2.startup").error("batch recovery check failed")
        if runtime.durable_worker_enabled:
            def run_worker():
                queue=DurableJobRepository(psycopg_connection_factory(url))
                try:queue.recover_stale(runtime.durable_stale_seconds)
                except Exception:logging.getLogger("v2.worker").error("stale job recovery failed")
                while not stop.is_set():
                    try:worked=process_next_durable_job()
                    except Exception:
                        logging.getLogger("v2.worker").error("durable worker iteration failed");worked=False
                    if not worked:stop.wait(runtime.durable_worker_poll_seconds)
            worker=threading.Thread(target=run_worker,name="v2-document-worker",daemon=True);worker.start()
    try:yield
    finally:
        stop.set()
        if worker:worker.join(timeout=10)
        close_connection_pools()


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description="Non-authoritative V2 document-intelligence foundation beside the certified Streamlit baseline.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=settings.production_auth_enabled,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Organization-ID", "X-Company-ID", "X-User-ID", "X-Roles"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(router)
