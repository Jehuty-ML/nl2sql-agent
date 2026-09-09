"""SQL 抽象化 → pattern_id（仅归一日期/数字；不硬合并不同业务过滤）。

动态 SQL 变体是否该合成一个 skill，交给 proposer 的 LLM 异步判断，
而不是在指纹层「硬蹭」成同一 pattern。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


_DATE_LIT = re.compile(
    r"toDate\(\s*'20\d{2}-\d{2}-\d{2}'\s*\)|'20\d{2}-\d{2}-\d{2}'",
    re.IGNORECASE,
)
_NUM_LIT = re.compile(r"(?<![A-Za-z_])\b\d+(?:\.\d+)?\b")
_WS = re.compile(r"\s+")


def abstract_sql(sql: str) -> str:
    """把可复用 SQL 归一成模板形态（日期/数字占位）。"""
    s = (sql or "").strip()
    s = _DATE_LIT.sub("{date}", s)
    s = re.sub(r"(?i)\bLIMIT\s+\d+", "LIMIT {n}", s)
    s = _NUM_LIT.sub("{n}", s)
    s = _WS.sub(" ", s).strip().lower()
    return s


def pattern_id_from_sql(sql: str, columns: list[str] | None = None) -> str:
    abs_sql = abstract_sql(sql)
    cols = ",".join(sorted(str(c) for c in (columns or []) if c))
    raw = f"{abs_sql}|{cols}" if cols else abs_sql
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def sql_to_fixed_template(sql: str) -> str:
    """尽量把成功 SQL 改写成带 {start_date}/{end_date} 的固定分析模板。"""
    s = (sql or "").strip().rstrip(";").strip()
    s = re.sub(
        r"toDate\(\s*'20\d{2}-\d{2}-\d{2}'\s*\)",
        "{start_date}",
        s,
        count=1,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"toDate\(\s*'20\d{2}-\d{2}-\d{2}'\s*\)",
        "{end_date}",
        s,
        count=1,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"'20\d{2}-\d{2}-\d{2}'", "{start_date}", s, count=1)
    s = re.sub(r"'20\d{2}-\d{2}-\d{2}'", "{end_date}", s, count=1)
    if "{start_date}" in s and "{end_date}" not in s:
        parts = s.split("{start_date}")
        if len(parts) >= 3:
            s = (
                parts[0]
                + "{start_date}"
                + parts[1]
                + "{end_date}"
                + "{start_date}".join(parts[2:])
            )
    return s


def columns_from_trace(entry: dict[str, Any]) -> list[str]:
    table = entry.get("table") or {}
    cols = table.get("columns")
    if isinstance(cols, list) and cols:
        return [str(c) for c in cols]
    rows = table.get("rows")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return [str(k) for k in rows[0].keys()]
    return []


def sql_from_trace(entry: dict[str, Any]) -> str:
    table = entry.get("table") or {}
    if isinstance(table, dict) and table.get("sql"):
        return str(table["sql"])
    preview = entry.get("result_preview")
    if isinstance(preview, str) and preview.strip().startswith("{"):
        try:
            import json

            parsed = json.loads(preview)
            if isinstance(parsed, dict) and parsed.get("sql"):
                return str(parsed["sql"])
        except (json.JSONDecodeError, TypeError):
            pass
    args = entry.get("args") or {}
    if isinstance(args, dict) and args.get("sql"):
        return str(args["sql"])
    return ""
