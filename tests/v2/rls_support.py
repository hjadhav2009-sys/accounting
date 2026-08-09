from __future__ import annotations

from uuid import UUID

from v2.backend.app.infrastructure.postgres import psycopg_tenant_connection_factory


def set_tenant(cursor, organization_id: UUID, company_id: UUID) -> None:
    cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(organization_id),))
    cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company_id),))


def tenant_factory(url: str, organization_id: UUID, company_id: UUID, user_id: UUID | None = None):
    return psycopg_tenant_connection_factory(url,organization_id,company_id,user_id)
