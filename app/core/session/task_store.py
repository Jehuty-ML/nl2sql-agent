"""任务状态：内存 + 落盘（Demo；避免进程重启后前端空转 404）。"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.json_safe import json_safe

_ROOT = Path(__file__).resolve().parents[3]
_TASK_DIR = _ROOT / ".scratchpad" / "tasks"
_lock = threading.Lock()
_TASKS: dict[str, dict[str, Any]] = {}


def new_task_id() -> str:
    return uuid.uuid4().hex


def _ensure_dir() -> None:
    _TASK_DIR.mkdir(parents=True, exist_ok=True)


def _dumps(obj: Any) -> str:
    """落盘 / 深拷贝：禁止 NaN，否则 HTTP JSONResponse 会 500。"""
    return json.dumps(json_safe(obj), ensure_ascii=False, default=str, allow_nan=False)


def _persist(task: dict[str, Any]) -> None:
    _ensure_dir()
    path = _TASK_DIR / f"{task['task_id']}.json"
    path.write_text(_dumps(task), encoding="utf-8")


def _load_from_disk(task_id: str) -> dict[str, Any] | None:
    path = _TASK_DIR / f"{task_id}.json"
    if not path.is_file():
        return None
    try:
        # 旧文件可能含字面 NaN；先替换再 parse
        raw = path.read_text(encoding="utf-8")
        raw = (
            raw.replace(": NaN", ": null")
            .replace(": -Infinity", ": null")
            .replace(": Infinity", ": null")
        )
        return json_safe(json.loads(raw))
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


def _apply_full(entry: dict[str, Any], full: str | None) -> None:
    """写入 full：只要有原文就保留，便于前端「查看全文」（可与 detail 相同）。"""
    if full is None:
        return
    text = str(full).strip()
    if text:
        entry["full"] = text


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
        _apply_full(entry, full)
        t["progress"].append(entry)
        t["status"] = "running"
        t["updated_at"] = time.time()
        _persist(t)


def update_latest_progress(
    task_id: str,
    step: str,
    detail: str = "",
    *,
    full: str | None = None,
    match_step: str | None = None,
) -> bool:
    """就地更新最近一条进度（可选按 step 匹配）。用于把「等待中」占位换成真实内容。"""
    with _lock:
        t = _TASKS.get(task_id)
        if not t:
            t = _load_from_disk(task_id)
            if not t:
                return False
            _TASKS[task_id] = t
        progress = t.get("progress") or []
        if not progress:
            return False
        idx = len(progress) - 1
        if match_step is not None:
            for i in range(len(progress) - 1, -1, -1):
                if progress[i].get("step") == match_step:
                    idx = i
                    break
            else:
                return False
        entry = dict(progress[idx])
        entry["step"] = step
        entry["detail"] = detail
        entry["ts"] = time.time()
        if full is not None:
            entry.pop("full", None)
            _apply_full(entry, full)
        progress[idx] = entry
        t["progress"] = progress
        t["status"] = "running"
        t["updated_at"] = time.time()
        _persist(t)
        return True


def finish_task(task_id: str, final_result: dict[str, Any], ok: bool = True) -> None:
    with _lock:
        t = _TASKS.get(task_id)
        if not t:
            t = _load_from_disk(task_id)
            if not t:
                return
            _TASKS[task_id] = t
        t["final_result"] = json_safe(final_result)
        t["status"] = "succeeded" if ok else "failed"
        t["updated_at"] = time.time()
        _persist(t)


def abort_task(task_id: str, reason: str = "任务已中止") -> dict[str, Any] | None:
    """把仍在 running/pending 的任务标为 failed（热重载杀线程后的僵尸任务）。"""
    with _lock:
        t = _TASKS.get(task_id)
        if not t:
            t = _load_from_disk(task_id)
            if not t:
                return None
            _TASKS[task_id] = t
        if t.get("status") not in ("running", "pending", "accepted"):
            return json.loads(_dumps(t))
        t["progress"].append(
            {"step": "任务中止", "detail": reason, "ts": time.time()}
        )
        t["final_result"] = json_safe(
            {
                "mode": "aborted",
                "status": "failed",
                "answer_md": reason,
                "error": reason,
            }
        )
        t["status"] = "failed"
        t["updated_at"] = time.time()
        _persist(t)
        return json.loads(_dumps(t))


def _maybe_fail_stale(t: dict[str, Any]) -> dict[str, Any]:
    """无进度更新过久 → 视为 worker 已死（常见于 uvicorn --reload）。"""
    if t.get("status") not in ("running", "pending", "accepted"):
        return t
    try:
        from app.config import settings

        stale_after = max(120.0, float(settings.llm_timeout) * 2.0 + 60.0)
    except Exception:
        stale_after = 420.0
    # 卡在「进化记忆已注入」且从未进入 LLM 思考：几乎必是热重载杀线程，缩短判定
    progress = list(t.get("progress") or [])
    last_step = str((progress[-1] or {}).get("step") or "") if progress else ""
    steps = {str(p.get("step") or "") for p in progress}
    if last_step == "进化记忆已注入" and not any(
        s.startswith("LLM 思考") for s in steps
    ):
        stale_after = min(stale_after, 90.0)
    updated = float(t.get("updated_at") or t.get("created_at") or 0)
    if updated <= 0 or (time.time() - updated) < stale_after:
        return t
    reason = (
        f"任务超时未更新（>{int(stale_after)}s）。"
        "常见原因：后端 --reload 热重启打断了后台线程；请用无 --reload 方式启动后重试。"
    )
    t["progress"] = list(t.get("progress") or [])
    t["progress"].append({"step": "任务中止", "detail": reason, "ts": time.time()})
    t["final_result"] = json_safe(
        {
            "mode": "aborted",
            "status": "failed",
            "answer_md": reason,
            "error": reason,
        }
    )
    t["status"] = "failed"
    t["updated_at"] = time.time()
    _persist(t)
    return t


def get_task(task_id: str) -> dict[str, Any] | None:
    with _lock:
        t = _TASKS.get(task_id)
        if not t:
            t = _load_from_disk(task_id)
            if not t:
                return None
            _TASKS[task_id] = t
        t = _maybe_fail_stale(t)
        _TASKS[task_id] = t
        return json.loads(_dumps(t))
