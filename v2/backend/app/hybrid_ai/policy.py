from __future__ import annotations

from dataclasses import dataclass

from .models import AiMode, PrivacyMode, PROHIBITED_INTENTS, TenantContext


class PolicyDenied(PermissionError): pass


@dataclass(frozen=True)
class RouteDecision:
    provider: str
    reason: str
    cloud_allowed: bool


class AiPolicyService:
    def authorize_mode(self, context: TenantContext, mode: AiMode, privacy: PrivacyMode) -> None:
        if mode == AiMode.FULL_CLOUD_DOCUMENT_ANALYSIS and "ADMIN" not in context.roles:
            raise PolicyDenied("full cloud document analysis is admin-only")
        if privacy == PrivacyMode.OFF_ADMIN_ONLY and "ADMIN" not in context.roles:
            raise PolicyDenied("privacy-off mode is admin-only")

    def route(self, mode: AiMode, *, local_healthy: bool, cloud_configured: bool,
              requires_vision: bool = False) -> RouteDecision:
        if local_healthy and not requires_vision:
            return RouteDecision("LOCAL", "LOCAL_CAPABLE_AND_HEALTHY", False)
        if mode == AiMode.LOCAL_ONLY:
            return RouteDecision("NONE", "LOCAL_ONLY_RUNTIME_UNAVAILABLE", False)
        if cloud_configured:
            reason = "VISION_CAPABILITY_REQUIRED" if requires_vision else "LOCAL_RUNTIME_UNAVAILABLE"
            return RouteDecision("CLOUD", reason, True)
        return RouteDecision("NONE", "NO_AUTHORIZED_RUNTIME_AVAILABLE", False)

    @staticmethod
    def require_domain_intent(intent: str) -> None:
        normalized = intent.strip().lower()
        if normalized in PROHIBITED_INTENTS:
            raise PolicyDenied(f"intent is prohibited: {normalized}")
        if normalized not in {"draft_template", "improve_mapping", "explain_validation", "compare_formats", "suggest_ledger"}:
            raise PolicyDenied("assistant is restricted to document-template and accounting review tasks")
