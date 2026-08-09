from __future__ import annotations

import re
from typing import Any

from shared.database import norm_platform as _legacy_norm_platform
from shared.database import norm_text as _legacy_norm_text


MATCH_TYPES=frozenset({"contains","smart_contains","equals","starts_with","regex"})


def normalize_text(value:Any)->str:return _legacy_norm_text(value)
def normalize_platform(value:Any)->str:return _legacy_norm_platform(value)


def _smart(value:Any)->str:return " ".join(re.sub(r"[^a-z0-9]+"," ",str(value or "").casefold()).split())


def mapping_matches(text:Any,pattern:Any,match_type:Any)->bool:
    source=str(text or "");wanted=normalize_text(pattern);kind=normalize_text(match_type).casefold() or "contains"
    if not wanted or kind not in MATCH_TYPES:return False
    if kind=="smart_contains":return _smart(wanted) in _smart(source)
    if kind=="equals":return source.strip().casefold()==wanted.casefold()
    if kind=="starts_with":return source.strip().casefold().startswith(wanted.casefold())
    if kind=="regex":
        try:return re.search(wanted,source,re.IGNORECASE) is not None
        except re.error:return False
    return wanted.casefold() in source.casefold()
