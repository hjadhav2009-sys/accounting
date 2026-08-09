from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ..template_studio.models import StudioContext, TemplateInvalid
from ..template_studio.service import TemplateStudioService
from .models import AiAction


ACTION_MAP = {
    "create_field": "create_field_mapping", "update_field": "update_field_mapping",
    "delete_field": "delete_field_mapping", "create_table": "create_table_rule",
    "update_table": "update_column_mapping", "create_anchor": "create_anchor",
    "create_ignore_region": "set_ignore_region",
}
FIELD_KINDS = frozenset({"DOCUMENT","PARTY","ITEM","TOTAL","BANK","CUSTOM"})
TABLE_TYPES = frozenset({"ITEM","TAX_SUMMARY","PAYMENT","BANK","SUMMARY","GENERIC"})


@dataclass(frozen=True)
class AppliedDraftAction:
    saved: dict[str, Any]
    preview: dict[str, Any]
    human_approval_required: bool = True


class TemplateActionAdapter:
    """Converts validated AI proposals into existing draft-only Studio actions."""

    def __init__(self, studio: TemplateStudioService) -> None: self.studio = studio

    def apply(self, context: StudioContext, version_id: UUID, expected_revision: int,
              action: AiAction, selection: dict[str, Any], evidence: dict[str, Any]) -> AppliedDraftAction:
        studio_action = ACTION_MAP.get(action.action)
        if not studio_action: raise TemplateInvalid("AI action is not mapped to Template Studio")
        payload: dict[str, Any] = {}
        if action.action in {"create_field", "create_table", "create_ignore_region"}:
            box = selection.get("box")
            if not isinstance(box, dict): raise TemplateInvalid("a user-selected bounding box is required")
            payload["box"] = box
        if action.action == "create_field":
            field_kind = str(action.payload.get("role") or "CUSTOM").upper()
            payload.update({"field": str(action.payload.get("field") or "custom_field")[:100],
                            "field_kind": field_kind if field_kind in FIELD_KINDS else "CUSTOM"})
        elif action.action == "create_table":
            columns = selection.get("columns")
            if not isinstance(columns, list) or not columns: raise TemplateInvalid("selected table columns are required")
            table_type = str(action.payload.get("table") or "GENERIC").upper()
            payload.update({"table_type": table_type if table_type in TABLE_TYPES else "GENERIC", "columns": columns})
        elif action.action == "create_anchor":
            payload.update({"field":str(action.payload.get("field") or "custom_field")[:100],
                            "anchor_text":str(action.payload.get("anchor") or action.payload.get("source") or "")[:200]})
        elif action.action in {"update_field", "delete_field", "update_table"}:
            object_id = selection.get("object_id")
            if not object_id: raise TemplateInvalid("an existing selected object is required")
            payload["id"] = str(object_id)[:80]
            if action.action == "update_field" and action.payload.get("field"):
                payload["field"] = str(action.payload["field"])[:100]
            if action.action == "update_table":
                columns = selection.get("columns")
                if not isinstance(columns,list): raise TemplateInvalid("selected columns are required")
                payload["columns"] = columns
        saved = self.studio.action(context,version_id,expected_revision,studio_action,payload)
        preview = self.studio.preview(context,version_id,evidence)
        return AppliedDraftAction(saved,preview)
