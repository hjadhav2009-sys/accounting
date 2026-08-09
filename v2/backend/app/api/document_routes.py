from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile
import logging
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..document_intelligence.models import IntakeContext, to_jsonable
from ..document_intelligence.ocr import TesseractOcrService
from ..document_intelligence.pipeline import DocumentIntakeService
from ..document_intelligence.repository import DocumentRepository
from ..document_intelligence.security import DocumentSecurityError, ResourceLimits
from ..infrastructure.postgres import psycopg_connection_factory, psycopg_tenant_connection_factory
from ..services.storage import LocalFilesystemStorage
from ..domain.enums import Role
from ..security.sessions import SessionRepository
from ..jobs.durable import DurableJobRepository
from ..domain.enums import Permission
from ..security.authorization import AuthorizationService
from ..services.accounting_exports import excel_preview,safe_export_filename
from ..services.legacy import LegacyExcelExportService
from ..services.accounting_workflows import AccountingWorkflowRepository,bank_preview,bank_xml,marketplace_preview,marketplace_xml
import hashlib
import tempfile
from pathlib import Path


router = APIRouter(prefix="/api/v2", tags=["document-intelligence"])
logger = logging.getLogger("v2.document_processing")


@dataclass(frozen=True)
class RequestContext:
    organization_id: UUID
    company_id: UUID
    user_id: UUID
    roles: frozenset[Role] = frozenset({Role.VIEWER})


def request_context(
    request: Request,
    header_organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    header_company_id: Annotated[UUID | None, Header(alias="X-Company-ID")] = None,
    header_user_id: Annotated[UUID | None, Header(alias="X-User-ID")] = None,
    roles: Annotated[str, Header(alias="X-Roles")] = "VIEWER",
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token")] = "",
) -> RequestContext:
    settings=get_settings()
    if settings.production_auth_enabled:
        url=settings.postgres_url or settings.database_url
        if not url: raise HTTPException(503,"authentication database is not configured")
        token=request.cookies.get(settings.session_cookie_name,"")
        identity=SessionRepository(psycopg_connection_factory(url),idle_minutes=settings.session_idle_minutes,
            absolute_hours=settings.session_absolute_hours).resolve(token,header_company_id,csrf_token)
        if not identity: raise HTTPException(401,"authentication required")
        if request.method not in {"GET","HEAD","OPTIONS"} and not identity.csrf_token_valid:
            raise HTTPException(403,"CSRF validation failed")
        return RequestContext(identity.organization_id,identity.company_id,identity.user_id,identity.roles)
    if not header_organization_id or not header_company_id or not header_user_id:
        raise HTTPException(401,"development identity headers are required")
    parsed: set[Role] = set()
    for value in roles.split(","):
        try:
            parsed.add(Role(value.strip().upper()))
        except ValueError:
            continue
    return RequestContext(header_organization_id, header_company_id, header_user_id, frozenset(parsed or {Role.VIEWER}))


def services(context: RequestContext) -> tuple[DocumentRepository, LocalFilesystemStorage]:
    settings = get_settings()
    url = settings.postgres_url or settings.database_url
    if not url:
        raise HTTPException(503, "PostgreSQL V2 metadata connection is not configured")
    repository = DocumentRepository(psycopg_tenant_connection_factory(
        url, context.organization_id, context.company_id, context.user_id))
    return repository, LocalFilesystemStorage(settings.storage_root)


def intake_service(repository: DocumentRepository, storage: LocalFilesystemStorage) -> DocumentIntakeService:
    settings = get_settings()
    limits = ResourceLimits(
        ocr_concurrency=settings.ocr_max_concurrency,
        ocr_timeout_seconds=settings.ocr_timeout_seconds,
        ocr_max_pages=settings.ocr_max_pages,
    )
    ocr = TesseractOcrService(settings.tesseract_cmd or None, timeout_seconds=settings.ocr_timeout_seconds)
    return DocumentIntakeService(repository, storage, ocr, limits)


class ReviewResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution_note: str = Field(min_length=1, max_length=2000)
    status: str = Field(default="RESOLVED", pattern="^(RESOLVED|REJECTED)$")


class MappingSave(BaseModel):
    model_config=ConfigDict(extra="forbid")
    tool:str=Field(pattern="^(marketplace|bank)$")
    platform:str=Field(default="",max_length=80)
    pattern:str=Field(min_length=1,max_length=500)
    voucher_type:str=Field(default="",max_length=80)
    ledger:str=Field(min_length=1,max_length=240)
    match_type:str=Field(default="contains",pattern="^(contains|smart_contains|equals|starts_with|regex)$")


@router.post("/documents", status_code=201, include_in_schema=False)
@router.post("/documents/upload", status_code=201)
async def upload_document(file: Annotated[UploadFile, File()], context: Annotated[RequestContext, Depends(request_context)]):
    repository, storage = services(context)
    try:
        content = await file.read()
        return intake_service(repository, storage).process(
            IntakeContext(context.organization_id, context.company_id, context.user_id),
            file.filename or "document.pdf", file.content_type or "", content,
        )
    except DocumentSecurityError as exc:
        raise HTTPException(422, {"code": exc.code.value, "message": str(exc)}) from exc


def durable_repository() -> DurableJobRepository:
    settings=get_settings();url=settings.postgres_url or settings.database_url
    if not url: raise RuntimeError("PostgreSQL V2 metadata connection is not configured")
    return DurableJobRepository(psycopg_connection_factory(url))


def process_next_durable_job(worker_id:str="local-document-worker",batch_id:UUID|None=None)->bool:
    queue=durable_repository();job=queue.claim(worker_id,batch_id)
    if not job:return False
    context=RequestContext(job.organization_id,job.company_id,job.initiated_by,frozenset({Role.OPERATOR}))
    repository,storage=services(context)
    if job.batch_id:
        try:repository.start_batch(job.organization_id,job.company_id,job.batch_id)
        except RuntimeError:pass
    outcome="FAILED";document_id=None;terminal=False
    try:
        queue.heartbeat(job,10);content=storage.read(job.source_storage_key)
        result=intake_service(repository,storage).process(IntakeContext(job.organization_id,job.company_id,job.initiated_by),
            job.original_filename,job.mime_type,content,batch_id=job.batch_id)
        document_id=UUID(str(result["document_id"]));outcome=str(result["status"])
        terminal=queue.finish(job,document_id)=="COMPLETED"
        if terminal:storage.delete_pending(job.source_storage_key)
    except Exception as exc:
        status=queue.finish(job,None,type(exc).__name__.upper()[:80],retryable=not isinstance(exc,DocumentSecurityError));terminal=status=="FAILED"
        logger.error("durable document processing failed",extra={"job_id":str(job.id),"batch_id":str(job.batch_id or ""),
            "tenant":str(job.organization_id),"company":str(job.company_id),"stage":"DURABLE_DOCUMENT","error_code":type(exc).__name__.upper()[:80]})
    if terminal and job.batch_id:
        repository.batch_document_started(job.organization_id,job.company_id,job.batch_id)
        repository.batch_document_finished(job.organization_id,job.company_id,job.batch_id,outcome)
        if queue.active_for_batch(job.batch_id)==0:repository.finish_batch(job.organization_id,job.company_id,job.batch_id)
    return True


def process_durable_batch(batch_id:UUID)->None:
    while process_next_durable_job(batch_id=batch_id): pass


@router.post("/documents/batch", status_code=202)
async def upload_batch(background_tasks: BackgroundTasks, files: Annotated[list[UploadFile], File()],
                       context: Annotated[RequestContext, Depends(request_context)]):
    if len(files) > 50:
        raise HTTPException(422, "A batch may contain at most 50 documents")
    repository,storage = services(context)
    batch_id = repository.create_batch(context.organization_id, context.company_id, context.user_id, len(files))
    queue=durable_repository();job_ids=[]
    for file in files:
        content=await file.read();staging_id=uuid4()
        stored=storage.put_pending(context.organization_id,context.company_id,staging_id,file.filename or "document.pdf",content)
        try:
            job_ids.append(queue.enqueue(context.organization_id,context.company_id,batch_id,context.user_id,
                stored.storage_key,file.filename or "document.pdf",file.content_type or "",stored.sha256))
        except Exception:
            storage.delete_pending(stored.storage_key);raise
    background_tasks.add_task(process_durable_batch,batch_id)
    return {"batch_id": batch_id, "status": "QUEUED", "total": len(files),
            "job_ids":job_ids,"restart_semantics":"source persisted; queued/running work resumes after restart"}


@router.get("/batches/{batch_id}")
def batch_status(batch_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services(context)
    result = repository.get_batch(context.organization_id, context.company_id, batch_id)
    if not result:
        raise HTTPException(404, "Batch not found")
    result["accounting_summary"] = repository.batch_accounting_summary(context.organization_id, context.company_id, batch_id)
    return result


@router.get("/batches/{batch_id}/documents")
def batch_documents(batch_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services(context)
    if not repository.get_batch(context.organization_id, context.company_id, batch_id):
        raise HTTPException(404, "Batch not found")
    return {"items": repository.batch_documents(context.organization_id, context.company_id, batch_id)}


@router.get("/documents")
def list_documents(context: Annotated[RequestContext, Depends(request_context)],
                   status: str | None = None, search: str = "", date_from: str | None = None,
                   date_to: str | None = None, document_type: str = "", supplier: str = "",
                   format_family_id: UUID | None = None, validation_status: str = "",
                   review_status: str = "", duplicate_status: str = "", uploaded_by: UUID | None = None,
                   financial_year_id:UUID|None=None,
                   limit: int = Query(100, ge=1, le=250), offset: int = Query(0, ge=0)):
    repository, _ = services(context)
    return {"items": repository.list(context.organization_id, context.company_id, status, search, limit, offset,
        date_from=date_from, date_to=date_to, document_type=document_type, supplier=supplier,
        format_family_id=format_family_id, validation_status=validation_status, review_status=review_status,
        duplicate_status=duplicate_status, uploaded_by=uploaded_by,financial_year_id=financial_year_id)}


@router.get("/documents/{document_id}")
def document_detail(document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services(context)
    result = repository.get(context.organization_id, context.company_id, document_id)
    if not result:
        raise HTTPException(404, "Document not found")
    result.pop("storage_key", None)
    return result


@router.get("/documents/{document_id}/content")
def document_content(document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, storage = services(context)
    record = repository.get(context.organization_id, context.company_id, document_id)
    if not record:
        raise HTTPException(404, "Document not found")
    return Response(storage.read(record["storage_key"]), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{record["safe_filename"]}"'})


@router.get("/documents/{document_id}/pages")
def document_pages(document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services(context)
    record = repository.get(context.organization_id, context.company_id, document_id)
    if not record:
        raise HTTPException(404, "Document not found")
    extraction = repository.extraction(context.organization_id, context.company_id, document_id)
    pages = (extraction or {}).get("normalized_result", {}).get("pages", [])
    return {"document_id": document_id, "pages": pages}


@router.get("/documents/{document_id}/pages/{page_number}/image")
def document_page_image(document_id: UUID, page_number: int,
                        context: Annotated[RequestContext, Depends(request_context)]):
    import pymupdf

    repository, storage = services(context)
    record = repository.get(context.organization_id, context.company_id, document_id)
    if not record:
        raise HTTPException(404, "Document not found")
    if page_number < 1 or page_number > record["page_count"]:
        raise HTTPException(404, "Document page not found")
    document = pymupdf.open(stream=storage.read(record["storage_key"]), filetype="pdf")
    try:
        page = document[page_number - 1]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        content = pixmap.tobytes("png")
    finally:
        document.close()
    return Response(content, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.get("/documents/{document_id}/extraction")
def document_extraction(document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services(context)
    result = repository.extraction(context.organization_id, context.company_id, document_id)
    if not result:
        raise HTTPException(404, "Extraction not found")
    return result


@router.get("/documents/{document_id}/validation")
def document_validation(document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services(context)
    result = repository.validation(context.organization_id, context.company_id, document_id)
    if not result:
        raise HTTPException(404, "Validation not found")
    return result


def require_permission(context:RequestContext,permission:Permission)->None:
    if not AuthorizationService().is_allowed(set(context.roles),permission):raise HTTPException(403,"permission denied")


@router.get("/documents/{document_id}/excel-preview")
def document_excel_preview(document_id:UUID,context:Annotated[RequestContext,Depends(request_context)]):
    require_permission(context,Permission.DOCUMENT_VIEW);repository,storage=services(context)
    record=repository.get(context.organization_id,context.company_id,document_id)
    if not record:raise HTTPException(404,"Document not found")
    extraction=repository.extraction(context.organization_id,context.company_id,document_id)
    validation=repository.validation(context.organization_id,context.company_id,document_id)
    if not extraction:raise HTTPException(409,"Document extraction is not available")
    preview=excel_preview(storage.read(record["storage_key"]),record["original_filename"],extraction["normalized_result"])
    preview.update({"document_id":document_id,"document_type":record.get("document_type") or "Custom",
        "validation_status":(validation or {}).get("status","MISSING"),"export_allowed":bool(validation and validation["status"]=="VERIFIED" and record["status"]=="VERIFIED")})
    return preview


@router.post("/documents/{document_id}/excel")
def document_excel(document_id:UUID,context:Annotated[RequestContext,Depends(request_context)]):
    require_permission(context,Permission.EXCEL_EXPORT);repository,storage=services(context)
    record=repository.get(context.organization_id,context.company_id,document_id)
    if not record:raise HTTPException(404,"Document not found")
    extraction=repository.extraction(context.organization_id,context.company_id,document_id)
    validation=repository.validation(context.organization_id,context.company_id,document_id)
    if not extraction or not validation or validation["status"]!="VERIFIED" or record["status"]!="VERIFIED":
        raise HTTPException(409,"Excel export is blocked until deterministic validation is VERIFIED")
    preview=excel_preview(storage.read(record["storage_key"]),record["original_filename"],extraction["normalized_result"])
    if not preview["rows"]:raise HTTPException(409,"Excel export has no accounting rows")
    filename=safe_export_filename(record["original_filename"])
    with tempfile.TemporaryDirectory(prefix="bap-excel-") as directory:
        output=Path(directory)/filename;LegacyExcelExportService().export(preview["rows"],preview["item_rows"],output);content=output.read_bytes()
    digest=hashlib.sha256(content).hexdigest()
    repository.record_export(context.organization_id,context.company_id,document_id,context.user_id,"EXCEL",filename,
        digest,validation["status"],extraction["id"],{"template":preview["template"],"summary":preview["summary"],
        "extractor_version":extraction["extractor_version"],"validator_version":validation["validator_version"]})
    return Response(content,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":f'attachment; filename="{filename}"',"X-Content-SHA256":digest})


@router.get("/exports")
def export_history(context:Annotated[RequestContext,Depends(request_context)],document_id:UUID|None=None):
    require_permission(context,Permission.DOCUMENT_VIEW);repository,_=services(context)
    return {"items":repository.exports(context.organization_id,context.company_id,document_id)}


def workflow_repository(context:RequestContext)->AccountingWorkflowRepository:
    settings=get_settings();url=settings.postgres_url or settings.database_url
    if not url:raise HTTPException(503,"PostgreSQL is not configured")
    return AccountingWorkflowRepository(psycopg_tenant_connection_factory(url,context.organization_id,context.company_id,context.user_id))


@router.get("/marketplace/{document_id}/preview")
def marketplace_document_preview(document_id:UUID,context:Annotated[RequestContext,Depends(request_context)]):
    require_permission(context,Permission.MARKETPLACE_PROCESS);documents,storage=services(context)
    record=documents.get(context.organization_id,context.company_id,document_id)
    if not record:raise HTTPException(404,"Document not found")
    result=marketplace_preview(storage.read(record["storage_key"]),record["original_filename"],context.organization_id,
        context.company_id,workflow_repository(context))
    return {key:value for key,value in result.items() if key!="profile"}


@router.post("/mappings")
def save_mapping(payload:MappingSave,context:Annotated[RequestContext,Depends(request_context)]):
    require_permission(context,Permission.MAPPING_EDIT)
    try:mapping_id=workflow_repository(context).save_mapping(context.organization_id,context.company_id,context.user_id,
        payload.tool,payload.platform,payload.pattern,payload.voucher_type,payload.ledger,payload.match_type)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    return {"id":mapping_id,"status":"SAVED","audit":"MAPPING_CHANGED"}


@router.post("/marketplace/{document_id}/xml")
def marketplace_document_xml(document_id:UUID,context:Annotated[RequestContext,Depends(request_context)]):
    require_permission(context,Permission.XML_EXPORT);documents,storage=services(context)
    record=documents.get(context.organization_id,context.company_id,document_id)
    if not record:raise HTTPException(404,"Document not found")
    preview=marketplace_preview(storage.read(record["storage_key"]),record["original_filename"],context.organization_id,
        context.company_id,workflow_repository(context))
    try:content=marketplace_xml(preview)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    filename=f"{Path(safe_export_filename(record['original_filename'])).stem}.xml";digest=hashlib.sha256(content).hexdigest()
    extraction=documents.extraction(context.organization_id,context.company_id,document_id)
    documents.record_export(context.organization_id,context.company_id,document_id,context.user_id,"MARKETPLACE_XML",
        filename,digest,preview["validation_status"],extraction["id"] if extraction else None,
        {"mapping_snapshot_sha256":preview["mapping_snapshot_sha256"],"totals":preview["totals"],"row_count":len(preview["rows"])})
    return Response(content,media_type="application/xml",headers={"Content-Disposition":f'attachment; filename="{filename}"',"X-Content-SHA256":digest})


@router.get("/bank/{document_id}/preview")
def bank_document_preview(document_id:UUID,context:Annotated[RequestContext,Depends(request_context)]):
    require_permission(context,Permission.BANK_PROCESS);documents,storage=services(context)
    record=documents.get(context.organization_id,context.company_id,document_id)
    if not record:raise HTTPException(404,"Document not found")
    settings=get_settings()
    return bank_preview(storage.read(record["storage_key"]),record["original_filename"],context.organization_id,
        context.company_id,workflow_repository(context),settings.bank_reconciliation_tolerance)


@router.post("/bank/{document_id}/xml")
def bank_document_xml(document_id:UUID,context:Annotated[RequestContext,Depends(request_context)]):
    require_permission(context,Permission.XML_EXPORT);documents,storage=services(context)
    record=documents.get(context.organization_id,context.company_id,document_id)
    if not record:raise HTTPException(404,"Document not found")
    settings=get_settings();preview=bank_preview(storage.read(record["storage_key"]),record["original_filename"],
        context.organization_id,context.company_id,workflow_repository(context),settings.bank_reconciliation_tolerance)
    try:content=bank_xml(preview)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    filename=f"{Path(safe_export_filename(record['original_filename'])).stem}_bank.xml";digest=hashlib.sha256(content).hexdigest()
    extraction=documents.extraction(context.organization_id,context.company_id,document_id)
    documents.record_export(context.organization_id,context.company_id,document_id,context.user_id,"BANK_XML",filename,
        digest,preview["validation_status"],extraction["id"] if extraction else None,
        {"mapping_snapshot_sha256":preview["mapping_snapshot_sha256"],"reconciliation":preview["reconciliation"],
         "bank_account_id":str(preview["bank_account"]["id"])})
    return Response(content,media_type="application/xml",headers={"Content-Disposition":f'attachment; filename="{filename}"',"X-Content-SHA256":digest})


@router.get("/reviews")
def review_queue(context: Annotated[RequestContext, Depends(request_context)], status: str = "OPEN",
                 reason: str = "", severity: str = "", assigned_to: UUID | None = None,
                 date_from: str | None = None, date_to: str | None = None):
    repository, _ = services(context)
    return {"items": repository.reviews(context.organization_id, context.company_id, status,
        reason=reason, severity=severity, assigned_to=assigned_to, date_from=date_from, date_to=date_to)}


@router.post("/reviews/{review_id}/resolve")
def resolve_review(review_id: UUID, resolution: ReviewResolution,
                   context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services(context)
    changed = repository.resolve_review(context.organization_id, context.company_id, review_id,
                                        context.user_id, resolution.resolution_note, resolution.status)
    if not changed:
        raise HTTPException(404, "Open review task not found")
    return {"review_id": review_id, "status": resolution.status}


@router.get("/reports/document-intelligence")
def document_report(context: Annotated[RequestContext, Depends(request_context)],
                    date_from: str | None = None, date_to: str | None = None):
    repository, _ = services(context)
    return to_jsonable(repository.unified_report(context.organization_id, context.company_id, date_from, date_to))


@router.get("/reports/unified")
def unified_report(context: Annotated[RequestContext, Depends(request_context)],
                   date_from: str | None = None, date_to: str | None = None,financial_year_id:UUID|None=None):
    repository, _ = services(context)
    if financial_year_id:
        year=repository.financial_year(context.organization_id,context.company_id,financial_year_id)
        if not year:raise HTTPException(404,"Financial year not found")
        date_from,date_to=str(year["starts_on"]),str(year["ends_on"])
    return to_jsonable(repository.unified_report(context.organization_id, context.company_id, date_from, date_to))


@router.get("/financial-years")
def financial_years(context:Annotated[RequestContext,Depends(request_context)]):
    repository,_=services(context);return {"items":repository.financial_years(context.organization_id,context.company_id)}


@router.get("/reports/format-health")
def format_health(context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services(context)
    return {"items": to_jsonable(repository.format_health(context.organization_id, context.company_id))}
