from __future__ import annotations

import ast
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .models import TemplateInvalid
from .schema import TRANSFORMS, validate_definition


def apply_transform(value: Any, transform: str) -> Any:
    if transform not in TRANSFORMS:
        raise TemplateInvalid(f"unsafe transform: {transform}")
    text = str(value or "")
    if transform == "trim":
        return text.strip()
    if transform == "normalize_whitespace":
        return " ".join(text.split())
    if transform == "remove_currency_symbol":
        return re.sub(r"[₹$€£]", "", text).strip()
    if transform == "remove_grouping_comma":
        return re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
    if transform == "parse_decimal":
        try:
            return Decimal(text.strip().replace(",", ""))
        except InvalidOperation as exc:
            raise TemplateInvalid(f"cannot parse decimal: {text}") from exc
    if transform == "parse_date":
        for pattern in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(text.strip(), pattern).date().isoformat()
            except ValueError:
                continue
        raise TemplateInvalid(f"cannot parse date: {text}")
    if transform == "normalize_percentage":
        try:
            return Decimal(text.strip().removesuffix("%").replace(",", ""))
        except InvalidOperation as exc:
            raise TemplateInvalid(f"cannot parse percentage: {text}") from exc
    raise TemplateInvalid(f"unsupported transform: {transform}")


def safe_formula(formula: str, values: dict[str, Any], rounding: int = 2) -> Decimal:
    """Evaluate arithmetic only. No calls, attributes, subscripts, or executable code."""
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise TemplateInvalid("invalid derived formula") from exc

    def visit(node: ast.AST) -> Decimal:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
            try:
                return Decimal(str(node.value))
            except InvalidOperation as exc:
                raise TemplateInvalid("invalid numeric constant") from exc
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise TemplateInvalid(f"missing formula input: {node.id}")
            try:
                return Decimal(str(values[node.id]))
            except InvalidOperation as exc:
                raise TemplateInvalid(f"non-numeric formula input: {node.id}") from exc
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = visit(node.operand)
            return result if isinstance(node.op, ast.UAdd) else -result
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if right == 0: raise TemplateInvalid("division by zero")
            return left / right
        raise TemplateInvalid("formula contains prohibited syntax")

    if len(list(ast.walk(tree))) > 100:
        raise TemplateInvalid("formula is too complex")
    result = visit(tree)
    quantum = Decimal(1).scaleb(-max(0, min(rounding, 8)))
    return result.quantize(quantum, rounding=ROUND_HALF_UP)


def _normalized_box(source: dict[str, Any] | None) -> dict[str, float] | None:
    if not source:
        return None
    box = source.get("bounding_box") or source.get("box")
    if not isinstance(box, dict):
        return None
    if all(key in box for key in ("page_width", "page_height")) and box.get("page_width") and box.get("page_height"):
        return {"x0": float(box["x0"]) / float(box["page_width"]), "y0": float(box["y0"]) / float(box["page_height"]),
                "x1": float(box["x1"]) / float(box["page_width"]), "y1": float(box["y1"]) / float(box["page_height"])}
    if all(key in box for key in ("x0", "y0", "x1", "y1")):
        values = {key: float(box[key]) for key in ("x0", "y0", "x1", "y1")}
        return values if all(0 <= value <= 1 for value in values.values()) else None
    return None


def _intersects(first: dict[str, float], second: dict[str, float]) -> bool:
    return not (first["x1"] < second["x0"] or first["x0"] > second["x1"] or first["y1"] < second["y0"] or first["y0"] > second["y1"])


class TemplateRuleEngine:
    """Deterministic extraction over certified page evidence; never executes template code."""

    def extract(self, definition: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        validate_definition(definition)
        fields: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        warnings: list[str] = []
        pages = evidence.get("pages", []) if isinstance(evidence, dict) else []
        source_fields = evidence.get("fields", []) if isinstance(evidence, dict) else []
        ignored = [item for item in definition["objects"] if item["type"] == "IGNORE_REGION"]

        def on_page(item: dict[str, Any], page_number: int) -> bool:
            policy = item.get("page_policy", "PAGE_ANY")
            if policy in {"PAGE_ANY", "TABLE_REPEAT"}: return True
            if policy == "PAGE_FIRST": return page_number == 1
            if policy == "PAGE_LAST": return page_number == max(1, len(pages))
            return page_number == item.get("page", 1)

        def is_ignored(page_number: int, box: dict[str, float] | None) -> bool:
            return bool(box and any(on_page(region, page_number) and _intersects(box, region["box"]) for region in ignored))

        for rule in definition["objects"]:
            if rule["type"] != "FIELD":
                continue
            candidates: list[dict[str, Any]] = []
            for source in source_fields:
                reference = source.get("source") or {}
                page_number = int(reference.get("page_number") or 1)
                source_box = _normalized_box(reference)
                if on_page(rule, page_number) and source_box and _intersects(source_box, rule["box"]) and not is_ignored(page_number, source_box):
                    candidates.append(source)
            if not candidates:
                warnings.append(f"{rule['field']}: no source in mapped region")
                continue
            chosen = max(candidates, key=lambda item: float(item.get("confidence") or 0))
            value: Any = chosen.get("value", chosen.get("text", ""))
            for transform in rule.get("transforms", []):
                value = apply_transform(value, transform)
            fields.append({"field": rule["field"], "value": str(value), "source": chosen.get("source"),
                           "rule_id": rule["id"], "why": "highest-confidence evidence intersecting mapped region",
                           "transforms": rule.get("transforms", []), "derived": False})

        text_blocks: list[dict[str, Any]] = []
        for page in pages:
            page_number = int(page.get("page_number") or 1)
            for block in page.get("text_blocks", page.get("blocks", [])):
                text_blocks.append({**block, "page_number": page_number})
        for anchor in (item for item in definition["objects"] if item["type"] == "ANCHOR"):
            wanted = anchor["anchor_text"]
            policy = anchor.get("match_policy", "EXACT")
            matches = []
            for block in text_blocks:
                actual = str(block.get("text", ""))
                matched = actual == wanted if policy == "EXACT" else actual.casefold() == wanted.casefold()
                if policy == "NORMALIZED_PUNCTUATION":
                    matched = re.sub(r"[^\w]+", "", actual).casefold() == re.sub(r"[^\w]+", "", wanted).casefold()
                if matched and on_page(anchor, block["page_number"]): matches.append(block)
            if not matches: warnings.append(f"anchor '{wanted}' not found")
            else: fields.append({"field": anchor.get("field", "anchor_value"), "value": anchor.get("sample_value", ""),
                "source": {"page_number": matches[0]["page_number"], "bounding_box": matches[0].get("bounding_box")},
                "rule_id": anchor["id"], "why": f"{anchor['relationship']} anchor '{wanted}'", "derived": False})

        for table_rule in (item for item in definition["objects"] if item["type"] == "TABLE"):
            extracted_rows: list[dict[str, Any]] = []
            for page in pages:
                page_number = int(page.get("page_number") or 1)
                if not on_page(table_rule, page_number): continue
                for table in page.get("tables", []):
                    table_box = _normalized_box({"bounding_box": table.get("bounding_box")})
                    if not table_box or not _intersects(table_box, table_rule["box"]): continue
                    for row in table.get("rows", []):
                        cells = row.get("cells", [])
                        mapped = {column["field"]: (cells[index].get("text", "") if index < len(cells) else "")
                                  for index, column in enumerate(table_rule.get("columns", []))}
                        joined = " ".join(str(cell.get("text", "")) for cell in cells)
                        row_type = "ITEM"
                        for classifier in table_rule.get("row_classifiers", []):
                            if joined.casefold().startswith(classifier.get("text", "").casefold()): row_type = classifier["row_type"]
                        if row_type != "IGNORE": extracted_rows.append({"row_type": row_type, "values": mapped, "source": {"page_number": page_number, "bounding_box": row.get("bounding_box")}})
            strategy = table_rule.get("multiline_strategy", "same-cell")
            if strategy in {"indent", "no-numeric-neighbor"}:
                merged: list[dict[str, Any]] = []
                for row in extracted_rows:
                    values = row["values"]
                    text_fields = [key for key in values if key in {"item_name", "narration", "description"}]
                    numeric_fields = [key for key in values if key not in text_fields]
                    continuation = row["row_type"] == "ITEM" and bool(text_fields) and any(str(values[key]).strip() for key in text_fields) and not any(str(values[key]).strip() for key in numeric_fields)
                    if continuation and merged and merged[-1]["row_type"] == "ITEM":
                        for key in text_fields:
                            addition = str(values[key]).strip()
                            if addition: merged[-1]["values"][key] = " ".join(filter(None, [str(merged[-1]["values"].get(key, "")).strip(), addition]))
                        merged[-1].setdefault("continuation_sources", []).append(row["source"])
                    else:
                        merged.append(row)
                extracted_rows = merged
            tables.append({"id": table_rule["id"], "table_type": table_rule.get("table_type", "GENERIC"), "rows": extracted_rows,
                           "repeating": table_rule.get("repeating", True)})

        values = {field["field"]: field["value"] for field in fields}
        for derived in definition.get("derived_fields", []):
            inputs = {name: values[name] for name in derived.get("inputs", []) if name in values}
            if len(inputs) != len(derived.get("inputs", [])):
                warnings.append(f"{derived['field']}: missing derived input")
                continue
            value = safe_formula(derived["formula"], inputs, derived.get("rounding", 2))
            fields.append({"field": derived["field"], "value": str(value), "source": None, "rule_id": None,
                           "why": f"explicit formula: {derived['formula']}", "derived": True, "inputs": derived.get("inputs", [])})

        tax_rows = [row for table in tables if table["table_type"] == "TAX_SUMMARY" for row in table["rows"]]
        item_rows = [row for table in tables if table["table_type"] in {"ITEM", "BANK"} for row in table["rows"] if row["row_type"] == "ITEM"]
        return {"fields": fields, "tables": tables, "item_rows": item_rows, "tax_buckets": tax_rows,
                "warnings": warnings, "source_trace": True, "engine": "deterministic-visual-rules-v1"}

    def compare_golden(self, actual: dict[str, Any], expected: dict[str, Any] | None) -> dict[str, Any]:
        if not expected:
            return {"status": "REVIEW", "reason": "NO_GOLDEN_OUTPUT", "matches": 0, "differences": []}
        differences: list[dict[str, Any]] = []
        actual_fields = {item["field"]: item.get("value") for item in actual.get("fields", [])}
        expected_fields = expected.get("fields", {})
        for name, value in expected_fields.items():
            if str(actual_fields.get(name, "")) != str(value):
                differences.append({"path": f"fields.{name}", "expected": str(value), "actual": str(actual_fields.get(name, ""))})
        for key in ("item_rows", "tax_buckets"):
            if key in expected and actual.get(key, []) != expected[key]:
                differences.append({"path": key, "expected_count": len(expected[key]), "actual_count": len(actual.get(key, []))})
        return {"status": "VERIFIED" if not differences else "BLOCKED", "matches": len(expected_fields) - sum(1 for item in differences if item["path"].startswith("fields.")),
                "differences": differences}
