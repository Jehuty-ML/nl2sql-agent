"""内置 FIXED / slash + promoted overlay 合并。"""

from __future__ import annotations

from typing import Any

from app.bi import fixed_dashboard as fd
from app.bi import fixed_queries as fq
from app.core.evolution import store


def get_fixed_queries() -> dict[str, dict[str, Any]]:
    """内置 + overlay（overlay 同名覆盖）。"""
    merged = dict(fq.FIXED_QUERIES)
    overlay = store.load_overlay()
    extra = overlay.get("fixed_queries") or {}
    if isinstance(extra, dict):
        for k, v in extra.items():
            if isinstance(v, dict) and v.get("sql"):
                merged[str(k)] = v
    return merged


def get_dashboard_commands() -> dict[str, dict[str, Any]]:
    merged = dict(fd.FIXED_DASHBOARD_COMMANDS)
    overlay = store.load_overlay()
    extra = overlay.get("dashboard_commands") or {}
    if isinstance(extra, dict):
        for k, v in extra.items():
            if isinstance(v, dict) and v.get("analysis_key"):
                merged[str(k)] = v
    return merged


def get_slash_aliases() -> dict[str, str]:
    merged = dict(fd.SLASH_ALIASES)
    overlay = store.load_overlay()
    extra = overlay.get("slash_aliases") or {}
    if isinstance(extra, dict):
        for k, v in extra.items():
            merged[str(k)] = str(v)
    return merged


def fixed_query_keys() -> list[str]:
    return list(get_fixed_queries().keys())
