"""查数类工具名集合（delivery_floor / numeric_audit / 贴表共用）。"""

from __future__ import annotations

QUERY_TOOLS = frozenset({"get_fixed_analysis", "db_query"})


def is_query_tool(name: str | None) -> bool:
    return str(name or "") in QUERY_TOOLS
