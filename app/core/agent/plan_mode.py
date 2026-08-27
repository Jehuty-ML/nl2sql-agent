"""轻量 Plan 模式：复杂问题先列查数计划（prompt 增强 + Run Log 记录）。"""

from __future__ import annotations

import re
from typing import Any

PLAN_BLOCK = re.compile(r"(?is)<plan>(.*?)</plan>")


def plan_mode_prompt_addon() -> str:
    return """
【复杂问题 · 查数计划（Plan）】
若用户一次问 ≥3 个独立指标或需多步对比，请先输出 <plan>…</plan> 块列出将调用的 fixed key 或 SQL 口径，
然后在下一轮用 PTC 并行执行查数，最后写结论。
计划阶段不要调用工具。
"""


def extract_plan(text: str) -> str | None:
    m = PLAN_BLOCK.search(text or "")
    if not m:
        return None
    body = m.group(1).strip()
    return body or None


def append_plan_progress(task_store: Any, task_id: str, plan_text: str) -> None:
    task_store.append_progress(
        task_id,
        "查数计划",
        plan_text[:480],
        full=plan_text,
    )
