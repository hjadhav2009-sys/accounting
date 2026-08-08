from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Query, Response, UploadFile
import logging
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..document_intelligence.models import IntakeContext, to_jsonable
from ..document_intelligence.ocr import TesseractOcrService
from ..document_intelligence.pipeline import DocumentIntakeService
from ..document_intelligence.repository import DocumentRepository
from ..document_intelligence.security import DocumentSecurityError, ResourceLimits
from ..infrastructure.postgres import psycopg_connection_factory
from ..services.storage import LocalFilesystemStorage


router = APIRouter(prefix="/api/v2", tags=["document-intelligence"])
logger = logging.getLogger("v2.document_processing")


@dataclass(frozen=True)
class RequestContext:
    organization_id: UUID
    company_id: UUID
    user_id: UUID


def request_context(
    organization_id: Annotated[UUID, Header(alias="X-Organization-ID")],
    company_id: Annotated[UUID, Header(alias="X-Company-ID")],
    user_id: Annotated[UUID, Header(alias="X-User-ID")],
) -> RequestContext:
    return RequestContext(organization_id, company_id, user_id)


def services() -> tuple[DocumentRepository, LocalFilesystemStorage]:
    settings = get_settings()
    url = settings.postgres_url or settings.database_url
    if not url:
        raise HTTPException(503, "PostgreSQL V2 metadata connection is not configured")
    repository = DocumentRepository(psycopg_connection_factory(url))
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


@router.post("/documents", status_code=201, include_in_schema=False)
@router.post("/documents/upload", status_code=201)
async def upload_document(file: Annotated[UploadFile, File()], context: Annotated[RequestContext, Depends(request_context)]):
    repository, storage = services()
    try:
        content = await file.read()
        return intake_service(repository, storage).process(
            IntakeContext(context.organization_id, context.company_id, context.user_id),
            file.filename or "document.pdf", file.content_type or "", content,
        )
    except DocumentSecurityError as exc:
        raise HTTPException(422, {"code": exc.code.value, "message": str(exc)}) from exc


def process_batch(batch_id: UUID, context: RequestContext, payloads: list[tuple[str, str, bytes]]) -> None:
    repository, storage = services()
    intake = intake_service(repository, storage)
    repository.start_batch(context.organization_id, context.company_id, batch_id)
    try:
        for filename, content_type, content in payloads:
            repository.batch_document_started(context.organization_id, context.company_id, batch_id)
            outcome = "FAILED"
            try:
                result = intake.process(IntakeContext(context.organization_id, context.company_id, context.user_id),
                                        filename, content_type, content, batch_id=batch_id)
                outcome = result["status"]
            except Exception:
                logger.error("document processing failed", extra={"batch_id": str(batch_id),
                    "tenant": str(context.organization_id), "company": str(context.company_id),
                    "stage": "BATCH_DOCUMENT", "error_code": "PROCESSING_FAILED"})
            finally:
                repository.batch_document_finished(context.organization_id, context.company_id, batch_id, outcome)
    finally:
        repository.finish_batch(context.organization_id, context.company_id, batch_id)


@router.post("/documents/batch", status_code=202)
async def upload_batch(background_tasks: BackgroundTasks, files: Annotated[list[UploadFile], File()],
                       context: Annotated[RequestContext, Depends(request_context)]):
    if len(files) > 50:
        raise HTTPException(422, "A batch may contain at most 50 documents")
    repository, _ = services()
    payloads = [(file.filename or "document.pdf", file.content_type or "", await file.read()) for file in files]
    batch_id = repository.create_batch(context.organization_id, context.company_id, context.user_id, len(payloads))
    background_tasks.add_task(process_batch, batch_id, context, payloads)
    return {"batch_id": batch_id, "status": "QUEUED", "total": len(payloads),
            "restart_semantics": "progress persists; interrupted in-process uploads require explicit resubmission"}


@router.get("/batches/{batch_id}")
def batch_status(batch_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services()
    result = repository.get_batch(context.organization_id, context.company_id, batch_id)
    if not result:
        raise HTTPException(404, "Batch not found")
    result["accounting_summary"] = repository.batch_accounting_summary(context.organization_id, context.company_id, batch_id)
    return result


@router.get("/batches/{batch_id}/documents")
def batch_documents(batch_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services()
    if not repository.get_batch(context.organization_id, context.company_id, batch_id):
        raise HTTPException(404, "Batch not found")
    return {"items": repository.batch_documents(context.organization_id, context.company_id, batch_id)}


@router.get("/documents")
def list_documents(context: Annotated[RequestContext, Depends(request_context)],
                   status: str | None = None, search: str = "", date_from: str | None = None,
                   date_to: str | None = None, document_type: str = "", supplier: str = "",
                   format_family_id: UUID | None = None, validation_status: str = "",
                   review_status: str = "", duplicate_status: str = "", uploaded_by: UUID | None = None,
                   limit: int = Query(100, ge=1, le=250), offset: int = Query(0, ge=0)):
    repository, _ = services()
    return {"items": repository.list(context.organization_id, context.company_id, status, search, limit, offset,
        date_from=date_from, date_to=date_to, document_type=document_type, supplier=supplier,
        format_family_id=format_family_id, validation_status=validation_status, review_status=review_status,
        duplicate_status=duplicate_status, uploaded_by=uploaded_by)}


@router.get("/documents/{document_id}")
def document_detail(document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services()
    result = repository.get(context.organization_id, context.company_id, document_id)
    if not result:
        raise HTTPException(404, "Document not found")
    result.pop("storage_key", None)
    return result


@router.get("/documents/{document_id}/content")
def document_content(document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, storage = services()
    record = repository.get(context.organization_id, context.company_id, document_id)
    if not record:
        raise HTTPException(404, "Document not found")
    return Response(storage.read(record["storage_key"]), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{record["safe_filename"]}"'})


@router.get("/documents/{document_id}/pages")
def document_pages(document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services()
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

    repository, storage = services()
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
    repository, _ = services()
    result = repository.extraction(context.organization_id, context.company_id, document_id)
    if not result:
        raise HTTPException(404, "Extraction not found")
    return result


@router.get("/documents/{document_id}/validation")
def document_validation(document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services()
    result = repository.validation(context.organization_id, context.company_id, document_id)
    if not result:
        raise HTTPException(404, "Validation not found")
    return result


@router.get("/reviews")
def review_queue(context: Annotated[RequestContext, Depends(request_context)], status: str = "OPEN",
                 reason: str = "", severity: str = "", assigned_to: UUID | None = None,
                 date_from: str | None = None, date_to: str | None = None):
    repository, _ = services()
    return {"items": repository.reviews(context.organization_id, context.company_id, status,
        reason=reason, severity=severity, assigned_to=assigned_to, date_from=date_from, date_to=date_to)}


@router.post("/reviews/{review_id}/resolve")
def resolve_review(review_id: UUID, resolution: ReviewResolution,
                   context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services()
    changed = repository.resolve_review(context.organization_id, context.company_id, review_id,
                                        context.user_id, resolution.resolution_note, resolution.status)
    if not changed:
        raise HTTPException(404, "Open review task not found")
    return {"review_id": review_id, "status": resolution.status}


@router.get("/reports/document-intelligence")
def document_report(context: Annotated[RequestContext, Depends(request_context)],
                    date_from: str | None = None, date_to: str | None = None):
    repository, _ = services()
    return to_jsonable(repository.unified_report(context.organization_id, context.company_id, date_from, date_to))


@router.get("/reports/unified")
def unified_report(context: Annotated[RequestContext, Depends(request_context)],
                   date_from: str | None = None, date_to: str | None = None):
    repository, _ = services()
    return to_jsonable(repository.unified_report(context.organization_id, context.company_id, date_from, date_to))


@router.get("/reports/format-health")
def format_health(context: Annotated[RequestContext, Depends(request_context)]):
    repository, _ = services()
    return {"items": to_jsonable(repository.format_health(context.organization_id, context.company_id))}
