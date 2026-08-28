"""查数工具结果 schema 归一化（grain / truncated / returned_rows）。"""

from __future__ import annotations

from typing import Any

from app.core.json_safe import json_safe

GRAIN_FIXED = "fixed"
GRAIN_AGGREGATE = "aggregate"
GRAIN_DETAIL = "detail"

SAMPLE_HINT = (
    "此为截断样本或明细查询，不可用于汇总类结论。"
    "请改用 get_fixed_analysis 或 SELECT 维度, count() ... GROUP BY 维度。"
)


def _row_list(payload: dict[str, Any]) -> list[Any]:
    rows = payload.get("rows")
    return rows if isinstance(rows, list) else []


def enrich_query_result(
    payload: dict[str, Any],
    *,
    grain: str | None = None,
    limit_applied: int | None = None,
) -> dict[str, Any]:
    """为成功/失败的查数结果补齐 spec 字段（就地修改并返回）。"""
    if not isinstance(payload, dict):
        return payload

    # 先 scrub NaN，避免进入 traces / HTTP
    cleaned = json_safe(payload)
    if cleaned is not payload and isinstance(cleaned, dict):
        payload.clear()
        payload.update(cleaned)

    if grain:
        payload["grain"] = grain

    rows = _row_list(payload)
    returned = len(rows)
    payload["returned_rows"] = returned
    # 向后兼容
    payload["row_count"] = returned

    if payload.get("ok"):
        truncated = bool(payload.get("truncated"))
        if limit_applied is not None and returned >= limit_applied:
            truncated = True
        payload["truncated"] = truncated
        if not payload.get("grain"):
            payload["grain"] = GRAIN_DETAIL
    else:
        payload.setdefault("truncated", False)
        payload.setdefault("grain", grain or GRAIN_DETAIL)

    return payload


def is_complete_evidence(payload: dict[str, Any]) -> bool:
    """是否为可结案完备包。"""
    if not payload.get("ok"):
        return False
    if payload.get("truncated"):
        return False
    grain = str(payload.get("grain") or "")
    return grain in (GRAIN_FIXED, GRAIN_AGGREGATE)


def trace_from_payload(
    fn: str,
    args: dict[str, Any],
    payload: dict[str, Any],
    *,
    projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建 tool_trace 条目（含 table / grain / projection）。"""
    entry: dict[str, Any] = {
        "tool": fn,
        "args": args,
        "ok": bool(payload.get("ok")) if "ok" in payload else None,
        "grain": payload.get("grain"),
        "truncated": bool(payload.get("truncated")),
        "returned_rows": payload.get("returned_rows"),
    }
    if projection:
        entry["projection"] = projection
    preview = payload
    try:
        import json

        entry["result_preview"] = json.dumps(preview, ensure_ascii=False)[:800]
    except Exception:
        entry["result_preview"] = str(preview)[:800]

    rows = _row_list(payload)
    if payload.get("ok") and rows:
        entry["row_count"] = payload.get("returned_rows", len(rows))
        entry["table"] = {
            "analysis_key": payload.get("analysis_key"),
            "name": payload.get("name"),
            "row_count": payload.get("returned_rows", len(rows)),
            "columns": payload.get("columns") or list(rows[0].keys()),
            "rows": rows[:20],
            "sql": payload.get("sql"),
            "grain": payload.get("grain"),
            "truncated": payload.get("truncated"),
        }
    return entry
