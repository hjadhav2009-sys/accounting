from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter,Depends,File,HTTPException,Response,UploadFile
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field

from ..config import get_settings
from ..domain.enums import Permission
from ..infrastructure.postgres import psycopg_tenant_connection_factory
from ..security.authorization import AuthorizationService
from ..security.masters import MasterRepository
from .document_routes import RequestContext,request_context

router=APIRouter(prefix="/api/v2/masters",tags=["masters"])

class BankMaster(BaseModel):
    model_config=ConfigDict(extra="forbid");account_hint:str=Field(min_length=4,max_length=8);bank_ledger:str=Field(min_length=1,max_length=240)
class PartyMaster(BaseModel):
    model_config=ConfigDict(extra="forbid");platform:str=Field(min_length=1,max_length=80);party_ledger:str=Field(min_length=1,max_length=240);party_gstin:str=Field(default="",max_length=15);state:str=Field(default="",max_length=100)
class GstMaster(BaseModel):
    model_config=ConfigDict(extra="forbid");tax_type:str=Field(pattern="^(CGST|SGST|IGST)$");ledger_name:str=Field(min_length=1,max_length=240)
class VoucherMaster(BaseModel):
    model_config=ConfigDict(extra="forbid");platform:str=Field(min_length=1,max_length=80);document_type:str=Field(min_length=1,max_length=80);tally_voucher_type:str=Field(min_length=1,max_length=80);sign_mode:str=Field(pattern="^(charge|reverse)$")

def repository(context:RequestContext,permission:Permission=Permission.COMPANY_ADMIN)->MasterRepository:
    if not AuthorizationService().is_allowed(set(context.roles),permission):raise HTTPException(403,"permission denied")
    settings=get_settings();url=settings.postgres_url or settings.database_url
    if not url:raise HTTPException(503,"PostgreSQL is not configured")
    return MasterRepository(psycopg_tenant_connection_factory(url,context.organization_id,context.company_id,context.user_id))

@router.get("")
def snapshot(context:Annotated[RequestContext,Depends(request_context)]):return repository(context,Permission.DOCUMENT_VIEW).snapshot(context.organization_id,context.company_id)
@router.post("/bank-accounts")
def bank(payload:BankMaster,context:Annotated[RequestContext,Depends(request_context)]):
    try:item=repository(context).save_bank(context.organization_id,context.company_id,context.user_id,payload.account_hint,payload.bank_ledger)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    return {"id":item,"status":"SAVED"}
@router.post("/party-ledgers")
def party(payload:PartyMaster,context:Annotated[RequestContext,Depends(request_context)]):return {"id":repository(context).save_party(context.organization_id,context.company_id,context.user_id,payload.platform,payload.party_ledger,payload.party_gstin,payload.state),"status":"SAVED"}
@router.post("/gst-ledgers")
def gst(payload:GstMaster,context:Annotated[RequestContext,Depends(request_context)]):return {"id":repository(context).save_gst(context.organization_id,context.company_id,context.user_id,payload.tax_type,payload.ledger_name),"status":"SAVED"}
@router.post("/voucher-rules")
def voucher(payload:VoucherMaster,context:Annotated[RequestContext,Depends(request_context)]):return {"id":repository(context).save_voucher(context.organization_id,context.company_id,context.user_id,payload.platform,payload.document_type,payload.tally_voucher_type,payload.sign_mode),"status":"SAVED"}

@router.get("/mappings/export")
def export_mappings(context:Annotated[RequestContext,Depends(request_context)]):
    content=repository(context,Permission.MAPPING_EDIT).mapping_workbook(context.organization_id,context.company_id)
    return Response(content,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":'attachment; filename="ledger_mappings.xlsx"'})

@router.post("/mappings/import-preview")
async def preview_mappings(file:Annotated[UploadFile,File()],context:Annotated[RequestContext,Depends(request_context)]):
    if not (file.filename or "").casefold().endswith(".xlsx"):raise HTTPException(422,"mapping import requires an XLSX workbook")
    try:return repository(context,Permission.MAPPING_EDIT).preview_mapping_workbook(context.organization_id,context.company_id,context.user_id,await file.read())
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

@router.post("/mappings/import/{preview_id}/apply")
def apply_mappings(preview_id:UUID,context:Annotated[RequestContext,Depends(request_context)]):
    try:return repository(context,Permission.MAPPING_EDIT).apply_mapping_preview(context.organization_id,context.company_id,context.user_id,preview_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
