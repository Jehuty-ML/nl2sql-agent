"""自进化一期单元测试（使用临时目录，不碰真实 .scratchpad）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.evolution import store
from app.core.evolution.controller import harvest_after_run
from app.core.evolution.promote import promote_proposal
from app.core.evolution.registry import get_dashboard_commands, get_fixed_queries
from app.core.evolution.sql_fingerprint import abstract_sql, pattern_id_from_sql
from app.core.evolution.strategy import load_strategy
from app.core.routing.slash_router import route_input


@pytest.fixture()
def evo_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store, "EVOLUTION_DIR", tmp_path / "evolution")
    monkeypatch.setenv("ENABLE_EVOLUTION", "true")
    # 刷新 settings 可能较重；直接改 settings 字段
    from app.config import settings

    monkeypatch.setattr(settings, "enable_evolution", True)
    monkeypatch.setattr(settings, "evolution_pattern_threshold", 2)
    return tmp_path / "evolution"


def test_strategy_baseline_loads():
    s = load_strategy("v1_baseline")
    assert s["id"] == "v1_baseline"
    assert "只读" in s["prompt"] or "只读硬约束" in s["prompt"]
    assert "max_parallel_tool_calls" in (s.get("knobs") or {})


def test_sql_fingerprint_stable():
    a = "SELECT dt, count() FROM events WHERE dt BETWEEN toDate('2026-07-01') AND toDate('2026-08-01') GROUP BY dt LIMIT 100"
    b = "SELECT dt, count() FROM events WHERE dt BETWEEN toDate('2026-07-15') AND toDate('2026-07-20') GROUP BY dt LIMIT 50"
    assert abstract_sql(a) == abstract_sql(b)
    assert pattern_id_from_sql(a, ["dt", "c"]) == pattern_id_from_sql(b, ["dt", "c"])


def test_dynamic_sql_variants_keep_distinct_fingerprints():
    """不同 event 过滤不应在指纹层硬合并；是否合成 skill 交给 LLM。"""
    a = (
        "SELECT lib, COUNT(DISTINCT identity_login_id) AS active_users FROM events "
        "WHERE event = 'page_view' AND identity_login_id IS NOT NULL GROUP BY lib LIMIT 500"
    )
    b = (
        "SELECT lib, COUNT(DISTINCT identity_login_id) AS active_users FROM events "
        "WHERE event = '屏浏览' AND identity_login_id IS NOT NULL GROUP BY lib LIMIT 500"
    )
    assert pattern_id_from_sql(a) != pattern_id_from_sql(b)


def test_harvest_positive_and_propose(evo_tmp: Path, monkeypatch: pytest.MonkeyPatch):
    from app.config import settings
    from app.core.evolution import proposer as proposer_mod

    def _fake_judge(group: dict):
        sql = group["variants"][0]["sql_template"] or group["variants"][0]["sql"]
        return {
            "should_propose": True,
            "reason": "test judge merge",
            "analysis_key": "evo_channel",
            "name": "渠道用户数",
            "slash": "/evo_channel",
            "sql": sql,
            "keywords": ["渠道"],
            "source_pattern_ids": [group["variants"][0]["pattern_id"]],
        }

    proposer_mod.set_skill_judge_for_tests(_fake_judge)
    monkeypatch.setattr(settings, "evolution_pattern_threshold", 2)

    result = {
        "mode": "agent_loop",
        "status": "success",
        "delivery_assessment": {
            "reason": "none",
            "has_complete_evidence": True,
        },
        "tool_traces": [
            {
                "tool": "db_query",
                "ok": True,
                "grain": "aggregate",
                "truncated": False,
                "args": {
                    "sql": (
                        "SELECT register_channel, count() AS n FROM users "
                        "GROUP BY register_channel LIMIT 20"
                    )
                },
                "table": {
                    "sql": (
                        "SELECT register_channel, count() AS n FROM users "
                        "GROUP BY register_channel LIMIT 20"
                    ),
                    "columns": ["register_channel", "n"],
                    "rows": [{"register_channel": "抖音", "n": 1}],
                    "row_count": 1,
                },
            }
        ],
    }
    try:
        for i in range(2):
            harvest_after_run(
                task_id=f"t{i}",
                query="各渠道用户数多少",
                result=result,
                session_id="sess_demo",
            )
        from app.core.evolution.proposer import list_proposals

        pending = list_proposals(pending_only=True)
        assert pending, "应在达到阈值后由 LLM 判定生成提案"
        assert pending[0]["promote_status"] == "pending"
        assert pending[0].get("eval_status") == "llm_ok"

        out = promote_proposal(pending[0]["id"], skip_execute=True)
        assert out["ok"] is True
        key = out["analysis_key"]
        assert key in get_fixed_queries()
        slash = out["slash"]
        assert slash in get_dashboard_commands()
        routed = route_input(slash)
        assert routed["execution_path"] == "fixed_slash"
        assert routed["analysis_key"] == key
    finally:
        proposer_mod.set_skill_judge_for_tests(None)


def test_session_memory_injection(evo_tmp: Path):
    store.save_session_memory(
        "s1",
        {
            "session_id": "s1",
            "turns": [
                {
                    "query": "看一下日活",
                    "status": "success",
                }
            ],
        },
    )
    store.save_negative(
        {
            "tips": {
                "incomplete_or_detail": {
                    "error_class": "incomplete_or_detail",
                    "tip_text": "汇总类问题禁止明细 SQL",
                    "hit_count": 3,
                    "weight": 1.0,
                }
            }
        }
    )
    from app.core.evolution.memory import prepare_memory_injection

    inj = prepare_memory_injection("s1", "最近日活怎样")
    block = inj["block"]
    assert "检索到的记忆" in block
    assert "上一轮" in block
    assert "明细" in block or "教训" in block
    assert "incomplete_or_detail" in inj["tip_classes"]
    assert "偏好" not in block
    assert "preferred" not in block.lower()


def test_tip_feedback_closed_loop(evo_tmp: Path):
    from app.core.evolution.feedback import apply_tip_feedback, maybe_queue_strategy_patch

    store.save_negative(
        {
            "tips": {
                "missing_ok_query": {
                    "error_class": "missing_ok_query",
                    "tip_text": "必须先查数",
                    "hit_count": 2,
                    "weight": 1.0,
                }
            }
        }
    )
    down = apply_tip_feedback(
        delivery_reason="missing_ok_query",
        injected_classes=["missing_ok_query"],
    )
    assert down["updated"][0]["weight_after"] < 1.0
    up = apply_tip_feedback(
        delivery_reason="none",
        injected_classes=["missing_ok_query"],
    )
    assert up["updated"][0]["weight_after"] > down["updated"][0]["weight_after"]

    patch = maybe_queue_strategy_patch("missing_ok_query", 3)
    assert patch and patch["status"] == "pending"
    assert maybe_queue_strategy_patch("missing_ok_query", 3) is None  # 不重复


def test_negative_harvest(evo_tmp: Path):
    result = {
        "mode": "agent_loop",
        "status": "partial",
        "delivery_assessment": {"reason": "missing_ok_query"},
        "delivery_gate": "missing_ok_query",
        "tool_traces": [],
    }
    harvest_after_run(task_id="n1", query="随便说说建议", result=result, session_id="")
    neg = store.load_negative()
    assert "missing_ok_query" in (neg.get("tips") or {})


def test_schema_error_becomes_memory_tip(evo_tmp: Path):
    from app.core.evolution.signals import (
        _error_class,
        _schema_lesson_from_error,
        _tip_for_negative,
    )

    blob = (
        "Code: 47. DB::Exception: Unknown expression or function identifier "
        "'login_id' in scope SELECT lib, COUNTDistinct(login_id) AS active_users "
        "FROM events WHERE ..."
    )
    entry = {"ok": False, "error": blob, "args": {"sql": "SELECT login_id FROM events"}}
    assert _error_class(entry) == "unknown_column_or_table"
    lesson = _schema_lesson_from_error(blob)
    assert "identity_login_id" in lesson
    tip = _tip_for_negative("unknown_column_or_table", "", error_blob=blob)
    assert "identity_login_id" in tip

    # 动态 SQL 失败应写入负例 tip，供下次注入
    harvest_after_run(
        task_id="schema1",
        query="各 lib 活跃用户数",
        result={
            "mode": "agent_loop",
            "status": "partial",
            "delivery_assessment": {"reason": "incomplete_evidence"},
            "tool_traces": [entry],
        },
        session_id="s_schema",
    )
    tips = store.load_negative().get("tips") or {}
    assert any(
        "login_id" in k and "identity_login_id" in (v.get("tip_text") or "")
        for k, v in tips.items()
    )
