"""内存任务状态（Demo；生产可换 Redis）。"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any


_lock = threading.Lock()
_TASKS: dict[str, dict[str, Any]] = {}


def new_task_id() -> str:
    return uuid.uuid4().hex


def create_task(query: str) -> str:
    tid = new_task_id()
    with _lock:
        _TASKS[tid] = {
            "task_id": tid,
            "query": query,
            "status": "pending",
            "progress": [],
            "final_result": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
    return tid


def append_progress(task_id: str, step: str, detail: str = "") -> None:
    with _lock:
        t = _TASKS.get(task_id)
        if not t:
            return
        t["progress"].append({"step": step, "detail": detail, "ts": time.time()})
        t["status"] = "running"
        t["updated_at"] = time.time()


def finish_task(task_id: str, final_result: dict[str, Any], ok: bool = True) -> None:
    with _lock:
        t = _TASKS.get(task_id)
        if not t:
            return
        t["final_result"] = final_result
        t["status"] = "succeeded" if ok else "failed"
        t["updated_at"] = time.time()


def get_task(task_id: str) -> dict[str, Any] | None:
    with _lock:
        t = _TASKS.get(task_id)
        return dict(t) if t else None
