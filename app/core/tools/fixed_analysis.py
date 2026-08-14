"""固定分析工具（仅按显式 analysis_key 执行；不做中文关键词路由）。"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from app.bi.fixed_queries import FIXED_QUERIES, render_sql
from app.core.tools.clickhouse_tool import run_query


def default_date_range(days: int = 30) -> tuple[str, str]:
    """Demo 数据默认结束于 2026-08-01，与合成脚本一致。"""
    end = date(2026, 8, 1)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def run_fixed_analysis(
    key: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    if key not in FIXED_QUERIES:
        return {"ok": False, "error": f"未知固定分析: {key}", "available": list(FIXED_QUERIES)}
    if not start_date or not end_date:
        start_date, end_date = default_date_range()
    meta = FIXED_QUERIES[key]
    sql = render_sql(meta["sql"], start_date, end_date)
    result = run_query(sql)
    return {
        "ok": result.get("ok", False),
        "analysis_key": key,
        "name": meta["name"],
        "description": meta["description"],
        "start_date": start_date,
        "end_date": end_date,
        **result,
    }


def tool_get_fixed_analysis(key: str, start_date: str = "", end_date: str = "") -> str:
    return json.dumps(
        run_fixed_analysis(key, start_date or None, end_date or None),
        ensure_ascii=False,
    )
