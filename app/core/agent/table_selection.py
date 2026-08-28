"""从 tool_traces 选择系统渲染表格。"""

from __future__ import annotations

from typing import Any

from app.core.tools.result_shape import GRAIN_AGGREGATE, GRAIN_FIXED

QUERY_TOOLS = frozenset({"get_fixed_analysis", "db_query"})


def _is_complete_trace(entry: dict[str, Any]) -> bool:
    if not entry.get("ok"):
        return False
    if entry.get("truncated"):
        return False
    grain = str(entry.get("grain") or "")
    if grain in (GRAIN_FIXED, GRAIN_AGGREGATE):
        return True
    proj = entry.get("projection") or {}
    return proj.get("kind") == "complete" and not proj.get("incomplete")


def select_display_tables(
    tool_traces: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """返回 data_tables 列表（按 trace 顺序）。"""
    out: list[dict[str, Any]] = []
    for idx, entry in enumerate(tool_traces or []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("tool") or "") not in QUERY_TOOLS:
            continue
        if not _is_complete_trace(entry):
            continue
        table = entry.get("table")
        if not isinstance(table, dict) or not table.get("rows"):
            continue
        label = str(table.get("name") or table.get("analysis_key") or f"查询 {idx + 1}")
        out.append(
            {
                "label": label,
                "table": table,
                "tool_index": idx,
            }
        )
    return out


def select_primary_table(tool_traces: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """最后一次完备查数的 table（兼容旧 data 字段）。"""
    tables = select_display_tables(tool_traces)
    if not tables:
        return None
    return tables[-1]["table"]
