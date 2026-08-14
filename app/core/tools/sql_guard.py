"""只读 SQL 防护（工具层）。

对齐常见问数 Agent 实践，并强于「仅黑名单」：
1. 必须以 SELECT / WITH 开头
2. 禁止多语句
3. 禁止写操作 / DDL / 权限 / 系统类关键字
4. 缺省自动补 LIMIT
"""

from __future__ import annotations

import re
from typing import Any

# 词边界匹配，降低 "updated_at" 误伤（仍用空格包裹主路径）
_FORBIDDEN = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "TRUNCATE",
    "ALTER",
    "CREATE",
    "REPLACE",
    "ATTACH",
    "DETACH",
    "RENAME",
    "GRANT",
    "REVOKE",
    "OPTIMIZE",
    "SYSTEM",
    "KILL",
    "EXCHANGE",
    "MOVE",
    "WATCH",
]

_FORBIDDEN_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(" + "|".join(_FORBIDDEN) + r")(?![A-Za-z0-9_])"
)


def guard_readonly_sql(sql: str, *, default_limit: int = 500) -> dict[str, Any]:
    """校验并规范化只读 SQL。

    成功返回 {"ok": True, "sql": normalized}
    失败返回 {"ok": False, "error": "...", "sql": original_stripped}
    """
    raw = (sql or "").strip().rstrip(";").strip()
    if not raw:
        return {"ok": False, "error": "SQL 为空", "sql": raw}

    if not re.match(r"(?is)^\s*(SELECT|WITH)\b", raw):
        return {
            "ok": False,
            "error": "只读模式：仅允许 SELECT / WITH … SELECT 查询",
            "sql": raw,
        }

    # 中间出现分号 → 多语句
    if ";" in raw:
        return {
            "ok": False,
            "error": "只读模式：禁止一次提交多条 SQL",
            "sql": raw,
        }

    m = _FORBIDDEN_RE.search(raw)
    if m:
        return {
            "ok": False,
            "error": f"只读模式：禁止关键字 {m.group(1).upper()}",
            "sql": raw,
        }

    normalized = raw
    if not re.search(r"(?i)\bLIMIT\b", normalized):
        normalized = f"{normalized} LIMIT {int(default_limit)}"

    return {"ok": True, "sql": normalized}
