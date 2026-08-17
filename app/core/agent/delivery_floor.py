"""交付完整性薄地板：检测查数证据异常 → 提示 + partial，不硬栏、不丢原文、不打回 LLM。

对齐 docs/LumenLearn-改造计划.md §6.3。
"""

from __future__ import annotations

import json
from typing import Any

QUERY_TOOLS = frozenset({"get_fixed_analysis", "db_query"})

NOTICE_NO_OK_QUERY = (
    "【系统提示】本次未产生成功的查数结果，结论请谨慎采信；"
    "请以 Run Log 与工具返回为准，或改用 /dau 等固定分析。"
)

NOTICE_EMPTY_ROWS = (
    "【系统提示】查数已执行但未返回可用数据行，结论请结合口径与空结果自行判断；"
    "请以 Run Log 与工具返回为准。"
)


def _parse_ok_from_trace(entry: dict[str, Any]) -> bool | None:
    """从 tool_traces 条目推断 ok；优先显式字段。"""
    if "ok" in entry and entry["ok"] is not None:
        return bool(entry["ok"])
    preview = entry.get("result_preview")
    if isinstance(preview, str) and preview.strip().startswith("{"):
        try:
            parsed = json.loads(preview)
            if isinstance(parsed, dict) and "ok" in parsed:
                return bool(parsed.get("ok"))
        except (json.JSONDecodeError, TypeError):
            return None
    if entry.get("table"):
        return True
    return None


def _row_count(entry: dict[str, Any]) -> int | None:
    table = entry.get("table")
    if isinstance(table, dict):
        if "row_count" in table:
            try:
                return int(table["row_count"])
            except (TypeError, ValueError):
                pass
        rows = table.get("rows")
        if isinstance(rows, list):
            return len(rows)
    preview = entry.get("result_preview")
    if isinstance(preview, str) and preview.strip().startswith("{"):
        try:
            parsed = json.loads(preview)
            if isinstance(parsed, dict):
                if "row_count" in parsed:
                    return int(parsed["row_count"])
                rows = parsed.get("rows")
                if isinstance(rows, list):
                    return len(rows)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    return None


def assess_query_evidence(tool_traces: list[dict[str, Any]] | None) -> dict[str, Any]:
    """评估 Agent 工具轨迹中的查数证据。

    返回:
      has_ok_query: 至少一次查数工具 ok=true（允许 0 行）
      called_query: 是否调用过查数工具
      has_nonempty_rows: 是否有 ok 且带行的结果
      reason: none | missing_ok_query | empty_rows
    """
    traces = tool_traces or []
    called = False
    has_ok = False
    has_rows = False

    for entry in traces:
        if not isinstance(entry, dict):
            continue
        tool = str(entry.get("tool") or "")
        if tool not in QUERY_TOOLS:
            continue
        called = True
        ok = _parse_ok_from_trace(entry)
        if ok is True:
            has_ok = True
            rc = _row_count(entry)
            if rc is None and entry.get("table"):
                has_rows = True
            elif rc is not None and rc > 0:
                has_rows = True

    if has_ok and has_rows:
        reason = "none"
    elif has_ok:
        reason = "empty_rows"
    else:
        reason = "missing_ok_query"

    return {
        "has_ok_query": has_ok,
        "called_query": called,
        "has_nonempty_rows": has_rows,
        "reason": reason,
    }


def apply_delivery_soft_floor(result: dict[str, Any]) -> dict[str, Any]:
    """就地增强 Agent 终态：有异常则加 notice / partial，保留 answer 与 tool_traces。

    非 agent_loop 或已有完整查数证据时原样返回。
    """
    if not isinstance(result, dict):
        return result
    if result.get("mode") != "agent_loop":
        return result

    assessment = assess_query_evidence(result.get("tool_traces"))
    result["delivery_assessment"] = assessment

    reason = assessment["reason"]
    if reason == "none":
        result.setdefault("status", "success")
        return result

    notice = NOTICE_EMPTY_ROWS if reason == "empty_rows" else NOTICE_NO_OK_QUERY
    answer = str(result.get("answer") or "")
    # 已带同款提示则不重复堆叠
    if notice not in answer:
        result["answer"] = f"{notice}\n\n{answer}".strip() if answer else notice

    result["status"] = "partial"
    result["delivery_notice"] = notice
    result["delivery_gate"] = reason
    return result
