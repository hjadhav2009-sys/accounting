from __future__ import annotations

import json
from typing import Any

from .models import DocumentMode, TemplateInvalid


SCHEMA_VERSION = 1
PAGE_POLICIES = {"PAGE_ANY", "PAGE_FIRST", "PAGE_LAST", "PAGE_NUMBER", "TABLE_REPEAT"}
FIELD_KINDS = {"DOCUMENT", "PARTY", "ITEM", "TOTAL", "BANK", "CUSTOM"}
RELATIONSHIPS = {"RIGHT_OF", "LEFT_OF", "BELOW", "ABOVE", "NEAREST", "SAME_LINE"}
MATCH_POLICIES = {"EXACT", "CASE_INSENSITIVE", "NORMALIZED_PUNCTUATION"}
TABLE_TYPES = {"ITEM", "TAX_SUMMARY", "PAYMENT", "BANK", "SUMMARY", "GENERIC"}
ROW_TYPES = {"HEADER", "ITEM", "SUBTOTAL", "TOTAL", "TAX_SUMMARY", "NOTE", "IGNORE"}
TRANSFORMS = {
    "trim", "normalize_whitespace", "remove_currency_symbol", "remove_grouping_comma",
    "parse_decimal", "parse_date", "normalize_percentage",
}
OBJECT_TYPES = {"FIELD", "TABLE", "ANCHOR", "IGNORE_REGION"}
ENGINES = {"VISUAL_RULES", "LEGACY_ADAPTER", "LEGACY_PARSER"}
VALIDATION_PROFILES = {"INVOICE", "MARKETPLACE", "BANK", "STOCK_TRANSFER", "GENERIC"}
MAX_OBJECTS = 1000


def empty_definition(mode: str = "GENERIC") -> dict[str, Any]:
    normalized_mode = DocumentMode(mode).value
    return {
        "schema_version": SCHEMA_VERSION,
        "document_mode": normalized_mode,
        "page_rules": [{"policy": "PAGE_ANY"}],
        "objects": [],
        "derived_fields": [],
        "validation_profile": normalized_mode,
        "metadata": {"assistant": "disabled", "source": "deterministic-draft"},
    }


def _box(value: Any, path: str) -> None:
    if not isinstance(value, dict) or set(value) != {"x0", "y0", "x1", "y1"}:
        raise TemplateInvalid(f"{path} must contain normalized x0,y0,x1,y1")
    try:
        numbers = [float(value[key]) for key in ("x0", "y0", "x1", "y1")]
    except (TypeError, ValueError) as exc:
        raise TemplateInvalid(f"{path} coordinates must be numeric") from exc
    if not all(0 <= number <= 1 for number in numbers) or numbers[0] >= numbers[2] or numbers[1] >= numbers[3]:
        raise TemplateInvalid(f"{path} coordinates must be ordered normalized values")


def _safe_text(value: Any, path: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise TemplateInvalid(f"{path} must be safe text up to {maximum} characters")
    lowered = value.casefold()
    forbidden = ("__import__", "subprocess", "javascript:", "file://", "postgresql://", "drop table", "<script")
    if any(token in lowered for token in forbidden):
        raise TemplateInvalid(f"{path} contains a prohibited executable or resource token")
    return value


def validate_definition(definition: Any) -> dict[str, Any]:
    if not isinstance(definition, dict):
        raise TemplateInvalid("template definition must be an object")
    allowed_top = {"schema_version", "document_mode", "page_rules", "objects", "derived_fields", "validation_profile", "metadata", "fingerprint_rules"}
    unknown = set(definition) - allowed_top
    if unknown:
        raise TemplateInvalid(f"unknown template properties: {sorted(unknown)}")
    if definition.get("schema_version") != SCHEMA_VERSION:
        raise TemplateInvalid(f"unsupported schema_version; expected {SCHEMA_VERSION}")
    try:
        DocumentMode(str(definition.get("document_mode")))
    except ValueError as exc:
        raise TemplateInvalid("unsupported document_mode") from exc
    if definition.get("validation_profile") not in VALIDATION_PROFILES:
        raise TemplateInvalid("unsupported validation_profile")
    page_rules = definition.get("page_rules", [])
    if not isinstance(page_rules, list) or not page_rules:
        raise TemplateInvalid("at least one page rule is required")
    for index, rule in enumerate(page_rules):
        if not isinstance(rule, dict) or rule.get("policy") not in PAGE_POLICIES:
            raise TemplateInvalid(f"page_rules[{index}] has an unsupported policy")
        if rule.get("policy") == "PAGE_NUMBER" and (not isinstance(rule.get("page"), int) or rule["page"] < 1):
            raise TemplateInvalid(f"page_rules[{index}].page must be positive")
    objects = definition.get("objects", [])
    if not isinstance(objects, list) or len(objects) > MAX_OBJECTS:
        raise TemplateInvalid(f"objects must be a list of at most {MAX_OBJECTS}")
    seen: set[str] = set()
    for index, item in enumerate(objects):
        if not isinstance(item, dict):
            raise TemplateInvalid(f"objects[{index}] must be an object")
        object_id = _safe_text(item.get("id"), f"objects[{index}].id", 80)
        if not object_id or object_id in seen:
            raise TemplateInvalid("object ids must be non-empty and unique")
        seen.add(object_id)
        kind = item.get("type")
        if kind not in OBJECT_TYPES:
            raise TemplateInvalid(f"objects[{index}].type is unsupported")
        if item.get("page_policy", "PAGE_ANY") not in PAGE_POLICIES:
            raise TemplateInvalid(f"objects[{index}].page_policy is unsupported")
        if "box" in item:
            _box(item["box"], f"objects[{index}].box")
        if kind in {"FIELD", "TABLE", "IGNORE_REGION"} and "box" not in item:
            raise TemplateInvalid(f"objects[{index}].box is required")
        if kind == "FIELD":
            _safe_text(item.get("field", ""), f"objects[{index}].field", 100)
            if item.get("field_kind", "CUSTOM") not in FIELD_KINDS:
                raise TemplateInvalid(f"objects[{index}].field_kind is unsupported")
            transforms = item.get("transforms", [])
            if not isinstance(transforms, list) or any(transform not in TRANSFORMS for transform in transforms):
                raise TemplateInvalid(f"objects[{index}].transforms contains an unsafe transform")
        elif kind == "ANCHOR":
            _safe_text(item.get("anchor_text", ""), f"objects[{index}].anchor_text", 200)
            if item.get("relationship") not in RELATIONSHIPS or item.get("match_policy", "EXACT") not in MATCH_POLICIES:
                raise TemplateInvalid(f"objects[{index}] has an unsupported anchor policy")
            tolerance = item.get("tolerance", 0)
            if not isinstance(tolerance, (int, float)) or not 0 <= float(tolerance) <= 0.2:
                raise TemplateInvalid(f"objects[{index}].tolerance exceeds the deterministic limit")
        elif kind == "TABLE":
            if item.get("table_type", "GENERIC") not in TABLE_TYPES:
                raise TemplateInvalid(f"objects[{index}].table_type is unsupported")
            columns = item.get("columns", [])
            if not isinstance(columns, list) or len(columns) > 100:
                raise TemplateInvalid(f"objects[{index}].columns is invalid")
            previous = -1.0
            for column_index, column in enumerate(columns):
                boundary = float(column.get("boundary", -1)) if isinstance(column, dict) else -1
                if not 0 <= boundary <= 1 or boundary <= previous:
                    raise TemplateInvalid(f"objects[{index}].columns[{column_index}] boundaries must ascend")
                previous = boundary
                _safe_text(column.get("field", ""), f"objects[{index}].columns[{column_index}].field", 100)
            classifiers = item.get("row_classifiers", [])
            for classifier in classifiers:
                if not isinstance(classifier, dict) or classifier.get("row_type") not in ROW_TYPES:
                    raise TemplateInvalid(f"objects[{index}] has an invalid row classifier")
                _safe_text(classifier.get("text", ""), "row classifier text", 100)
            if item.get("multiline_strategy", "same-cell") not in {"same-cell", "indent", "no-numeric-neighbor", "manual"}:
                raise TemplateInvalid(f"objects[{index}].multiline_strategy is unsupported")
    derived = definition.get("derived_fields", [])
    if not isinstance(derived, list) or len(derived) > 100:
        raise TemplateInvalid("derived_fields is invalid")
    for index, item in enumerate(derived):
        if not isinstance(item, dict):
            raise TemplateInvalid(f"derived_fields[{index}] must be an object")
        _safe_text(item.get("field", ""), f"derived_fields[{index}].field", 100)
        _safe_text(item.get("formula", ""), f"derived_fields[{index}].formula", 300)
        if not isinstance(item.get("inputs", []), list) or not isinstance(item.get("rounding", 2), int):
            raise TemplateInvalid(f"derived_fields[{index}] inputs/rounding are invalid")
    metadata = definition.get("metadata", {})
    if not isinstance(metadata, dict) or len(json.dumps(metadata)) > 20_000:
        raise TemplateInvalid("metadata is invalid or too large")
    # Serialization is a final structural/resource boundary.
    encoded = json.dumps(definition, allow_nan=False)
    if len(encoded) > 1_000_000:
        raise TemplateInvalid("template definition exceeds 1 MB")
    return definition


def sanitized_export(family: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    return {
        "export_schema": "business-automation-template-v1",
        "family": {key: family.get(key) for key in ("name", "description", "supplier", "document_type")},
        "version": {
            "schema_version": version.get("schema_version", SCHEMA_VERSION),
            "validation_profile": version.get("validation_profile", "GENERIC"),
            "engine": version.get("engine", "VISUAL_RULES"),
            "definition": validate_definition(version["definition"]),
        },
    }
