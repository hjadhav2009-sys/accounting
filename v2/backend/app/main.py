from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from .api.routes import router
from .config import get_settings
from .document_intelligence.repository import DocumentRepository
from .infrastructure.postgres import psycopg_connection_factory


settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    runtime = get_settings(); url = runtime.postgres_url or runtime.database_url
    if url:
        try:
            DocumentRepository(psycopg_connection_factory(url)).mark_interrupted_batches()
        except Exception:
            logging.getLogger("v2.startup").error("batch recovery check failed")
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description="Non-authoritative V2 document-intelligence foundation beside the certified Streamlit baseline.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Organization-ID", "X-Company-ID", "X-User-ID"],
)
app.include_router(router)
