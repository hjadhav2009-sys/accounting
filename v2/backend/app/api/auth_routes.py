from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..infrastructure.postgres import psycopg_connection_factory
from ..security.sessions import AuthenticationFailed, SessionRepository


router=APIRouter(prefix="/api/v2/auth",tags=["authentication"])


class LoginRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    organization: str=Field(min_length=1,max_length=200)
    email: str=Field(min_length=3,max_length=320)
    password: str=Field(min_length=1,max_length=128)
    company_id: UUID | None=None


def repository() -> SessionRepository:
    settings=get_settings();url=settings.postgres_url or settings.database_url
    if not url: raise HTTPException(503,"authentication database is not configured")
    return SessionRepository(psycopg_connection_factory(url),idle_minutes=settings.session_idle_minutes,
                             absolute_hours=settings.session_absolute_hours)


@router.post("/login")
def login(payload: LoginRequest,request: Request,response: Response):
    settings=get_settings()
    try:
        issued=repository().authenticate(payload.email,payload.password,payload.company_id,
            request.headers.get("user-agent",""),request.client.host if request.client else "",
            organization_name=payload.organization)
    except AuthenticationFailed as exc:
        raise HTTPException(401,"invalid credentials") from exc
    response.set_cookie(settings.session_cookie_name,issued.token,httponly=True,secure=settings.session_cookie_secure,
        samesite="lax",path="/",max_age=settings.session_absolute_hours*3600)
    identity=issued.identity
    return {"user":{"id":identity.user_id,"email":identity.email,"display_name":identity.display_name},
            "organization_id":identity.organization_id,"company_id":identity.company_id,
            "roles":sorted(role.value for role in identity.roles),"csrf_token":issued.csrf_token,
            "expires_at":issued.absolute_expires_at}


@router.post("/logout")
def logout(request:Request,response:Response,csrf_token:Annotated[str,Header(alias="X-CSRF-Token")]):
    settings=get_settings();token=request.cookies.get(settings.session_cookie_name,"")
    identity=repository().resolve(token,None,csrf_token)
    if not identity or not identity.csrf_token_valid: raise HTTPException(403,"CSRF validation failed")
    repository().revoke(token,identity.user_id)
    response.delete_cookie(settings.session_cookie_name,path="/",secure=settings.session_cookie_secure,samesite="lax")
    return {"status":"LOGGED_OUT"}


@router.get("/session")
def session(request:Request,company_id:Annotated[UUID | None,Header(alias="X-Company-ID")]=None):
    settings=get_settings();identity=repository().resolve(request.cookies.get(settings.session_cookie_name,""),company_id)
    if not identity: raise HTTPException(401,"authentication required")
    return {"user":{"id":identity.user_id,"email":identity.email,"display_name":identity.display_name},
            "organization_id":identity.organization_id,"company_id":identity.company_id,
            "roles":sorted(role.value for role in identity.roles)}


@router.get("/companies")
def companies(request:Request):
    settings=get_settings();items=repository().authorized_companies(request.cookies.get(settings.session_cookie_name,""))
    if not items:raise HTTPException(401,"authentication required")
    return {"items":items}
