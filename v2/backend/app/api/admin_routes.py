from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field

from ..config import get_settings
from ..domain.enums import Permission,Role
from ..infrastructure.postgres import psycopg_tenant_connection_factory
from ..infrastructure.postgres import psycopg_connection_factory
from ..infrastructure.service_health import collect_health
from ..infrastructure.retention import retention_policy
from ..security.authorization import AuthorizationService
from ..security.user_admin import UserAdminRepository
from .document_routes import RequestContext,request_context


router=APIRouter(prefix="/api/v2/admin",tags=["administration"])


class Assignment(BaseModel):
    model_config=ConfigDict(extra="forbid")
    company_id:UUID;role:Role

class UserCreate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    email:str=Field(min_length=3,max_length=320);display_name:str=Field(min_length=2,max_length=160)
    temporary_password:str=Field(min_length=12,max_length=128);assignments:list[Assignment]=Field(min_length=1,max_length=100)

class RoleChange(BaseModel):
    model_config=ConfigDict(extra="forbid")
    company_id:UUID;role:Role

class PasswordReset(BaseModel):
    model_config=ConfigDict(extra="forbid")
    temporary_password:str=Field(min_length=12,max_length=128)


def service(context:RequestContext)->UserAdminRepository:
    if not AuthorizationService().is_allowed(set(context.roles),Permission.USER_ADMIN):raise HTTPException(403,"permission denied")
    settings=get_settings();url=settings.postgres_url or settings.database_url
    if not url:raise HTTPException(503,"PostgreSQL is not configured")
    return UserAdminRepository(psycopg_tenant_connection_factory(url,context.organization_id,context.company_id,context.user_id))


@router.get("/users")
def users(context:Annotated[RequestContext,Depends(request_context)]):return {"items":service(context).list_users(context.organization_id)}

@router.post("/users",status_code=201)
def create_user(payload:UserCreate,context:Annotated[RequestContext,Depends(request_context)]):
    try:return service(context).create_user(context.organization_id,context.user_id,payload.email,payload.display_name,
        payload.temporary_password,[(item.company_id,item.role) for item in payload.assignments])
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

@router.post("/users/{user_id}/disable")
def disable_user(user_id:UUID,context:Annotated[RequestContext,Depends(request_context)]):
    if user_id==context.user_id:raise HTTPException(409,"cannot disable the current user")
    if not service(context).set_status(context.organization_id,context.user_id,user_id,"DISABLED"):raise HTTPException(404,"user not found")
    return {"id":user_id,"status":"DISABLED"}

@router.post("/users/{user_id}/reactivate")
def reactivate_user(user_id:UUID,context:Annotated[RequestContext,Depends(request_context)]):
    if not service(context).set_status(context.organization_id,context.user_id,user_id,"ACTIVE"):raise HTTPException(404,"user not found")
    return {"id":user_id,"status":"ACTIVE"}

@router.put("/users/{user_id}/role")
def change_role(user_id:UUID,payload:RoleChange,context:Annotated[RequestContext,Depends(request_context)]):
    if not service(context).replace_company_role(context.organization_id,context.user_id,user_id,payload.company_id,payload.role):raise HTTPException(404,"user or company not found")
    return {"id":user_id,"company_id":payload.company_id,"role":payload.role}

@router.post("/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id:UUID,context:Annotated[RequestContext,Depends(request_context)]):
    return {"id":user_id,"revoked":service(context).revoke_sessions(context.organization_id,context.user_id,user_id)}

@router.post("/users/{user_id}/reset-password")
def reset_password(user_id:UUID,payload:PasswordReset,context:Annotated[RequestContext,Depends(request_context)]):
    if not service(context).reset_password(context.organization_id,context.user_id,user_id,payload.temporary_password):raise HTTPException(404,"user not found")
    return {"id":user_id,"must_change_password":True,"sessions_revoked":True}


@router.get("/health")
def health(context:Annotated[RequestContext,Depends(request_context)]):
    service(context)
    settings=get_settings();url=settings.postgres_url or settings.database_url
    result=collect_health(settings,psycopg_connection_factory(url) if url else None);result["retention_policy"]=retention_policy(settings);return result
