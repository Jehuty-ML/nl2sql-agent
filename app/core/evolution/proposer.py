"""从正例动态 SQL 生成 fixed_analysis / slash 提案。

不做指纹层「硬蹭」合并：保留各次成功 SQL 原样记账；当同一问法下
变体足够多/成功次数够阈值时，异步请 LLM 判断：
1) 是否值得固化成 skill；2) 固化用哪条（或改写后的）SQL / key / 名称。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Callable

import httpx

from app.config import settings
from app.core.evolution import store
from app.core.evolution.registry import get_fixed_queries
from app.core.evolution.sql_fingerprint import sql_to_fixed_template
from app.core.tools.sql_guard import guard_readonly_sql

logger = logging.getLogger(__name__)

# 测试可替换
_judge_fn: Callable[[list[dict[str, Any]]], dict[str, Any] | None] | None = None


def set_skill_judge_for_tests(
    fn: Callable[[list[dict[str, Any]]], dict[str, Any] | None] | None,
) -> None:
    global _judge_fn
    _judge_fn = fn


def _group_key(sample_queries: list[str]) -> str:
    norms = sorted({re.sub(r"\s+", " ", str(q).strip()) for q in sample_queries if q})
    if not norms:
        return ""
    # 以主问法为组（取最短/第一条规范化串的集合哈希）
    raw = "||".join(norms[:5])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _collect_candidate_groups(
    patterns: dict[str, Any], threshold: int
) -> list[dict[str, Any]]:
    """按 sample_queries 归组；组内 success 总和 ≥ 阈值才送审。"""
    buckets: dict[str, dict[str, Any]] = {}
    for pid, row in patterns.items():
        if not isinstance(row, dict):
            continue
        samples = [str(x) for x in (row.get("sample_queries") or []) if x]
        if not samples:
            continue
        # 每个 sample 单独挂到以其为主键的组，便于「同一句话多次问」聚合变体
        for q in samples[:3]:
            gk = _group_key([q])
            if not gk:
                continue
            b = buckets.get(gk)
            if not b:
                buckets[gk] = {
                    "group_id": gk,
                    "primary_query": q,
                    "variants": [],
                    "success_total": 0,
                    "sample_queries": [],
                }
                b = buckets[gk]
            b["variants"].append(
                {
                    "pattern_id": pid,
                    "success_count": int(row.get("success_count") or 0),
                    "sql": str(row.get("sample_sql") or row.get("sql_template") or ""),
                    "sql_template": str(
                        row.get("sql_template")
                        or sql_to_fixed_template(str(row.get("sample_sql") or ""))
                    ),
                    "columns": list(row.get("columns") or []),
                }
            )
            b["success_total"] = int(b["success_total"]) + int(
                row.get("success_count") or 0
            )
            if q not in b["sample_queries"]:
                b["sample_queries"].append(q)

    out: list[dict[str, Any]] = []
    for b in buckets.values():
        # 去重同一 pattern 被多 query 重复累加
        seen: set[str] = set()
        uniq = []
        total = 0
        for v in b["variants"]:
            pid = str(v["pattern_id"])
            if pid in seen:
                continue
            seen.add(pid)
            uniq.append(v)
            total += int(v["success_count"])
        b["variants"] = uniq
        b["success_total"] = total
        if total >= threshold and uniq:
            out.append(b)
    return out


def _already_handled(group_id: str, proposals: list[dict[str, Any]]) -> bool:
    for p in proposals:
        if not isinstance(p, dict):
            continue
        if p.get("group_id") == group_id and p.get("promote_status") in (
            "pending",
            "promoted",
            "declined",
        ):
            # declined 可过冷却后再审
            if p.get("promote_status") == "declined":
                until = float(p.get("declined_until") or 0)
                if until and time.time() < until:
                    return True
                continue
            return True
    return False


def _sanitize_key(raw: str, fallback: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", (raw or "").lower()).strip("_")
    if not base or not re.match(r"^[a-z]", base):
        base = fallback
    base = base[:40]
    existing = set(get_fixed_queries().keys())
    proposals = store.load_proposals().get("proposals") or []
    for p in proposals:
        if isinstance(p, dict) and p.get("analysis_key"):
            existing.add(str(p["analysis_key"]))
    key = base
    i = 2
    while key in existing:
        key = f"{base}_{i}"
        i += 1
    return key


def _default_llm_judge(group: dict[str, Any]) -> dict[str, Any] | None:
    """调用当前 Provider：判断是否固化，并给出规范 SQL/命名。"""
    llm = settings.resolve_llm()
    if not llm.get("enabled"):
        return None

    variants = group.get("variants") or []
    payload_variants = []
    for v in variants[:8]:
        payload_variants.append(
            {
                "pattern_id": v.get("pattern_id"),
                "success_count": v.get("success_count"),
                "sql": v.get("sql"),
                "sql_template": v.get("sql_template"),
            }
        )
    user_msg = {
        "primary_query": group.get("primary_query"),
        "sample_queries": group.get("sample_queries"),
        "success_total": group.get("success_total"),
        "variants": payload_variants,
        "instruction": (
            "这些是同一类自然语言问数下、多次成功的动态聚合 SQL 变体。"
            "请判断是否应固化为 fixed_analysis + slash。"
            "若变体只是 event 过滤/别名/排序等非本质差异，可合并选一条最稳妥的规范 SQL"
            "（可用 {start_date}/{end_date} 占位）；若差异本质不同或样本不足，应拒绝。"
            "只输出 JSON，不要 markdown。"
        ),
        "schema": {
            "should_propose": "bool",
            "reason": "string",
            "analysis_key": "snake_case ascii id, e.g. evo_lib_active",
            "name": "short Chinese title",
            "slash": "/evo_xxx",
            "sql": "SELECT ... with optional {start_date}/{end_date}",
            "keywords": ["lib", "活跃"],
            "source_pattern_ids": ["..."],
        },
    }
    body = {
        "model": llm["model"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是 NL2SQL 技能提案评审。只输出合法 JSON 对象。"
                    "should_propose=false 时仍给 reason。"
                ),
            },
            {"role": "user", "content": json.dumps(user_msg, ensure_ascii=False)},
        ],
        "temperature": 0.1,
    }
    url = f"{str(llm['base_url']).rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {llm['api_key']}"}
    try:
        with httpx.Client(timeout=min(60.0, float(llm.get("timeout") or 60))) as client:
            resp = client.post(url, headers=headers, json=body)
            if resp.status_code >= 400:
                logger.warning(
                    "skill judge LLM HTTP %s: %s",
                    resp.status_code,
                    (resp.text or "")[:200],
                )
                return None
            content = (
                resp.json()
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content")
                or ""
            )
    except Exception:
        logger.exception("skill judge LLM call failed")
        return None

    return _parse_judge_json(str(content))


def _parse_judge_json(text: str) -> dict[str, Any] | None:
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None


def maybe_propose_skills() -> list[dict[str, Any]]:
    """阈值触发 →（异步路径中）LLM 判定是否提案及规范内容。"""
    if not settings.enable_evolution:
        return []
    threshold = max(1, int(settings.evolution_pattern_threshold))
    data = store.load_positive()
    patterns = data.get("patterns") or {}
    proposals_doc = store.load_proposals()
    proposals: list[dict[str, Any]] = list(proposals_doc.get("proposals") or [])
    created: list[dict[str, Any]] = []

    groups = _collect_candidate_groups(patterns, threshold)
    judge = _judge_fn or _default_llm_judge

    for group in groups:
        gid = str(group["group_id"])
        if _already_handled(gid, proposals):
            continue

        decision = judge(group)
        if not decision:
            # LLM 不可用：不自动硬蹭提案，只记一次观测，避免空转刷屏
            logger.info(
                "skill judge skipped/unavailable group=%s query=%s",
                gid,
                group.get("primary_query"),
            )
            continue

        if not decision.get("should_propose"):
            proposals.append(
                {
                    "id": f"decl_{gid}",
                    "group_id": gid,
                    "promote_status": "declined",
                    "eval_status": "llm_declined",
                    "reason": str(decision.get("reason") or "llm declined")[:300],
                    "sample_queries": group.get("sample_queries") or [],
                    "success_count": group.get("success_total"),
                    "created_at": time.time(),
                    "declined_until": time.time() + 86400,
                }
            )
            proposals_doc["proposals"] = proposals
            store.save_proposals(proposals_doc)
            continue

        sql_tmpl = str(decision.get("sql") or "").strip()
        if not sql_tmpl and group["variants"]:
            sql_tmpl = str(
                group["variants"][0].get("sql_template")
                or group["variants"][0].get("sql")
                or ""
            )
        if not sql_tmpl:
            continue
        if "{start_date}" not in sql_tmpl and re.search(
            r"'20\d{2}-\d{2}-\d{2}'", sql_tmpl
        ):
            sql_tmpl = sql_to_fixed_template(sql_tmpl)

        probe = (
            sql_tmpl.replace("{start_date}", "toDate('2026-07-01')")
            .replace("{end_date}", "toDate('2026-08-01')")
        )
        guarded = guard_readonly_sql(probe, default_limit=500)
        if not guarded.get("ok"):
            proposals.append(
                {
                    "id": f"decl_{gid}",
                    "group_id": gid,
                    "promote_status": "declined",
                    "eval_status": "guard_failed",
                    "reason": str(guarded.get("error") or "sql_guard failed")[:300],
                    "sql": sql_tmpl,
                    "created_at": time.time(),
                    "declined_until": time.time() + 3600,
                }
            )
            proposals_doc["proposals"] = proposals
            store.save_proposals(proposals_doc)
            continue

        fallback_key = "evo_" + gid[:8]
        key = _sanitize_key(str(decision.get("analysis_key") or ""), fallback_key)
        slash_raw = str(decision.get("slash") or ("/" + key)).strip()
        if not slash_raw.startswith("/"):
            slash_raw = "/" + slash_raw
        slash = "/" + re.sub(r"[^a-z0-9_]", "", slash_raw[1:].lower())[:28]
        if slash == "/":
            slash = f"/evo_{gid[:6]}"

        name = str(decision.get("name") or group.get("primary_query") or key)[:40]
        kws = decision.get("keywords")
        if not isinstance(kws, list):
            kws = []
        kws = [str(x) for x in kws if x][:8]
        src = decision.get("source_pattern_ids")
        if not isinstance(src, list):
            src = [v["pattern_id"] for v in group["variants"]]

        proposal = {
            "id": f"prop_{gid}",
            "group_id": gid,
            "pattern_id": gid,
            "analysis_key": key,
            "name": name,
            "description": str(
                decision.get("reason")
                or f"LLM 提案：问法「{group.get('primary_query')}」固化"
            )[:240],
            "keywords": kws,
            "sql": sql_tmpl,
            "columns": (group["variants"][0].get("columns") if group["variants"] else [])
            or [],
            "sample_queries": group.get("sample_queries") or [],
            "slash": slash,
            "success_count": int(group.get("success_total") or 0),
            "source_pattern_ids": [str(x) for x in src][:12],
            "eval_status": "llm_ok",
            "promote_status": "pending",
            "created_at": time.time(),
        }
        proposals.append(proposal)
        created.append(proposal)
        proposals_doc["proposals"] = proposals
        store.save_proposals(proposals_doc)

    return created


def list_proposals(*, pending_only: bool = False) -> list[dict[str, Any]]:
    rows = list(store.load_proposals().get("proposals") or [])
    if pending_only:
        return [
            p
            for p in rows
            if isinstance(p, dict) and p.get("promote_status") == "pending"
        ]
    return [p for p in rows if isinstance(p, dict)]
