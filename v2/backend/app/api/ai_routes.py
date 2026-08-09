from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID
import base64
import io

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field,model_validator

from ..config import get_settings
from ..hybrid_ai.hardware import detect_hardware
from ..hybrid_ai.models import AiMode, BillingMode, PrivacyMode, TenantContext
from ..hybrid_ai.policy import AiPolicyService
from ..hybrid_ai.privacy import PrivacyService
from ..hybrid_ai.providers import CloudAiService, LocalAiService
from ..hybrid_ai.quota import AiQuotaService, PostgresAiQuotaService
from ..hybrid_ai.repository import AiRepository
from ..hybrid_ai.service import HybridAiService
from ..infrastructure.postgres import psycopg_connection_factory, psycopg_tenant_connection_factory
from ..domain.enums import Permission
from ..document_intelligence.ocr import TesseractOcrService
from ..security.authorization import AuthorizationService
from .document_routes import RequestContext, permission_dependency, request_context,services as document_services


router = APIRouter(prefix="/api/v2/ai", tags=["hybrid-ai"])

AI_ROUTE_PERMISSION_MATRIX={
    ("GET","/api/v2/ai/status"):Permission.DOCUMENT_VIEW,
    ("GET","/api/v2/ai/setup/hardware"):Permission.DOCUMENT_VIEW,
    ("GET","/api/v2/ai/models"):Permission.DOCUMENT_VIEW,
    ("POST","/api/v2/ai/payload-preview"):Permission.TEMPLATE_CREATE,
    ("POST","/api/v2/ai/proposals"):Permission.TEMPLATE_CREATE,
    ("POST","/api/v2/ai/jobs/{job_id}/cancel"):Permission.DOCUMENT_VIEW,
    ("GET","/api/v2/ai/dashboard"):Permission.DOCUMENT_VIEW,
}


class PayloadPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=100_000)
    privacy_mode: PrivacyMode = PrivacyMode.BALANCED
    known_entities: list[str] = Field(default_factory=list, max_length=100)


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str = Field(min_length=1, max_length=80)
    text: str = Field(max_length=100_000)
    selection: "SelectionContext" = Field(default_factory=lambda:SelectionContext())
    mode: AiMode = AiMode.HYBRID_PRIVATE
    privacy_mode: PrivacyMode = PrivacyMode.BALANCED
    requires_vision: bool = False
    document_id:UUID|None=None


class VisionBox(BaseModel):
    model_config=ConfigDict(extra="forbid")
    x0:float=Field(ge=0,le=1);y0:float=Field(ge=0,le=1);x1:float=Field(gt=0,le=1);y1:float=Field(gt=0,le=1)
    @model_validator(mode="after")
    def ordered(self):
        if self.x0>=self.x1 or self.y0>=self.y1:raise ValueError("vision box coordinates must be ordered")
        return self


class SelectionContext(BaseModel):
    model_config=ConfigDict(extra="forbid")
    selected_type:str=Field(default="",max_length=40)
    page:int=Field(default=1,ge=1,le=200)
    nearby_text:str=Field(default="",max_length=1000)
    field_name:str=Field(default="",max_length=100)
    box:VisionBox|None=None


ProposalRequest.model_rebuild()


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
    if context and url:
        quota=PostgresAiQuotaService(psycopg_tenant_connection_factory(
            url,context.organization_id,context.company_id,context.user_id),context.organization_id,context.company_id,
                                     settings.cloudflare_account_id or "byoc-default",settings.ai_daily_free_neurons,
                                     billing_mode=BillingMode(settings.ai_billing_mode))
    return HybridAiService(local=local,cloud=cloud,privacy=PrivacyService(),policy=AiPolicyService(),quota=quota)


def repository(context: RequestContext) -> AiRepository | None:
    settings=get_settings(); url=settings.postgres_url or settings.database_url
    return AiRepository(psycopg_tenant_connection_factory(
        url,context.organization_id,context.company_id,context.user_id)) if url else None


def server_sanitized_vision(context:RequestContext,payload:ProposalRequest)->str|None:
    if not payload.requires_vision:return None
    if not payload.document_id or not payload.selection.box:raise HTTPException(422,"vision requires a document and bounded selection box")
    documents,storage=document_services(context);record=documents.get(context.organization_id,context.company_id,payload.document_id)
    if not record:raise HTTPException(404,"Document not found")
    import pymupdf
    document=pymupdf.open(stream=storage.read(record["storage_key"]),filetype="pdf")
    try:
        page_number=payload.selection.page
        if page_number>len(document):raise HTTPException(422,"vision page is outside the document")
        page=document[page_number-1];box=payload.selection.box;bounds=page.rect
        clip=pymupdf.Rect(bounds.x0+box.x0*bounds.width,bounds.y0+box.y0*bounds.height,
                          bounds.x0+box.x1*bounds.width,bounds.y0+box.y1*bounds.height)
        image=page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),clip=clip,alpha=False).tobytes("png")
    finally:document.close()
    ocr=TesseractOcrService(get_settings().tesseract_cmd or None,timeout_seconds=30)
    try:boxes=PrivacyService.sensitive_image_boxes(image,ocr.executable,30)
    except RuntimeError as exc:raise HTTPException(503,str(exc)) from exc
    sanitized=PrivacyService.redact_image(image,boxes).png_bytes
    if len(sanitized)>240*1024:
        from PIL import Image
        with Image.open(io.BytesIO(sanitized)) as source:
            output=source.convert("RGB");output.thumbnail((720,720));buffer=io.BytesIO();output.save(buffer,"JPEG",quality=80,optimize=True);sanitized=buffer.getvalue()
    if len(sanitized)>256*1024:raise HTTPException(422,"sanitized vision crop exceeds the cloud safety limit")
    mime="image/jpeg" if sanitized.startswith(b"\xff\xd8") else "image/png"
    return f"data:{mime};base64,{base64.b64encode(sanitized).decode('ascii')}"


@router.get("/status")
def status(context: Annotated[RequestContext, Depends(permission_dependency(Permission.DOCUMENT_VIEW))]):
    settings=get_settings(); hardware=detect_hardware(settings.storage_root)
    local_configured=bool(settings.local_ai_model)
    cloud_configured=bool(settings.cloudflare_ai_worker_url and settings.cloudflare_ai_worker_hmac_secret)
    quota=build_service(context).quota.status()
    runtime_verified=settings.ai_phase5_runtime_certified
    return {"phase":"PHASE_5_PASS" if runtime_verified else "PHASE_5_PARTIAL","mode":settings.ai_mode,"billing_mode":settings.ai_billing_mode,
            "privacy_mode":settings.ai_privacy_mode,"local":{"configured":local_configured,
            "runtime_healthy":hardware.runtime_healthy,"model":settings.local_ai_model or None},
            "cloud":{"configured":cloud_configured,"deployed_runtime_verified":runtime_verified,
            "model":settings.cloudflare_ai_model if cloud_configured else None,"raw_payload_logging":False},
            "quota":quota.__dict__,"human_approval_required":True,"deterministic_authority":True}


@router.get("/setup/hardware")
def hardware(_context: Annotated[RequestContext, Depends(permission_dependency(Permission.DOCUMENT_VIEW))]):
    return detect_hardware(get_settings().storage_root).public()


@router.get("/models")
def models(_context: Annotated[RequestContext, Depends(permission_dependency(Permission.DOCUMENT_VIEW))]):
    settings=get_settings()
    runtime_status="READY" if settings.ai_phase5_runtime_certified else "UNVERIFIED"
    return {"items":[
        {"provider":"LOCAL","model":settings.local_ai_model or "not-configured","capabilities":["TEXT","STRUCTURED_OUTPUT"],"status":runtime_status},
        {"provider":"CLOUDFLARE_WORKERS_AI","role":"TEXT_TOOL_MODEL","model":settings.cloudflare_ai_model,"capabilities":["TEXT","TOOLS","STRUCTURED_OUTPUT"],"status":runtime_status},
        {"provider":"CLOUDFLARE_WORKERS_AI","role":"VISION_DOCUMENT_MODEL","model":settings.cloudflare_ai_vision_model,"capabilities":["VISION","STRUCTURED_OUTPUT"],"status":runtime_status},
    ]}


@router.post("/payload-preview")
def payload_preview(payload: PayloadPreviewRequest,
                    context: Annotated[RequestContext, Depends(permission_dependency(Permission.TEMPLATE_CREATE))]):
    if payload.privacy_mode == PrivacyMode.OFF_ADMIN_ONLY and "ADMIN" not in {role.value for role in context.roles}:
        raise HTTPException(403,"privacy-off mode is admin-only")
    value=PrivacyService().sanitize(payload.text,payload.privacy_mode,payload.known_entities)
    return PrivacyService.payload_preview(value)


@router.post("/proposals")
def propose(payload: ProposalRequest, context: Annotated[RequestContext, Depends(permission_dependency(Permission.TEMPLATE_CREATE))]):
    service=build_service(context); repo=repository(context); job=None
    if repo:
        job=repo.create_job(context.organization_id,context.company_id,context.user_id,payload.intent,
                            payload.mode.value,payload.privacy_mode.value,service.prompt_version)
    sanitized_image=server_sanitized_vision(context,payload)
    result=service.propose(tenant(context),intent=payload.intent,text=payload.text,selection=payload.selection.model_dump(),
                           mode=payload.mode,privacy_mode=payload.privacy_mode,requires_vision=payload.requires_vision,
                           model=get_settings().cloudflare_ai_model,sanitized_image_data_url=sanitized_image)
    if repo and job: repo.finish_job(context.organization_id,context.company_id,job["id"],result)
    result["job_id"]=str(job["id"]) if job else None
    return result


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: UUID, context: Annotated[RequestContext, Depends(permission_dependency(Permission.DOCUMENT_VIEW))]):
    repo=repository(context)
    if not repo: raise HTTPException(503,"PostgreSQL V2 metadata connection is not configured")
    privileged=AuthorizationService().is_allowed(set(context.roles),Permission.TEMPLATE_APPROVE)
    if not repo.cancel_job(context.organization_id,context.company_id,job_id,context.user_id,privileged):
        raise HTTPException(409,"job is not cancellable")
    return {"job_id":job_id,"status":"CANCELLED"}


@router.get("/dashboard")
def dashboard(context: Annotated[RequestContext, Depends(permission_dependency(Permission.DOCUMENT_VIEW))]):
    repo=repository(context)
    if not repo: return {"jobs":{},"usage_30d":{"input_tokens":0,"output_tokens":0,"units":0},
                         "raw_payload_retention":False,"reset_timezone":"UTC"}
    return repo.dashboard(context.organization_id,context.company_id)
