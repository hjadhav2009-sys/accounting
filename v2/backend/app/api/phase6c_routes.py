from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from ..config import get_settings
from ..document_intelligence.models import to_jsonable
from ..domain.enums import Permission, Role
from ..infrastructure.postgres import psycopg_tenant_connection_factory
from ..phase6c import ExecutionMode, IndependentParityCoordinator
from ..phase6c.repository import Phase6CRepository
from ..phase6c.sqlite_migration import ExistingDataMigration, EXPECTED_SQLITE_SHA256
from ..phase6c.v2_native import V2NativeDocumentEngine
from ..security.authorization import AuthorizationService
from .document_routes import RequestContext, request_context, services


router = APIRouter(prefix="/api/v2/phase6c", tags=["phase6c"])
ROOT = Path(__file__).resolve().parents[4]
SQLITE_SOURCE = ROOT / "data" / "business_rules.db"


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: ExecutionMode = ExecutionMode.COMPARE


def _require(context: RequestContext, permission: Permission) -> None:
    if not AuthorizationService().is_allowed(set(context.roles), permission): raise HTTPException(403, "permission denied")


def _factory(context: RequestContext):
    settings = get_settings(); url = settings.postgres_url or settings.database_url
    if not url: raise HTTPException(503, "PostgreSQL is not configured")
    return psycopg_tenant_connection_factory(url, context.organization_id, context.company_id, context.user_id)


def _repository(context: RequestContext) -> Phase6CRepository:
    return Phase6CRepository(_factory(context))


@router.post("/documents/{document_id}/execute")
def execute(document_id: UUID, payload: CompareRequest,
            context: Annotated[RequestContext, Depends(request_context)]):
    _require(context, Permission.DOCUMENT_REVIEW)
    documents, storage = services(context); record = documents.get(context.organization_id, context.company_id, document_id)
    if not record: raise HTTPException(404, "Document not found")
    repository = _repository(context)
    native = V2NativeDocumentEngine(lambda signature: repository.approved_template(
        context.organization_id, context.company_id, signature))
    result = IndependentParityCoordinator(native).execute(payload.mode,
        storage.read(record["storage_key"]), record["original_filename"])
    native_result = result.get("v2")
    if native_result and native_result.get("reason") == "NO_APPROVED_V2_TEMPLATE":
        draft = repository.ensure_v2_draft(context.organization_id, context.company_id, document_id,
                                            context.user_id, native_result["fingerprint"])
        native_result["draft_template"] = draft
    run_id = repository.save_parity(context.organization_id, context.company_id, document_id,
                                    context.user_id, payload.mode.value, result)
    return to_jsonable({"run_id": run_id, **result})


@router.get("/parity")
def parity(context: Annotated[RequestContext, Depends(request_context)]):
    _require(context, Permission.DOCUMENT_VIEW)
    return {"items": to_jsonable(_repository(context).parity_runs(context.organization_id, context.company_id))}


@router.get("/parity/{run_id}")
def parity_detail(run_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    _require(context, Permission.DOCUMENT_VIEW)
    result = _repository(context).parity_run(context.organization_id, context.company_id, run_id)
    if not result: raise HTTPException(404, "Parity run not found")
    return to_jsonable(result)


@router.post("/migration/preview", status_code=201)
def migration_preview(context: Annotated[RequestContext, Depends(request_context)]):
    _require(context, Permission.COMPANY_ADMIN)
    connection = _factory(context)()
    try: report = ExistingDataMigration(connection, context.organization_id, SQLITE_SOURCE).preview()
    finally: connection.rollback(); connection.close()
    preview_id = _repository(context).save_migration_preview(context.organization_id, context.user_id,
        str(SQLITE_SOURCE), report["source_sha256"], EXPECTED_SQLITE_SHA256, report)
    return to_jsonable({"preview_id": preview_id, **report})


@router.get("/migration/previews")
def migration_previews(context: Annotated[RequestContext, Depends(request_context)]):
    _require(context, Permission.COMPANY_ADMIN)
    return {"items": to_jsonable(_repository(context).migration_previews(context.organization_id))}


@router.post("/migration/{preview_id}/apply")
def migration_apply(preview_id: UUID, context: Annotated[RequestContext, Depends(request_context)]):
    _require(context, Permission.COMPANY_ADMIN); repository = _repository(context)
    preview = repository.migration_preview(context.organization_id, preview_id)
    if not preview: raise HTTPException(404, "Migration preview not found")
    if preview["status"] != "PREVIEW": raise HTTPException(409, "Migration preview is stale or already applied")
    if not preview["report"].get("apply_allowed"): raise HTTPException(409, "Migration preview contains blockers")
    if preview["source_sha256"] != EXPECTED_SQLITE_SHA256: raise HTTPException(409, "Source hash is not certified")
    connection = _factory(context)()
    try:
        report = ExistingDataMigration(connection, context.organization_id, SQLITE_SOURCE).apply("Existing Business Automation Data")
    finally: connection.close()
    role_code="OWNER" if Role.OWNER in context.roles else "ADMIN"
    report["company_access_granted"]=repository.grant_imported_company_access(context.organization_id,context.user_id,
        [UUID(value) for value in report["company_ids"].values()],role_code)
    repository.mark_migration_applied(context.organization_id, preview_id, report)
    return to_jsonable({"preview_id": preview_id, "status": "APPLIED", "report": report})
