from __future__ import annotations

from ..domain.enums import Permission, Role


ALL_PERMISSIONS = frozenset(Permission)
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: ALL_PERMISSIONS,
    Role.ADMIN: ALL_PERMISSIONS,
    Role.ACCOUNTANT: frozenset({
        Permission.DOCUMENT_UPLOAD, Permission.DOCUMENT_VIEW, Permission.DOCUMENT_REVIEW,
        Permission.BANK_PROCESS, Permission.MARKETPLACE_PROCESS, Permission.XML_EXPORT,
        Permission.EXCEL_EXPORT, Permission.MAPPING_EDIT,
    }),
    Role.OPERATOR: frozenset({
        Permission.DOCUMENT_UPLOAD, Permission.DOCUMENT_VIEW, Permission.BANK_PROCESS,
        Permission.MARKETPLACE_PROCESS, Permission.EXCEL_EXPORT,
    }),
    Role.REVIEWER: frozenset({
        Permission.DOCUMENT_VIEW, Permission.DOCUMENT_REVIEW, Permission.TEMPLATE_CREATE,
        Permission.TEMPLATE_APPROVE,
    }),
    Role.VIEWER: frozenset({Permission.DOCUMENT_VIEW}),
}


class AuthorizationService:
    def is_allowed(self, roles: set[Role], permission: Permission) -> bool:
        return any(permission in ROLE_PERMISSIONS.get(role, frozenset()) for role in roles)

    def require(self, roles: set[Role], permission: Permission) -> None:
        if not self.is_allowed(roles, permission):
            raise PermissionError(f"permission denied: {permission}")
