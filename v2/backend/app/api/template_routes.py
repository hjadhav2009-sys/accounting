from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..document_intelligence.repository import DocumentRepository
from ..infrastructure.postgres import psycopg_tenant_connection_factory
from ..template_studio import TemplateConflict, TemplateImmutable, TemplateInvalid, TemplatePermissionDenied
from ..template_studio.models import StudioContext
from ..template_studio.repository import TemplateRepository
from ..template_studio.service import TemplateStudioService
from .document_routes import RequestContext, request_context


router = APIRouter(prefix="/api/v2", tags=["template-studio"])


def services(context: RequestContext) -> tuple[TemplateStudioService, DocumentRepository]:
    settings = get_settings(); url = settings.postgres_url or settings.database_url
    if not url: raise HTTPException(503, "PostgreSQL V2 metadata connection is not configured")
    connect = psycopg_tenant_connection_factory(url,context.organization_id,context.company_id,context.user_id)
    return TemplateStudioService(TemplateRepository(connect)), DocumentRepository(connect)


def studio_context(value: RequestContext) -> StudioContext:
    return StudioContext(value.organization_id, value.company_id, value.user_id,
                         frozenset(role.value for role in value.roles))


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TemplatePermissionDenied): return HTTPException(403, str(exc))
    if isinstance(exc, TemplateConflict): return HTTPException(409, {"code": "REVISION_CONFLICT", "message": str(exc)})
    if isinstance(exc, TemplateImmutable): return HTTPException(409, {"code": "VERSION_IMMUTABLE", "message": str(exc)})
    if isinstance(exc, TemplateInvalid): return HTTPException(422, {"code": "TEMPLATE_INVALID", "message": str(exc)})
    if isinstance(exc, KeyError): return HTTPException(404, str(exc).strip("'"))
    return HTTPException(500, "Template Studio operation failed")


class FamilyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=160)
    document_type: str = Field(min_length=1, max_length=100)
    supplier: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1000)
    mode: str = "GENERIC"


class SaveDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    definition: dict[str, Any]


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class CloneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_summary: str = Field(default="", max_length=1000)


class SampleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID
    expected_result: dict[str, Any] | None = None
    notes: str = Field(default="", max_length=2000)


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: dict[str, Any]


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict[str, Any]
    family_id: UUID | None = None


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID
    candidate_family_id: UUID | None = None


class CommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=1, max_length=2000)
    version_id: UUID | None = None
    document_id: UUID | None = None


class SelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selection: dict[str, Any]


class RoutingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fingerprint: dict[str, Any]
    candidates: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


@router.get("/templates")
def templates(context: Annotated[RequestContext, Depends(request_context)], document_type: str = "", status: str = "",
              supplier: str = "", search: str = ""):
    service, _ = services(context)
    return {"items": service.repository.list_families(context.organization_id, context.company_id,
        document_type=document_type, status=status, supplier=supplier, search=search)}


@router.post("/templates/families", status_code=201)
def create_family(payload: FamilyCreate, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.create_family(studio_context(context), **payload.model_dump())
    except Exception as exc: raise translate_error(exc) from exc


@router.get("/templates/families/{family_id}")
def family_detail(family_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context); result = service.repository.get_family(context.organization_id, context.company_id, family_id)
    if not result: raise HTTPException(404, "Format family not found")
    result["activity"] = service.repository.activity(context.organization_id, context.company_id, family_id)
    return result


@router.post("/templates/versions/{version_id}/clone", status_code=201)
def clone_version(version_id: UUID, payload: CloneRequest, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.clone_version(studio_context(context), version_id, payload.change_summary)
    except Exception as exc: raise translate_error(exc) from exc


@router.get("/templates/versions/{version_id}")
def version_detail(version_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try:
        result = service._version(studio_context(context), version_id)
        result["samples"] = service.repository.samples(context.organization_id, context.company_id, version_id)
        return result
    except Exception as exc: raise translate_error(exc) from exc


@router.put("/templates/versions/{version_id}")
def save_version(version_id: UUID, payload: SaveDefinition, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.save(studio_context(context), version_id, payload.definition, payload.revision)
    except Exception as exc: raise translate_error(exc) from exc


@router.post("/templates/versions/{version_id}/actions")
def template_action(version_id: UUID, payload: ActionRequest, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.action(studio_context(context), version_id, payload.revision, payload.action, payload.payload)
    except Exception as exc: raise translate_error(exc) from exc


@router.post("/templates/versions/{version_id}/preview")
def preview(version_id: UUID, payload: PreviewRequest, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.preview(studio_context(context), version_id, payload.evidence)
    except Exception as exc: raise translate_error(exc) from exc


@router.get("/templates/versions/{version_id}/samples")
def samples(version_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context); return {"items": service.repository.samples(context.organization_id, context.company_id, version_id)}


@router.post("/templates/versions/{version_id}/samples", status_code=201)
def add_sample(version_id: UUID, payload: SampleRequest, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try:
        service.add_sample(studio_context(context), version_id, payload.document_id, payload.expected_result, payload.notes)
        return {"status": "ATTACHED"}
    except Exception as exc: raise translate_error(exc) from exc


@router.delete("/templates/versions/{version_id}/samples/{document_id}", status_code=204)
def remove_sample(version_id: UUID, document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    if not service.repository.remove_sample(context.organization_id, context.company_id, version_id, document_id):
        raise HTTPException(404, "Active sample not found")


def execute_background_test(context: RequestContext, version_id: UUID, run_id: UUID) -> None:
    service, _ = services(context); service.execute_test_run(studio_context(context), version_id, run_id)


@router.post("/templates/versions/{version_id}/test-all", status_code=202)
def test_all(version_id: UUID, background_tasks: BackgroundTasks,
             context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try:
        run_id = service.queue_test_run(studio_context(context), version_id)
        background_tasks.add_task(execute_background_test, context, version_id, run_id)
        return {"test_run_id": run_id, "status": "QUEUED"}
    except Exception as exc: raise translate_error(exc) from exc


@router.get("/template-test-runs/{run_id}")
def test_run(run_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context); result = service.repository.test_run(context.organization_id, context.company_id, run_id)
    if not result: raise HTTPException(404, "Template test run not found")
    return result


@router.post("/templates/versions/{version_id}/approve")
def approve(version_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.approve(studio_context(context), version_id)
    except Exception as exc: raise translate_error(exc) from exc


@router.post("/templates/versions/{version_id}/deprecate")
def deprecate(version_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.deprecate(studio_context(context), version_id)
    except Exception as exc: raise translate_error(exc) from exc


@router.get("/templates/versions/{version_id}/export")
def export_version(version_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.export(studio_context(context), version_id)
    except Exception as exc: raise translate_error(exc) from exc


@router.post("/templates/import", status_code=201)
def import_template(payload: ImportRequest, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.import_definition(studio_context(context), payload.payload, payload.family_id)
    except Exception as exc: raise translate_error(exc) from exc


@router.get("/templates/diff")
def version_diff(context: Annotated[RequestContext, Depends(request_context)], old: UUID = Query(), new: UUID = Query()):
    service, _ = services(context)
    try: return service.repository.version_diff(context.organization_id, context.company_id, old, new)
    except Exception as exc: raise translate_error(exc) from exc


@router.post("/template-studio/from-document", status_code=201)
def draft_from_document(payload: DraftRequest, context: Annotated[RequestContext, Depends(request_context)]):
    service, documents = services(context); document = documents.get(context.organization_id, context.company_id, payload.document_id)
    if not document: raise HTTPException(404, "Document not found")
    extraction = documents.extraction(context.organization_id, context.company_id, payload.document_id)
    try: return service.deterministic_draft(studio_context(context), document,
        (extraction or {}).get("normalized_result", {}), payload.candidate_family_id)
    except Exception as exc: raise translate_error(exc) from exc


@router.post("/templates/versions/{version_id}/selection-context")
def selection_context(version_id: UUID, payload: SelectionRequest,
                      context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.selection_context(studio_context(context), version_id, payload.selection)
    except Exception as exc: raise translate_error(exc) from exc


@router.post("/templates/routing-diagnostic")
def routing_diagnostic(payload: RoutingRequest, context: Annotated[RequestContext, Depends(request_context)]):
    del context
    return TemplateStudioService.routing_diagnostic(payload.fingerprint, payload.candidates)


@router.get("/templates/routing-diagnostic/{document_id}")
def routing_diagnostic_document(document_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    from ..document_intelligence.models import FormatFingerprint
    from ..document_intelligence.fingerprint import fingerprint_similarity

    service, _ = services(context)
    try:
        current, stored = service.repository.routing_fingerprints(context.organization_id, context.company_id, document_id)
        def model(item: dict[str, Any]) -> FormatFingerprint:
            features = item["features"]
            return FormatFingerprint(item["signature"], tuple(features.get("anchors", [])), int(features.get("page_count", 0)),
                                     tuple(tuple(value) for value in features.get("dimensions", [])), tuple(features.get("table_headers", [])))
        wanted = model(current)
        candidates = [{"family_id": item["family_id"], "name": item["name"], "version_id": item["version_id"],
                       "similarity": fingerprint_similarity(wanted, model(item))} for item in stored]
        return service.routing_diagnostic({"signature": current["signature"], **current["features"]}, candidates)
    except Exception as exc: raise translate_error(exc) from exc


@router.post("/templates/families/{family_id}/comments", status_code=201)
def add_comment(family_id: UUID, payload: CommentRequest, context: Annotated[RequestContext, Depends(request_context)]):
    service, _ = services(context)
    try: return service.repository.add_comment(context.organization_id, context.company_id, family_id,
        payload.version_id, payload.document_id, context.user_id, payload.note)
    except Exception as exc: raise translate_error(exc) from exc
