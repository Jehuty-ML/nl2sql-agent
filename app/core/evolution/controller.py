"""异步调度：run 结束后收获信号，并尝试生成 skill 提案。"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.config import settings
from app.core.evolution.proposer import maybe_propose_skills
from app.core.evolution.signals import harvest_signals

logger = logging.getLogger(__name__)


def harvest_after_run(
    *,
    task_id: str,
    query: str,
    result: dict[str, Any],
    session_id: str = "",
) -> dict[str, Any]:
    """同步收获（供测试 / sync 路径）。"""
    if not settings.enable_evolution:
        return {"skipped": True}
    try:
        summary = harvest_signals(
            task_id=task_id,
            query=query,
            result=result,
            session_id=session_id,
        )
        proposals = maybe_propose_skills()
        summary["proposals"] = proposals
        return summary
    except Exception:
        logger.exception("evolution harvest failed task_id=%s", task_id)
        return {"ok": False, "error": "harvest_failed"}


def schedule_harvest(
    *,
    task_id: str,
    query: str,
    result: dict[str, Any],
    session_id: str = "",
) -> None:
    """不阻塞主问答路径。"""
    if not settings.enable_evolution:
        return

    def _run() -> None:
        harvest_after_run(
            task_id=task_id,
            query=query,
            result=result,
            session_id=session_id,
        )

    threading.Thread(target=_run, daemon=True, name=f"evo-harvest-{task_id[:8]}").start()
