"""ClickHouse 客户端封装（唯一分析库 · 只读查询入口）。"""

from __future__ import annotations

import json
from typing import Any

import clickhouse_connect

from app.config import settings
from app.core.tools.sql_guard import guard_readonly_sql


_client = None


def get_client():
    """Agent 查询客户端：强制 settings.readonly=1。"""
    global _client
    if _client is None:
        _client = clickhouse_connect.get_client(
            host=settings.ch_host,
            port=settings.ch_port,
            username=settings.ch_user,
            password=settings.ch_password,
            database=settings.ch_database,
            settings={"readonly": 1},
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
    """执行只读 SQL，返回列名与行数据；CK 错误以 ok=false 返回，不抛到 Agent 外。"""
    guarded = guard_readonly_sql(sql, default_limit=limit)
    if not guarded["ok"]:
        return {
            "ok": False,
            "error": guarded["error"],
            "sql": guarded.get("sql") or sql,
        }

    sql_strip = guarded["sql"]
    try:
        client = get_client()
        # 单次查询再带 readonly，防止客户端缓存 settings 被改写
        result = client.query(sql_strip, settings={"readonly": 1})
        rows = [dict(zip(result.column_names, row)) for row in result.result_rows[:limit]]
        safe_rows = []
        for r in rows:
            safe_rows.append({k: _jsonable(v) for k, v in r.items()})
        return {
            "ok": True,
            "sql": sql_strip,
            "columns": list(result.column_names),
            "row_count": len(safe_rows),
            "rows": safe_rows,
            "readonly": True,
        }
    except Exception as e:
        err = str(e)
        hint = ""
        if "readonly" in err.lower() or "Cannot execute query in readonly mode" in err:
            hint = " 当前为 ClickHouse 只读会话/只读账号，禁止任何写库或 DDL。"
        if "channel" in err.lower() and "register_channel" not in sql_strip.lower():
            hint += " users/events 渠道字段名为 register_channel，不是 channel。"
        if "unknown identifier" in err.lower() or "UNKNOWN_IDENTIFIER" in err:
            hint += (
                " 可用表：events(distinct_id,identity_login_id,event,dt,app_id,lib,"
                "path_id,lesson_id,register_channel,…)、"
                "users(distinct_id,login_id,register_dt,register_channel,app_id,last_active_dt)。"
            )
        return {
            "ok": False,
            "error": err[:1200],
            "hint": hint.strip() or None,
            "sql": sql_strip,
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
