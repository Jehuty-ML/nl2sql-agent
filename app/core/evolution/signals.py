"""从 run 结果抽取进化信号并写入经验库。"""

from __future__ import annotations

import re
import time
from typing import Any

from app.config import settings
from app.core.evolution import store
from app.core.evolution.sql_fingerprint import (
    columns_from_trace,
    pattern_id_from_sql,
    sql_from_trace,
    sql_to_fixed_template,
)
from app.core.tools.result_shape import GRAIN_AGGREGATE, GRAIN_FIXED


def _clip(text: str, n: int = 200) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _error_class(entry: dict[str, Any]) -> str:
    if entry.get("truncated") or str(entry.get("grain") or "") == "detail":
        return "incomplete_or_detail"
    blob = _trace_error_blob(entry).lower()
    if (
        "unknown" in blob
        or "不存在" in blob
        or "no such" in blob
        or "unknown_identifier" in blob
        or "code: 47" in blob
    ):
        return "unknown_column_or_table"
    if "readonly" in blob or "禁止" in blob:
        return "readonly_or_guard"
    if "empty" in blob or entry.get("ok") and not entry.get("table"):
        return "empty_or_failed"
    return "query_failed"


def _trace_error_blob(entry: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("error", "result_preview", "hint"):
        val = entry.get(key)
        if val:
            parts.append(str(val))
    table = entry.get("table")
    if isinstance(table, dict) and table.get("error"):
        parts.append(str(table.get("error")))
    args = entry.get("args") if isinstance(entry.get("args"), dict) else {}
    if args.get("sql"):
        parts.append(str(args.get("sql")))
    return "\n".join(parts)


_UNKNOWN_IDENT = re.compile(
    r"Unknown (?:expression or function )?identifier ['`]?([A-Za-z_][\w]*)['`]?",
    re.IGNORECASE,
)
_FROM_TABLE = re.compile(r"\bFROM\s+([A-Za-z_][\w]*)", re.IGNORECASE)


def _schema_lesson_from_error(blob: str) -> str:
    """从 CH / 工具报错提炼可注入的短教训（列名踩坑）。"""
    m = _UNKNOWN_IDENT.search(blob)
    bad_col = m.group(1) if m else ""
    tm = _FROM_TABLE.search(blob)
    table = tm.group(1).lower() if tm else ""

    # Demo 库常见错列纠正
    fixes = {
        ("events", "login_id"): "events 表登录字段是 identity_login_id（不是 login_id；login_id 在 users 表）",
        ("events", "channel"): "events/users 渠道字段是 register_channel（不是 channel）",
        ("users", "channel"): "users 渠道字段是 register_channel（不是 channel）",
        ("events", "user_id"): "events 用户字段用 distinct_id / identity_login_id（不是 user_id）",
    }
    if table and bad_col:
        specific = fixes.get((table, bad_col.lower()))
        if specific:
            return specific
        return f"{table} 表没有列 {bad_col}；请对照可用字段改写 SQL，勿臆造列名。"
    if bad_col:
        if bad_col.lower() == "login_id":
            return (
                "若查 events 活跃/登录，用 identity_login_id；login_id 只在 users 表。"
            )
        return f"未知列/标识符 {bad_col}；勿臆造列名，events 常用 identity_login_id / distinct_id / event / dt / lib。"
    return ""


def _tip_for_negative(error_class: str, hint: str, *, error_blob: str = "") -> str:
    defaults = {
        "incomplete_or_detail": (
            "汇总类问题禁止明细/截断 SQL；请用 GROUP BY 聚合或 get_fixed_analysis。"
        ),
        "unknown_column_or_table": (
            "勿臆造列名；events 登录字段是 identity_login_id；渠道是 register_channel。"
        ),
        "readonly_or_guard": "db_query 仅允许单条 SELECT/WITH；禁止写操作与多语句。",
        "empty_or_failed": (
            "空结果时检查日期是否在 Demo 窗口 2026-05-04~2026-08-01；"
            "固定分析默认勿传日期。"
        ),
        "missing_ok_query": "回答前必须先成功调用 get_fixed_analysis 或 db_query。",
    }
    lesson = _schema_lesson_from_error(error_blob or hint or "")
    if error_class == "unknown_column_or_table" and lesson:
        return _clip(lesson, 200)
    base = defaults.get(error_class, "查数失败时根据 error/hint 改写 SQL 再试。")
    if lesson:
        return _clip(f"{base}（{lesson}）", 200)
    if hint and "ClickHouse" not in hint and len(hint) < 120:
        return _clip(f"{base}（提示：{hint}）", 200)
    return base


def harvest_signals(
    *,
    task_id: str,
    query: str,
    result: dict[str, Any],
    session_id: str = "",
) -> dict[str, Any]:
    """同步收获：写 jsonl + 更新正/负例；返回摘要供测试。"""
    if not settings.enable_evolution:
        return {"skipped": True}

    mode = str(result.get("mode") or "")
    status = str(result.get("status") or "")
    assessment = result.get("delivery_assessment") or {}
    reason = str(assessment.get("reason") or result.get("delivery_gate") or "")
    traces = result.get("tool_traces") or []
    numeric = result.get("numeric_audit") or {}
    tool_count = len([t for t in traces if isinstance(t, dict)])

    event = {
        "ts": time.time(),
        "task_id": task_id,
        "session_id": session_id or "",
        "query": _clip(query, 240),
        "mode": mode,
        "status": status,
        "delivery_reason": reason,
        "tool_count": tool_count,
        "numeric_warn": bool(numeric.get("flagged") or numeric.get("warned")),
    }
    store.append_jsonl("signals.jsonl", event)

    summary: dict[str, Any] = {"event": event, "positive": [], "negative": []}

    if mode != "agent_loop":
        _update_session_turn(session_id, query, result, None)
        return summary

    # 正例：完备成功的查数
    if reason == "none" or (status == "success" and assessment.get("has_complete_evidence")):
        for entry in traces:
            if not isinstance(entry, dict) or not entry.get("ok"):
                continue
            tool = str(entry.get("tool") or "")
            grain = str(entry.get("grain") or "")
            if tool == "get_fixed_analysis":
                key = str((entry.get("args") or {}).get("key") or entry.get("analysis_key") or "")
                if key:
                    # 仅记观测，不写入/注入「偏好」（易干扰工具选择）
                    summary["positive"].append({"kind": "fixed", "key": key})
                continue
            if tool != "db_query":
                continue
            if grain not in (GRAIN_AGGREGATE, GRAIN_FIXED) or entry.get("truncated"):
                continue
            sql = sql_from_trace(entry)
            if not sql:
                continue
            cols = columns_from_trace(entry)
            pid = pattern_id_from_sql(sql, cols)
            _bump_positive_pattern(pid, sql, cols, query)
            summary["positive"].append({"kind": "db_query", "pattern_id": pid})

    # 负例
    tip_key_for_patch = ""
    if reason and reason != "none":
        tip_key = reason
        if reason == "incomplete_evidence":
            tip_key = "incomplete_or_detail"
        elif reason == "empty_rows":
            tip_key = "empty_or_failed"
        tip = _tip_for_negative(tip_key, "")
        _bump_negative(tip_key, tip, query)
        summary["negative"].append({"error_class": tip_key, "tip": tip})
        tip_key_for_patch = tip_key

    for entry in traces:
        if not isinstance(entry, dict):
            continue
        if entry.get("ok") is False or (
            entry.get("ok") and entry.get("truncated") and str(entry.get("grain")) == "detail"
        ):
            ec = _error_class(entry)
            blob = _trace_error_blob(entry)
            tip = _tip_for_negative(ec, "", error_blob=blob)
            # 列名错误用更细的 key，避免不同错列互相覆盖
            tip_key = ec
            lesson = _schema_lesson_from_error(blob)
            if ec == "unknown_column_or_table":
                ident = _UNKNOWN_IDENT.search(blob)
                tbl = _FROM_TABLE.search(blob)
                if ident:
                    tip_key = (
                        f"bad_col_{(tbl.group(1) if tbl else 'x').lower()}_"
                        f"{ident.group(1).lower()}"
                    )
            _bump_negative(tip_key, tip, query)
            summary["negative"].append(
                {"error_class": tip_key, "tip": tip, "lesson": lesson or tip}
            )

    _update_session_turn(session_id, query, result)

    # 反馈闭环：评估「上一轮注入的教训」；再登记本轮注入供下一轮评估
    from app.core.evolution.feedback import apply_tip_feedback, maybe_queue_strategy_patch

    if session_id:
        mem = store.load_session_memory(session_id)
        pending = mem.get("feedback_pending") or {}
        pending_classes = list(pending.get("tip_classes") or [])
        if pending_classes:
            summary["feedback"] = apply_tip_feedback(
                delivery_reason=reason or "none",
                injected_classes=pending_classes,
            )
        last_inj = mem.get("last_injected") or {}
        # 本轮若刚注入了教训，留给下一轮 harvest 打分
        if last_inj.get("tip_classes") and last_inj.get("query") == _clip(query, 160):
            mem["feedback_pending"] = {
                "tip_classes": list(last_inj.get("tip_classes") or []),
                "from_query": last_inj.get("query"),
            }
        else:
            mem["feedback_pending"] = None
        store.save_session_memory(session_id, mem)

    if tip_key_for_patch:
        neg = store.load_negative()
        row = (neg.get("tips") or {}).get(tip_key_for_patch) or {}
        patch = maybe_queue_strategy_patch(
            tip_key_for_patch, int(row.get("hit_count") or 0)
        )
        if patch:
            summary["strategy_patch"] = patch

    return summary


def _bump_positive_pattern(pid: str, sql: str, cols: list[str], query: str) -> None:
    data = store.load_positive()
    patterns = data.setdefault("patterns", {})
    row = patterns.get(pid) or {
        "pattern_id": pid,
        "sql_template": sql_to_fixed_template(sql),
        "sample_sql": sql[:2000],
        "columns": cols,
        "sample_queries": [],
        "success_count": 0,
        "last_delivery_reason": "none",
    }
    row["success_count"] = int(row.get("success_count") or 0) + 1
    row["sql_template"] = sql_to_fixed_template(sql)
    row["columns"] = cols or row.get("columns") or []
    qs = list(row.get("sample_queries") or [])
    q = _clip(query, 160)
    if q and q not in qs:
        qs.append(q)
    row["sample_queries"] = qs[-8:]
    row["updated_at"] = time.time()
    patterns[pid] = row
    store.save_positive(data)


def _bump_negative(error_class: str, tip: str, query: str) -> None:
    data = store.load_negative()
    tips = data.setdefault("tips", {})
    row = tips.get(error_class) or {
        "error_class": error_class,
        "tip_text": tip,
        "hit_count": 0,
        "sample_queries": [],
        "weight": 1.0,
    }
    row["hit_count"] = int(row.get("hit_count") or 0) + 1
    row["tip_text"] = tip or row.get("tip_text") or ""
    qs = list(row.get("sample_queries") or [])
    q = _clip(query, 160)
    if q and q not in qs:
        qs.append(q)
    row["sample_queries"] = qs[-8:]
    row["updated_at"] = time.time()
    tips[error_class] = row
    store.save_negative(data)


def _update_session_turn(
    session_id: str,
    query: str,
    result: dict[str, Any],
) -> None:
    if not session_id:
        return
    mem = store.load_session_memory(session_id)
    turns = list(mem.get("turns") or [])
    turns.append(
        {
            "ts": time.time(),
            "query": _clip(query, 200),
            "mode": result.get("mode"),
            "status": result.get("status"),
            "delivery_reason": (result.get("delivery_assessment") or {}).get("reason")
            or result.get("delivery_gate"),
        }
    )
    mem["turns"] = turns[-20:]
    mem["session_id"] = session_id
    store.save_session_memory(session_id, mem)
