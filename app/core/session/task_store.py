"""任务状态：内存 + 落盘（Demo；避免进程重启后前端空转 404）。"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
_TASK_DIR = _ROOT / ".scratchpad" / "tasks"
_lock = threading.Lock()
_TASKS: dict[str, dict[str, Any]] = {}


def new_task_id() -> str:
    return uuid.uuid4().hex


def _ensure_dir() -> None:
    _TASK_DIR.mkdir(parents=True, exist_ok=True)


def _persist(task: dict[str, Any]) -> None:
    _ensure_dir()
    path = _TASK_DIR / f"{task['task_id']}.json"
    path.write_text(json.dumps(task, ensure_ascii=False, default=str), encoding="utf-8")


def _load_from_disk(task_id: str) -> dict[str, Any] | None:
    path = _TASK_DIR / f"{task_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def create_task(query: str) -> str:
    tid = new_task_id()
    with _lock:
        task = {
            "task_id": tid,
            "query": query,
            "status": "pending",
            "progress": [],
            "final_result": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        _TASKS[tid] = task
        _persist(task)
    return tid


def append_progress(
    task_id: str,
    step: str,
    detail: str = "",
    *,
    full: str | None = None,
) -> None:
    """追加进度。detail 供列表摘要；full 保留完整原文（点开查看）。"""
    with _lock:
        t = _TASKS.get(task_id)
        if not t:
            t = _load_from_disk(task_id)
            if not t:
                return
            _TASKS[task_id] = t
        entry: dict[str, Any] = {"step": step, "detail": detail, "ts": time.time()}
        if full and full.strip() and full.strip() != str(detail).strip():
            entry["full"] = full
        t["progress"].append(entry)
        t["status"] = "running"
        t["updated_at"] = time.time()
        _persist(t)


def finish_task(task_id: str, final_result: dict[str, Any], ok: bool = True) -> None:
    with _lock:
        t = _TASKS.get(task_id)
        if not t:
            t = _load_from_disk(task_id)
            if not t:
                return
            _TASKS[task_id] = t
        t["final_result"] = final_result
        t["status"] = "succeeded" if ok else "failed"
        t["updated_at"] = time.time()
        _persist(t)


def get_task(task_id: str) -> dict[str, Any] | None:
    with _lock:
        t = _TASKS.get(task_id)
        if t:
            return json.loads(json.dumps(t, ensure_ascii=False, default=str))
        disk = _load_from_disk(task_id)
        if disk:
            _TASKS[task_id] = disk
            return json.loads(json.dumps(disk, ensure_ascii=False, default=str))
        return None
