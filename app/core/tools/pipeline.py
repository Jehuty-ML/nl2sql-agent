"""工具执行流水线：pre → execute → post。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from app.config import settings
from app.core.agent.tool_projection import project_result_string
from app.core.tools.result_shape import enrich_query_result
from app.core.tools.sql_classifier import classify_sql, detail_reject_hint


@dataclass
class PreResult:
    blocked: bool
    result_json: str = ""


class ToolPipeline:
    """查数工具 pre/post；execute 仍由注册表执行。"""

    def __init__(self, tools: dict[str, Callable[..., str]] | None = None) -> None:
        self._tools = tools or {}

    def set_tools(self, tools: dict[str, Callable[..., str]]) -> None:
        self._tools = tools

    def pre_execute(self, name: str, args: dict[str, Any]) -> PreResult:
        if name != "db_query":
            return PreResult(blocked=False)

        sql = str(args.get("sql") or "").strip()
        if not sql:
            return PreResult(
                blocked=True,
                result_json=json.dumps(
                    {"ok": False, "error": "SQL 为空", "sql": ""},
                    ensure_ascii=False,
                ),
            )

        grain = classify_sql(sql)
        if settings.reject_detail_sql and grain == "detail":
            return PreResult(
                blocked=True,
                result_json=json.dumps(
                    {
                        "ok": False,
                        "error": "只读模式：明细 SQL 已被策略拒绝",
                        "hint": detail_reject_hint(),
                        "grain": grain,
                        "sql": sql,
                    },
                    ensure_ascii=False,
                ),
            )
        return PreResult(blocked=False)

    def execute(self, name: str, args: dict[str, Any]) -> str:
        if name not in self._tools:
            return json.dumps(
                {"ok": False, "error": f"未知工具 {name}"},
                ensure_ascii=False,
            )
        try:
            return self._tools[name](**args)
        except TypeError as e:
            return json.dumps(
                {"ok": False, "error": f"工具参数错误: {e}", "args": args},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"ok": False, "error": f"工具执行异常: {e}"},
                ensure_ascii=False,
            )

    def post_execute(self, name: str, args: dict[str, Any], full_result: str) -> tuple[str, str, dict[str, Any]]:
        """返回 (full_result, model_content, projection_meta)。"""
        try:
            parsed = json.loads(full_result)
        except (json.JSONDecodeError, TypeError):
            return full_result, full_result, {"kind": "raw", "incomplete": True}

        if isinstance(parsed, dict) and name == "db_query" and parsed.get("ok"):
            grain = classify_sql(str(parsed.get("sql") or args.get("sql") or ""))
            limit = 500
            enrich_query_result(parsed, grain=grain, limit_applied=limit)
            full_result = json.dumps(parsed, ensure_ascii=False, allow_nan=False)
        elif isinstance(parsed, dict) and name == "get_fixed_analysis":
            enrich_query_result(parsed, grain="fixed")

        _, model_str, meta = project_result_string(full_result)
        return full_result, model_str, meta


_pipeline: ToolPipeline | None = None


def get_tool_pipeline() -> ToolPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ToolPipeline()
    return _pipeline
