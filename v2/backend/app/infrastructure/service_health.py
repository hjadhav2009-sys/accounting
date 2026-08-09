from __future__ import annotations

import shutil
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


HEALTHY="HEALTHY";DEGRADED="DEGRADED";UNAVAILABLE="UNAVAILABLE";DISABLED="DISABLED"


def _port(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host,port),timeout=timeout):return True
    except OSError:return False


def _component(status: str, message: str) -> dict[str,str]:return {"status":status,"message":message}


def collect_health(settings, connect=None) -> dict[str,Any]:
    components:dict[str,dict[str,str]]={}
    components["frontend"]=_component(HEALTHY if _port("127.0.0.1",settings.frontend_port) else UNAVAILABLE,
        f"localhost:{settings.frontend_port}")
    components["backend"]=_component(HEALTHY,"Health API is responding")
    database_url=settings.postgres_url or settings.database_url
    if database_url and connect:
        try:
            connection=connect()
            try:
                with connection.cursor() as cursor:cursor.execute("SELECT version()");version=cursor.fetchone()[0].split(",")[0]
                components["postgresql"]=_component(HEALTHY,version)
            finally:connection.close()
        except Exception:components["postgresql"]=_component(UNAVAILABLE,"Database connection failed")
    else:components["postgresql"]=_component(DISABLED if not database_url else UNAVAILABLE,"Database is not configured" if not database_url else "Connection check unavailable")
    executable=(shutil.which(settings.tesseract_cmd) if settings.tesseract_cmd else None) or settings.tesseract_cmd or shutil.which("tesseract")
    components["tesseract"]=_component(HEALTHY if executable and Path(executable).exists() else UNAVAILABLE,
        "OCR executable available" if executable and Path(executable).exists() else "OCR executable not found")
    local=urlsplit(settings.local_ai_endpoint);local_port=local.port or (443 if local.scheme=="https" else 80)
    local_enabled=bool(settings.local_ai_model)
    components["local_ai"]=_component(HEALTHY if local_enabled and _port(local.hostname or "127.0.0.1",local_port) else (UNAVAILABLE if local_enabled else DISABLED),
        "Local model endpoint reachable" if local_enabled and _port(local.hostname or "127.0.0.1",local_port) else ("Configured but unreachable" if local_enabled else "Local model is not configured"))
    cloud_enabled=bool(settings.cloudflare_ai_worker_url)
    components["cloud_worker"]=_component(DEGRADED if cloud_enabled else DISABLED,
        "Configured; use explicit cloud self-test to verify" if cloud_enabled else "Cloud AI is not configured")
    components["text_cloud_model"]=_component(DEGRADED if cloud_enabled else DISABLED,"Configured, not invoked by passive health check" if cloud_enabled else "Disabled")
    components["vision_cloud_model"]=_component(DEGRADED if cloud_enabled else DISABLED,"Configured, not invoked by passive health check" if cloud_enabled else "Disabled")
    components["quota_safety"]=_component(HEALTHY if settings.ai_billing_mode=="FREE_ONLY" else DEGRADED,settings.ai_billing_mode)
    storage=Path(settings.storage_root)
    components["storage"]=_component(HEALTHY if storage.exists() and storage.is_dir() else UNAVAILABLE,
        "Protected storage directory available" if storage.exists() and storage.is_dir() else "Storage directory unavailable")
    components["job_worker"]=_component(HEALTHY if settings.durable_worker_enabled else DISABLED,"Durable PostgreSQL worker enabled" if settings.durable_worker_enabled else "Worker disabled")
    components["legacy_compatibility"]=_component(HEALTHY,"Legacy authority remains enabled")
    overall=HEALTHY if all(item["status"] in {HEALTHY,DISABLED} for item in components.values()) else DEGRADED
    return {"status":overall,"components":components,"secrets_exposed":False}
