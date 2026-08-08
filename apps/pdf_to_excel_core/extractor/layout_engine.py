from __future__ import annotations

import re
from typing import Optional


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def first_match(pattern: str, text: str, flags: int = re.I | re.S) -> str:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else ""


def money_to_float(value: str) -> float:
    if value is None:
        return 0.0
    value = str(value).replace("₹", "").replace(",", "").strip()
    value = re.sub(r"[^0-9.\-]", "", value)
    try:
        return float(value) if value else 0.0
    except ValueError:
        return 0.0


def norm_rate(value: str | float | int) -> str:
    try:
        f = float(str(value).replace("%", "").strip())
        if f.is_integer():
            return str(int(f))
        return str(f)
    except Exception:
        return str(value).replace("%", "").strip()


def get_section(text: str, start_label: str, end_labels: list[str]) -> str:
    start = re.search(re.escape(start_label), text, re.I)
    if not start:
        return ""
    section = text[start.end():]
    end_positions = []
    for label in end_labels:
        m = re.search(re.escape(label), section, re.I)
        if m:
            end_positions.append(m.start())
    if end_positions:
        section = section[: min(end_positions)]
    return section.strip()
