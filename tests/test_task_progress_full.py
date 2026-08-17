"""Smoke tests for Run Log progress full-text helpers."""

from __future__ import annotations

from app.core.session import task_store


def test_append_progress_keeps_full_even_when_same_as_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(task_store, "_TASK_DIR", tmp_path)
    task_store._TASKS.clear()
    tid = task_store.create_task("q")
    task_store.append_progress(tid, "工具返回 · 动态 SQL", "short", full="short")
    t = task_store.get_task(tid)
    assert t is not None
    assert t["progress"][0]["full"] == "short"


def test_update_latest_progress_replaces_waiting_placeholder(tmp_path, monkeypatch):
    monkeypatch.setattr(task_store, "_TASK_DIR", tmp_path)
    task_store._TASKS.clear()
    tid = task_store.create_task("q")
    step = "LLM 思考 · 第 1 轮"
    task_store.append_progress(tid, step, "等待模型决定：继续查数 / 还是给出结论…")
    ok = task_store.update_latest_progress(
        tid,
        step,
        "核心结论摘要",
        full="### 核心结论：\n完整思考正文",
        match_step=step,
    )
    assert ok is True
    t = task_store.get_task(tid)
    assert t is not None
    assert len(t["progress"]) == 1
    entry = t["progress"][0]
    assert entry["detail"] == "核心结论摘要"
    assert entry["full"].startswith("### 核心结论")
