from fastapi import FastAPI

from .api.routes import router
from .config import get_settings


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description="Disabled/non-authoritative V2 foundation beside the certified Streamlit baseline.",
)
app.include_router(router)
