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


def _center(box:dict[str,float])->tuple[float,float]:return ((box["x0"]+box["x1"])/2,(box["y0"]+box["y1"])/2)


def _overlap(first:dict[str,float],second:dict[str,float])->float:
    width=max(0.0,min(first["x1"],second["x1"])-max(first["x0"],second["x0"]))
    height=max(0.0,min(first["y1"],second["y1"])-max(first["y0"],second["y0"]))
    return width*height


def _relationship_score(anchor:dict[str,float],candidate:dict[str,float],relationship:str,tolerance:float)->float|None:
    ax,ay=_center(anchor);cx,cy=_center(candidate);vertical=min(anchor["y1"],candidate["y1"])-max(anchor["y0"],candidate["y0"])
    horizontal=min(anchor["x1"],candidate["x1"])-max(anchor["x0"],candidate["x0"])
    if relationship=="RIGHT_OF" and not (candidate["x0"]>=anchor["x1"]-tolerance and (vertical>=0 or abs(cy-ay)<=tolerance)):return None
    if relationship=="LEFT_OF" and not (candidate["x1"]<=anchor["x0"]+tolerance and (vertical>=0 or abs(cy-ay)<=tolerance)):return None
    if relationship=="BELOW" and not (candidate["y0"]>=anchor["y1"]-tolerance and (horizontal>=0 or abs(cx-ax)<=tolerance)):return None
    if relationship=="ABOVE" and not (candidate["y1"]<=anchor["y0"]+tolerance and (horizontal>=0 or abs(cx-ax)<=tolerance)):return None
    if relationship=="SAME_LINE" and not (vertical>=0 or abs(cy-ay)<=tolerance):return None
    distance=((cx-ax)**2+(cy-ay)**2)**.5
    return distance+(abs(cy-ay) if relationship in {"RIGHT_OF","LEFT_OF","SAME_LINE"} else abs(cx-ax))


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
            if not box:return False
            area=max((box["x1"]-box["x0"])*(box["y1"]-box["y0"]),1e-9);cx,cy=_center(box)
            return any(on_page(region,page_number) and (_overlap(box,region["box"])/area>=.5 or
                (region["box"]["x0"]<=cx<=region["box"]["x1"] and region["box"]["y0"]<=cy<=region["box"]["y1"])) for region in ignored)

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
            def field_score(item:dict[str,Any])->tuple[float,float,float]:
                source_box=_normalized_box(item.get("source") or {}) or rule["box"]
                overlap=_overlap(source_box,rule["box"]);area=max((source_box["x1"]-source_box["x0"])*(source_box["y1"]-source_box["y0"]),1e-9)
                sx,sy=_center(source_box);rx,ry=_center(rule["box"])
                return (overlap/area,-((sx-rx)**2+(sy-ry)**2),float(item.get("confidence") or 0))
            chosen = max(candidates, key=field_score)
            value: Any = chosen.get("value", chosen.get("text", ""))
            for transform in rule.get("transforms", []):
                value = apply_transform(value, transform)
            fields.append({"field": rule["field"], "value": str(value), "source": chosen.get("source"),
                           "rule_id": rule["id"], "why": "best overlap and distance within mapped region",
                           "transforms": rule.get("transforms", []), "derived": False})

        text_blocks: list[dict[str, Any]] = []
        for page in pages:
            page_number = int(page.get("page_number") or 1)
            for block in page.get("text_blocks", page.get("blocks", [])):
                box=block.get("bounding_box") or block.get("box")
                if isinstance(box,dict) and not all(key in box for key in ("page_width","page_height")):
                    box={**box,"page_width":page.get("width",1),"page_height":page.get("height",1)}
                text_blocks.append({**block,"bounding_box":box,"page_number":page_number})
        for anchor in (item for item in definition["objects"] if item["type"] == "ANCHOR"):
            wanted = anchor["anchor_text"]
            policy = anchor.get("match_policy", "EXACT")
            matches = []
            for block in text_blocks:
                actual = str(block.get("text", ""))
                matched = actual == wanted if policy == "EXACT" else actual.casefold() == wanted.casefold()
                if policy == "NORMALIZED_PUNCTUATION":
                    matched = re.sub(r"[^\w]+", "", actual).casefold() == re.sub(r"[^\w]+", "", wanted).casefold()
                block_box=_normalized_box({"bounding_box":block.get("bounding_box")})
                if matched and on_page(anchor, block["page_number"]) and block_box and not is_ignored(block["page_number"],block_box): matches.append(block)
            if not matches: warnings.append(f"anchor '{wanted}' not found")
            else:
                candidates=[];tolerance=float(anchor.get("tolerance",0));relationship=anchor["relationship"]
                for matched_anchor in matches:
                    anchor_box=_normalized_box({"bounding_box":matched_anchor.get("bounding_box")})
                    if not anchor_box:continue
                    for candidate in text_blocks:
                        if candidate is matched_anchor or candidate["page_number"]!=matched_anchor["page_number"]:continue
                        candidate_box=_normalized_box({"bounding_box":candidate.get("bounding_box")})
                        if not candidate_box or is_ignored(candidate["page_number"],candidate_box):continue
                        score=_relationship_score(anchor_box,candidate_box,relationship,tolerance)
                        if score is not None and str(candidate.get("text") or "").strip():candidates.append((score,candidate))
                if not candidates:warnings.append(f"anchor '{wanted}' has no {relationship} value evidence")
                else:
                    _,chosen=min(candidates,key=lambda item:item[0])
                    fields.append({"field":anchor.get("field","anchor_value"),"value":str(chosen.get("text") or "").strip(),
                        "source":{"page_number":chosen["page_number"],"bounding_box":chosen.get("bounding_box")},
                        "rule_id":anchor["id"],"why":f"nearest geometric {relationship} evidence for anchor '{wanted}'","derived":False})

        for table_rule in (item for item in definition["objects"] if item["type"] == "TABLE"):
            extracted_rows: list[dict[str, Any]] = []
            for page in pages:
                page_number = int(page.get("page_number") or 1)
                if not on_page(table_rule, page_number): continue
                for table in page.get("tables", []):
                    table_box = _normalized_box({"bounding_box": table.get("bounding_box")})
                    if not table_box or not _intersects(table_box, table_rule["box"]) or is_ignored(page_number,table_box): continue
                    for row in table.get("rows", []):
                        cells = row.get("cells", [])
                        mapped={};previous=0.0
                        for column in table_rule.get("columns",[]):
                            boundary=float(column["boundary"]);selected=[]
                            if "source_index" in column:
                                source_index=int(column["source_index"]);selected=[cells[source_index]] if source_index<len(cells) else []
                            else:
                                for cell in cells:
                                    cell_box=_normalized_box({"bounding_box":cell.get("bounding_box")})
                                    if not cell_box or is_ignored(page_number,cell_box):continue
                                    relative=(_center(cell_box)[0]-table_rule["box"]["x0"])/max(table_rule["box"]["x1"]-table_rule["box"]["x0"],1e-9)
                                    if previous<=relative<=(boundary if boundary==1 else boundary):selected.append(cell)
                            mapped[column["field"]]=" ".join(str(cell.get("text","")).strip() for cell in selected if str(cell.get("text","")).strip())
                            previous=boundary
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
