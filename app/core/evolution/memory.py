"""L1 记忆：会话短摘要 + 负例 tip（可观测、可反馈）。

刻意不做「固定分析偏好 / preferred_key」注入：模型结合当轮上下文自行选工具即可，
偏好易抢路由、干扰动态 SQL 判断（见 docs/self-evolution.md 计划留存）。
"""

from __future__ import annotations

import time
from typing import Any

from app.config import settings
from app.core.evolution import store

_SESSION_TURN_WINDOW = 8


def prepare_memory_injection(
    session_id: str = "", query: str = ""
) -> dict[str, Any]:
    """返回注入块与元数据，供 Run Log 展示与事后反馈。"""
    empty = {"block": "", "lines": [], "tip_classes": []}
    if not settings.enable_evolution:
        return empty

    parts: list[str] = []
    tip_classes: list[str] = []
    cap = max(200, int(settings.evolution_memory_char_cap))
    _ = query

    if session_id:
        mem = store.load_session_memory(session_id)
        turns = list(mem.get("turns") or [])[-_SESSION_TURN_WINDOW:]
        if turns:
            last = turns[-1]
            q = str(last.get("query") or "")
            st = last.get("status") or last.get("delivery_reason") or ""
            if q:
                parts.append(f"上一轮: {q[:80]} → {st}")

    neg = store.load_negative()
    tips = list((neg.get("tips") or {}).values())
    tips.sort(
        key=lambda r: float(r.get("weight") or 1) * int(r.get("hit_count") or 0),
        reverse=True,
    )
    for row in tips[:4]:
        text = str(row.get("tip_text") or "").strip()
        w = float(row.get("weight") or 1)
        if text and w > 0.2:
            ec = str(row.get("error_class") or "")
            parts.append(f"教训[{ec}|w={w:.2f}]: {text}")
            if ec:
                tip_classes.append(ec)

    if not parts:
        return empty

    body = "\n".join(f"- {p}" for p in parts)
    block = "## 检索到的记忆\n" + body
    if len(block) > cap:
        block = block[: cap - 1] + "…"

    if session_id and tip_classes:
        mem = store.load_session_memory(session_id)
        mem["last_injected"] = {
            "ts": time.time(),
            "tip_classes": tip_classes,
            "query": (query or "")[:160],
        }
        store.save_session_memory(session_id, mem)

    return {
        "block": block,
        "lines": parts,
        "tip_classes": tip_classes,
    }


def build_memory_block(session_id: str = "", query: str = "") -> str:
    return str(prepare_memory_injection(session_id, query).get("block") or "")


def format_system_with_memory(base_prompt: str, session_id: str = "", query: str = "") -> str:
    mem = build_memory_block(session_id, query)
    if not mem:
        return base_prompt
    return base_prompt.rstrip() + "\n\n" + mem
