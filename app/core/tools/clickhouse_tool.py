"""ClickHouse 客户端封装（唯一分析库）。"""

from __future__ import annotations

import json
from typing import Any

import clickhouse_connect

from app.config import settings


_client = None


def get_client():
    global _client
    if _client is None:
        _client = clickhouse_connect.get_client(
            host=settings.ch_host,
            port=settings.ch_port,
            username=settings.ch_user,
            password=settings.ch_password,
            database=settings.ch_database,
        )
    return _client


def reset_client() -> None:
    global _client
    _client = None


def ping() -> bool:
    try:
        get_client().query("SELECT 1")
        return True
    except Exception:
        return False


def run_query(sql: str, limit: int = 500) -> dict[str, Any]:
    """执行只读 SQL，返回列名与行数据。"""
    sql_strip = sql.strip().rstrip(";")
    # 简单防护：禁止明显写操作
    lowered = sql_strip.lower()
    for bad in (" drop ", " truncate ", " alter ", " insert ", " delete ", " create "):
        if bad in f" {lowered} ":
            return {"ok": False, "error": f"禁止执行写操作类语句: {bad.strip()}", "sql": sql_strip}

    client = get_client()
    result = client.query(sql_strip)
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows[:limit]]
    # JSON 友好：处理 date 等
    safe_rows = []
    for r in rows:
        safe_rows.append({k: _jsonable(v) for k, v in r.items()})
    return {
        "ok": True,
        "sql": sql_strip,
        "columns": list(result.column_names),
        "row_count": len(safe_rows),
        "rows": safe_rows,
    }


def _jsonable(v: Any) -> Any:
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", errors="replace")
    return v


def tool_db_query(sql: str) -> str:
    """供 Agent 调用的工具：返回 JSON 字符串。"""
    return json.dumps(run_query(sql), ensure_ascii=False)
