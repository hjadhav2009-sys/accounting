from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree


DOCUMENT_FIELDS = ("invoice_number", "date", "document_type", "supplier", "row_count", "quantity",
                   "taxable", "tax_amount", "subtotal", "round_off", "invoice_total", "rows", "tax_buckets")


def _normal(value: Any) -> Any:
    if value is None or value == "": return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal("0.0001")).normalize()
    if isinstance(value, str):
        text = " ".join(value.split())
        try: return Decimal(text.replace(",", "").replace("%", "")).quantize(Decimal("0.0001")).normalize()
        except InvalidOperation: return text.casefold()
    if isinstance(value, dict): return {key: _normal(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)): return [_normal(item) for item in value]
    return str(value)


def compare_documents(reference: dict[str, Any], native: dict[str, Any]) -> dict[str, Any]:
    if native.get("status") == "BLOCKED":
        return {"status": "BLOCKED", "fields": [], "matches": 0, "differences": 0,
                "unexplained_differences": 0, "reason": native.get("reason")}
    left, right = reference.get("canonical", {}), native.get("canonical", {})
    fields = []
    for name in DOCUMENT_FIELDS:
        legacy_value, v2_value = left.get(name), right.get(name)
        if legacy_value in (None, "") and v2_value not in (None, ""): status = "MISSING_LEGACY"
        elif v2_value in (None, "") and legacy_value not in (None, ""): status = "MISSING_V2"
        else: status = "MATCH" if _normal(legacy_value) == _normal(v2_value) else "DIFFERENCE"
        fields.append({"field": name, "legacy": legacy_value, "v2": v2_value, "status": status})
    differences = sum(item["status"] != "MATCH" for item in fields)
    return {"status": "MATCH" if not differences else "DIFFERENCE", "fields": fields,
            "matches": len(fields) - differences, "differences": differences,
            "unexplained_differences": differences}


def compare_excel(reference_rows: list[dict[str, Any]], native_rows: list[dict[str, Any]]) -> dict[str, Any]:
    reference_columns = list(reference_rows[0]) if reference_rows else []
    native_columns = list(native_rows[0]) if native_rows else []
    schema_match = reference_columns == native_columns
    values_match = _normal(reference_rows) == _normal(native_rows)
    return {"status": "MATCH" if schema_match and values_match else "DIFFERENCE",
            "schema": {"legacy": reference_columns, "v2": native_columns, "status": "MATCH" if schema_match else "DIFFERENCE"},
            "values_status": "MATCH" if values_match else "DIFFERENCE"}


def _xml_semantics(content: bytes | str) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(content)
    vouchers = []
    for voucher in root.iter():
        if voucher.tag.split("}")[-1].upper() != "VOUCHER": continue
        values: dict[str, Any] = {"voucher_type": voucher.attrib.get("VCHTYPE", "")}
        ledgers = []
        for node in voucher.iter():
            tag = node.tag.split("}")[-1].upper(); text = (node.text or "").strip()
            if tag in {"DATE", "PARTYLEDGERNAME", "VOUCHERNUMBER", "REFERENCE"}: values[tag.casefold()] = text
            if tag == "LEDGERNAME": ledgers.append(text)
            if tag == "AMOUNT": ledgers.append(text)
        values["ledger_amounts"] = sorted(ledgers)
        vouchers.append(values)
    return sorted(vouchers, key=lambda item: repr(item))


def compare_xml(reference_xml: bytes | str, native_xml: bytes | str) -> dict[str, Any]:
    left, right = _xml_semantics(reference_xml), _xml_semantics(native_xml)
    return {"status": "MATCH" if _normal(left) == _normal(right) else "DIFFERENCE",
            "legacy": left, "v2": right, "formatting_ignored": True}
