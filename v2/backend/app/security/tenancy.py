from __future__ import annotations

from uuid import UUID

from ..domain.models import CompanyAccess


class TenantAccessService:
    def require_company(self, access: CompanyAccess, organization_id: UUID, company_id: UUID) -> None:
        if access.organization_id != organization_id or access.company_id != company_id:
            raise PermissionError("tenant access denied")
