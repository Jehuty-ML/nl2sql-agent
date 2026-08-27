"""交付完整性薄地板：检测查数证据异常 → 提示 + partial，不硬栏、不丢原文、不打回 LLM。"""

from __future__ import annotations

import json
from typing import Any

from app.core.tools.result_shape import GRAIN_AGGREGATE, GRAIN_FIXED

QUERY_TOOLS = frozenset({"get_fixed_analysis", "db_query"})

NOTICE_NO_OK_QUERY = (
    "【系统提示】本次未产生成功的查数结果，结论请谨慎采信；"
    "请以 Run Log 与工具返回为准，或改用 /dau 等固定分析。"
)

NOTICE_EMPTY_ROWS = (
    "【系统提示】查数已执行但未返回可用数据行，结论请结合口径与空结果自行判断；"
    "请以 Run Log 与工具返回为准。"
)

NOTICE_INCOMPLETE = (
    "【系统提示】查数证据不完备（结果已截断或为明细样本），汇总类结论请谨慎采信；"
    "请以 Run Log 与工具返回为准，或改用固定分析 / 聚合 SQL。"
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
                if "returned_rows" in parsed:
                    return int(parsed["returned_rows"])
                if "row_count" in parsed:
                    return int(parsed["row_count"])
                rows = parsed.get("rows")
                if isinstance(rows, list):
                    return len(rows)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    return None


def _trace_is_complete(entry: dict[str, Any]) -> bool:
    if not entry.get("ok"):
        return False
    if entry.get("truncated"):
        return False
    grain = str(entry.get("grain") or "")
    if grain in (GRAIN_FIXED, GRAIN_AGGREGATE):
        return True
    proj = entry.get("projection") or {}
    return proj.get("kind") == "complete" and not proj.get("incomplete")


def assess_query_evidence(tool_traces: list[dict[str, Any]] | None) -> dict[str, Any]:
    """评估 Agent 工具轨迹中的查数证据。"""
    traces = tool_traces or []
    called = False
    has_ok = False
    has_rows = False
    has_complete = False

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
            if _trace_is_complete(entry):
                has_complete = True

    if has_ok and has_rows and has_complete:
        reason = "none"
    elif has_ok and has_rows:
        reason = "incomplete_evidence"
    elif has_ok:
        reason = "empty_rows"
    else:
        reason = "missing_ok_query"

    return {
        "has_ok_query": has_ok,
        "called_query": called,
        "has_nonempty_rows": has_rows,
        "has_complete_evidence": has_complete,
        "reason": reason,
    }


def apply_delivery_soft_floor(result: dict[str, Any]) -> dict[str, Any]:
    """就地增强 Agent 终态：有异常则加 notice / partial，保留 answer 与 tool_traces。"""
    if not isinstance(result, dict):
        return result
    if result.get("mode") != "agent_loop":
        return result

    assessment = assess_query_evidence(result.get("tool_traces"))
    result["delivery_assessment"] = assessment

    reason = assessment["reason"]
    if reason == "none":
        result.setdefault("status", "success")
        from app.core.agent.numeric_audit import apply_numeric_audit

        return apply_numeric_audit(result)

    if reason == "empty_rows":
        notice = NOTICE_EMPTY_ROWS
    elif reason == "incomplete_evidence":
        notice = NOTICE_INCOMPLETE
    else:
        notice = NOTICE_NO_OK_QUERY

    answer = str(result.get("answer") or "")
    if notice not in answer:
        result["answer"] = f"{notice}\n\n{answer}".strip() if answer else notice

    result["status"] = "partial"
    result["delivery_notice"] = notice
    result["delivery_gate"] = reason
    return result
