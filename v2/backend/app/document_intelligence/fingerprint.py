from __future__ import annotations

import hashlib
import json
import re

from .models import DocumentPage, FormatFingerprint


def _tokens(text: str) -> tuple[str, ...]:
    normalized = re.sub(r"\s+", " ", text).casefold()
    words = re.findall(r"[a-z]{3,}|\b(?:gstin|invoice|statement|credit|debit|tax|total|quantity)\b", normalized)
    return tuple(sorted(set(words[:250])))


def create_format_fingerprint(pages: tuple[DocumentPage, ...]) -> FormatFingerprint:
    text = "\n".join(page.text for page in pages)
    anchors = _tokens(text)
    dimensions = tuple((round(page.width), round(page.height)) for page in pages)
    headers = tuple(sorted(set(
        " | ".join(cell.text.strip().casefold() for cell in row.cells if cell.text.strip())
        for page in pages for table in page.tables for row in table.rows[:1]
    )))
    payload = json.dumps({"anchors": anchors, "page_count": len(pages), "dimensions": dimensions, "headers": headers}, separators=(",", ":"))
    return FormatFingerprint(hashlib.sha256(payload.encode("utf-8")).hexdigest(), anchors, len(pages), dimensions, headers)


def fingerprint_similarity(left: FormatFingerprint, right: FormatFingerprint) -> float:
    left_set, right_set = set(left.anchors), set(right.anchors)
    anchor_score = len(left_set & right_set) / max(1, len(left_set | right_set))
    page_score = 1.0 if left.page_count == right.page_count else max(0.0, 1.0 - abs(left.page_count - right.page_count) * 0.2)
    dimension_pairs = zip(left.dimensions, right.dimensions)
    dimension_score = sum(1 for a, b in dimension_pairs if abs(a[0] - b[0]) <= 5 and abs(a[1] - b[1]) <= 5) / max(1, max(len(left.dimensions), len(right.dimensions)))
    return round(anchor_score * 0.7 + page_score * 0.15 + dimension_score * 0.15, 4)
