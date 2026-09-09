"""验收并 promote skill 提案 → overlay 热加载。"""

from __future__ import annotations

import time
from typing import Any

from app.bi.fixed_queries import FIXED_QUERIES as BUILTIN_FIXED
from app.bi.fixed_queries import render_sql
from app.config import settings
from app.core.evolution import store
from app.core.evolution.proposer import list_proposals
from app.core.tools.clickhouse_tool import run_query
from app.core.tools.result_shape import GRAIN_AGGREGATE, enrich_query_result
from app.core.tools.sql_classifier import classify_sql
from app.core.tools.sql_guard import guard_readonly_sql


def evaluate_proposal(proposal: dict[str, Any], *, try_execute: bool = True) -> dict[str, Any]:
    """sql_guard +（可选）只读试跑。"""
    sql_tmpl = str(proposal.get("sql") or "")
    start, end = "2026-07-01", "2026-08-01"
    try:
        sql = render_sql(sql_tmpl, start, end)
    except Exception as e:
        return {"ok": False, "error": f"render_sql failed: {e}"}

    guarded = guard_readonly_sql(sql)
    if not guarded.get("ok"):
        return {"ok": False, "error": guarded.get("error"), "stage": "sql_guard"}

    sql = str(guarded["sql"])
    grain = classify_sql(sql)

    if not try_execute:
        return {"ok": True, "sql": sql, "grain": grain, "executed": False}

    try:
        result = run_query(sql)
    except Exception as e:
        return {"ok": False, "error": str(e), "stage": "execute"}

    enrich_query_result(result, grain=grain or GRAIN_AGGREGATE)
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error") or "query failed",
            "stage": "execute",
            "result": result,
        }
    rows = result.get("rows") or []
    if not rows:
        return {"ok": False, "error": "empty rows", "stage": "execute", "result": result}
    if result.get("truncated"):
        return {"ok": False, "error": "truncated result", "stage": "grain", "result": result}
    cap = int(settings.model_row_cap)
    if len(rows) > cap:
        return {
            "ok": False,
            "error": f"too many rows ({len(rows)} > {cap})",
            "stage": "row_cap",
        }
    return {
        "ok": True,
        "sql": sql,
        "result_meta": {
            "returned_rows": len(rows),
            "grain": result.get("grain"),
            "truncated": result.get("truncated"),
        },
    }


def promote_proposal(
    proposal_id: str,
    *,
    try_execute: bool = True,
    skip_execute: bool = False,
) -> dict[str, Any]:
    """将 pending 提案写入 overlay，并标记 promoted。"""
    proposals_doc = store.load_proposals()
    proposals = list(proposals_doc.get("proposals") or [])
    target: dict[str, Any] | None = None
    for p in proposals:
        if isinstance(p, dict) and str(p.get("id")) == proposal_id:
            target = p
            break
    if not target:
        raise KeyError(f"proposal not found: {proposal_id}")
    if target.get("promote_status") == "promoted":
        return {"ok": True, "already": True, "proposal": target}

    eval_res = evaluate_proposal(target, try_execute=try_execute and not skip_execute)
    if not eval_res.get("ok"):
        target["eval_status"] = "failed"
        target["eval_error"] = eval_res.get("error")
        store.save_proposals({"proposals": proposals})
        return {"ok": False, "error": eval_res.get("error"), "eval": eval_res}

    key = str(target["analysis_key"])
    if key in BUILTIN_FIXED:
        return {"ok": False, "error": f"不能覆盖内置固定分析: {key}"}

    overlay = store.load_overlay()
    fq = dict(overlay.get("fixed_queries") or {})
    fq[key] = {
        "name": target.get("name") or key,
        "keywords": target.get("keywords") or [],
        "description": target.get("description") or "",
        "sql": target.get("sql"),
        "evolved": True,
        "pattern_id": target.get("pattern_id"),
    }
    overlay["fixed_queries"] = fq

    slash = str(target.get("slash") or f"/{key}")
    if not slash.startswith("/"):
        slash = "/" + slash
    dash = dict(overlay.get("dashboard_commands") or {})
    dash[slash] = {
        "title": str(target.get("name") or key),
        "analysis_key": key,
        "lookback_days": 29,
        "filename_prefix": key,
        "chart_mode": "metric_dashboard",
        "table_mode": "list",
        "evolved": True,
    }
    overlay["dashboard_commands"] = dash
    store.save_overlay(overlay)

    target["eval_status"] = "passed"
    target["promote_status"] = "promoted"
    target["promoted_at"] = time.time()
    target["slash"] = slash
    store.save_proposals({"proposals": proposals})

    return {
        "ok": True,
        "analysis_key": key,
        "slash": slash,
        "eval": eval_res,
        "proposal": target,
    }


def promote_by_pattern(pattern_id: str, **kwargs: Any) -> dict[str, Any]:
    for p in list_proposals():
        if p.get("pattern_id") == pattern_id:
            return promote_proposal(str(p["id"]), **kwargs)
    raise KeyError(f"no proposal for pattern: {pattern_id}")
