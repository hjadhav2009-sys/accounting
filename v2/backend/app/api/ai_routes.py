from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..hybrid_ai.hardware import detect_hardware
from ..hybrid_ai.models import AiMode, BillingMode, PrivacyMode, TenantContext
from ..hybrid_ai.policy import AiPolicyService
from ..hybrid_ai.privacy import PrivacyService
from ..hybrid_ai.providers import CloudAiService, LocalAiService
from ..hybrid_ai.quota import AiQuotaService, PostgresAiQuotaService
from ..hybrid_ai.repository import AiRepository
from ..hybrid_ai.service import HybridAiService
from ..infrastructure.postgres import psycopg_connection_factory
from .document_routes import RequestContext, request_context


router = APIRouter(prefix="/api/v2/ai", tags=["hybrid-ai"])


class PayloadPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=100_000)
    privacy_mode: PrivacyMode = PrivacyMode.BALANCED
    known_entities: list[str] = Field(default_factory=list, max_length=100)


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str = Field(min_length=1, max_length=80)
    text: str = Field(max_length=100_000)
    selection: dict[str, Any] = Field(default_factory=dict)
    mode: AiMode = AiMode.HYBRID_PRIVATE
    privacy_mode: PrivacyMode = PrivacyMode.BALANCED
    requires_vision: bool = False


def tenant(value: RequestContext) -> TenantContext:
    return TenantContext(value.organization_id,value.company_id,value.user_id,
                         frozenset(role.value for role in value.roles))


def build_service(context: RequestContext | None = None) -> HybridAiService:
    settings=get_settings(); local=None; cloud=None
    if settings.local_ai_model:
        local=LocalAiService(settings.local_ai_endpoint,settings.local_ai_model,60,settings.local_ai_api_key)
    if settings.cloudflare_ai_worker_url and settings.cloudflare_ai_worker_hmac_secret:
        cloud=CloudAiService(settings.cloudflare_ai_worker_url,settings.cloudflare_ai_worker_hmac_secret)
    quota: Any=AiQuotaService(limit=settings.ai_daily_free_neurons,billing_mode=BillingMode(settings.ai_billing_mode))
    url=settings.postgres_url or settings.database_url
    if context and cloud and url:
        quota=PostgresAiQuotaService(psycopg_connection_factory(url),context.organization_id,context.company_id,
                                     settings.cloudflare_account_id or "byoc-default",settings.ai_daily_free_neurons,
                                     billing_mode=BillingMode(settings.ai_billing_mode))
    return HybridAiService(local=local,cloud=cloud,privacy=PrivacyService(),policy=AiPolicyService(),quota=quota)


def repository() -> AiRepository | None:
    settings=get_settings(); url=settings.postgres_url or settings.database_url
    return AiRepository(psycopg_connection_factory(url)) if url else None


@router.get("/status")
def status(_context: Annotated[RequestContext, Depends(request_context)]):
    settings=get_settings(); hardware=detect_hardware(settings.storage_root)
    local_configured=bool(settings.local_ai_model)
    cloud_configured=bool(settings.cloudflare_ai_worker_url and settings.cloudflare_ai_worker_hmac_secret)
    quota=AiQuotaService(settings.ai_daily_free_neurons,billing_mode=BillingMode(settings.ai_billing_mode)).status()
    runtime_verified=settings.ai_phase5_runtime_certified
    return {"phase":"PHASE_5_PASS" if runtime_verified else "PHASE_5_PARTIAL","mode":settings.ai_mode,"billing_mode":settings.ai_billing_mode,
            "privacy_mode":settings.ai_privacy_mode,"local":{"configured":local_configured,
            "runtime_healthy":hardware.runtime_healthy,"model":settings.local_ai_model or None},
            "cloud":{"configured":cloud_configured,"deployed_runtime_verified":runtime_verified,
            "model":settings.cloudflare_ai_model if cloud_configured else None,"raw_payload_logging":False},
            "quota":quota.__dict__,"human_approval_required":True,"deterministic_authority":True}


@router.get("/setup/hardware")
def hardware(_context: Annotated[RequestContext, Depends(request_context)]):
    return detect_hardware(get_settings().storage_root).public()


@router.get("/models")
def models(_context: Annotated[RequestContext, Depends(request_context)]):
    settings=get_settings()
    runtime_status="READY" if settings.ai_phase5_runtime_certified else "UNVERIFIED"
    return {"items":[
        {"provider":"LOCAL","model":settings.local_ai_model or "not-configured","capabilities":["TEXT","STRUCTURED_OUTPUT"],"status":runtime_status},
        {"provider":"CLOUDFLARE_WORKERS_AI","role":"TEXT_TOOL_MODEL","model":settings.cloudflare_ai_model,"capabilities":["TEXT","TOOLS","STRUCTURED_OUTPUT"],"status":runtime_status},
        {"provider":"CLOUDFLARE_WORKERS_AI","role":"VISION_DOCUMENT_MODEL","model":settings.cloudflare_ai_vision_model,"capabilities":["VISION","STRUCTURED_OUTPUT"],"status":runtime_status},
    ]}


@router.post("/payload-preview")
def payload_preview(payload: PayloadPreviewRequest,
                    context: Annotated[RequestContext, Depends(request_context)]):
    if payload.privacy_mode == PrivacyMode.OFF_ADMIN_ONLY and "ADMIN" not in {role.value for role in context.roles}:
        raise HTTPException(403,"privacy-off mode is admin-only")
    value=PrivacyService().sanitize(payload.text,payload.privacy_mode,payload.known_entities)
    return PrivacyService.payload_preview(value)


@router.post("/proposals")
def propose(payload: ProposalRequest, context: Annotated[RequestContext, Depends(request_context)]):
    service=build_service(context); repo=repository(); job=None
    if repo:
        job=repo.create_job(context.organization_id,context.company_id,context.user_id,payload.intent,
                            payload.mode.value,payload.privacy_mode.value,service.prompt_version)
    result=service.propose(tenant(context),intent=payload.intent,text=payload.text,selection=payload.selection,
                           mode=payload.mode,privacy_mode=payload.privacy_mode,requires_vision=payload.requires_vision,
                           model=get_settings().cloudflare_ai_model)
    if repo and job: repo.finish_job(context.organization_id,context.company_id,job["id"],result)
    result["job_id"]=str(job["id"]) if job else None
    return result


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repo=repository()
    if not repo: raise HTTPException(503,"PostgreSQL V2 metadata connection is not configured")
    if not repo.cancel_job(context.organization_id,context.company_id,job_id):
        raise HTTPException(409,"job is not cancellable")
    return {"job_id":job_id,"status":"CANCELLED"}


@router.get("/dashboard")
def dashboard(context: Annotated[RequestContext, Depends(request_context)]):
    repo=repository()
    if not repo: return {"jobs":{},"usage_30d":{"input_tokens":0,"output_tokens":0,"units":0},
                         "raw_payload_retention":False,"reset_timezone":"UTC"}
    return repo.dashboard(context.organization_id,context.company_id)
