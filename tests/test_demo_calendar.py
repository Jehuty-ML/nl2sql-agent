"""Demo 日历诚实门闩：以「今天 vs Demo 窗 + 是否查数」为主，不靠措辞白名单。"""

from datetime import date

from app.core.agent.demo_calendar import (
    DEMO_DATA_END,
    DEMO_DATA_START,
    assess_calendar_demo_gate,
    resolve_relative_calendar_intent,
    user_pins_demo_window,
)
from app.core.agent.delivery_floor import apply_delivery_soft_floor

_OK_TRACE = [
    {
        "tool": "get_fixed_analysis",
        "ok": True,
        "grain": "fixed",
        "truncated": False,
        "row_count": 7,
        "table": {"rows": [{"dt": "2026-07-26", "dau": 1}], "row_count": 7},
    }
]


def test_stale_today_triggers_without_recent_phrase():
    """「dau 怎么样」无「最近」也应在 9 月触发——不靠措辞。"""
    info = assess_calendar_demo_gate(
        "dau怎么样",
        tool_traces=_OK_TRACE,
        today=date(2026, 9, 10),
    )
    assert info is not None
    assert info["out_of_range"] is True
    assert "2026-05-04" in info["notice"]
    assert "2026-08-01" in info["notice"]


def test_vague_recent_also_triggers():
    info = assess_calendar_demo_gate(
        "最近的dau",
        tool_traces=_OK_TRACE,
        today=date(2026, 9, 10),
    )
    assert info and info["out_of_range"]


def test_no_query_no_gate():
    info = assess_calendar_demo_gate(
        "最近一周日活",
        tool_traces=[],
        today=date(2026, 9, 10),
    )
    assert info is not None
    assert info["out_of_range"] is False
    assert info["reason"] == "no_successful_query"


def test_pin_demo_date_skips_gate():
    assert user_pins_demo_window("看一下 2026-07-15 的日活")
    info = assess_calendar_demo_gate(
        "看一下 2026-07-15 的日活",
        tool_traces=_OK_TRACE,
        today=date(2026, 9, 10),
    )
    assert info is not None
    assert info["out_of_range"] is False
    assert info["reason"] == "user_pinned_demo_dates"


def test_pin_demo_month_skips_gate():
    assert user_pins_demo_window("2026年7月完课率")
    info = assess_calendar_demo_gate(
        "2026年7月完课率",
        tool_traces=_OK_TRACE,
        today=date(2026, 9, 10),
    )
    assert info and not info["out_of_range"]


def test_today_inside_demo_no_gate():
    info = assess_calendar_demo_gate(
        "最近一周日活",
        tool_traces=_OK_TRACE,
        today=DEMO_DATA_END,
    )
    assert info and not info["out_of_range"]


def test_resolve_last_week_enrichment_only():
    intent = resolve_relative_calendar_intent(
        "最近一周日活怎样？", today=date(2026, 9, 9)
    )
    assert intent is not None
    assert intent["label"] == "最近一周"


def test_soft_floor_structural_gate(monkeypatch):
    import app.core.agent.demo_calendar as dc

    fixed = date(2026, 9, 10)
    real = dc.assess_calendar_demo_gate

    def _fake_assess(query, *, tool_traces=None, today=None):
        return real(query, tool_traces=tool_traces, today=fixed)

    monkeypatch.setattr(dc, "assess_calendar_demo_gate", _fake_assess)

    out = apply_delivery_soft_floor(
        {
            "mode": "agent_loop",
            "answer": "### 核心结论：见上表",
            "tool_traces": _OK_TRACE,
        },
        user_query="dau怎么样",  # 无「最近」措辞
    )
    assert out["status"] == "partial"
    assert out["delivery_gate"] == "calendar_out_of_demo"
    assert str(DEMO_DATA_START) in out["answer"]
    assert str(DEMO_DATA_END) in out["answer"]
    assert "核心结论" in out["answer"]


def test_soft_floor_pin_demo_keeps_success(monkeypatch):
    import app.core.agent.demo_calendar as dc

    fixed = date(2026, 9, 10)
    real = dc.assess_calendar_demo_gate

    def _fake_assess(query, *, tool_traces=None, today=None):
        return real(query, tool_traces=tool_traces, today=fixed)

    monkeypatch.setattr(dc, "assess_calendar_demo_gate", _fake_assess)

    out = apply_delivery_soft_floor(
        {
            "mode": "agent_loop",
            "answer": "### 核心结论：见上表",
            "tool_traces": _OK_TRACE,
        },
        user_query="2026-07-20 日活",
    )
    assert out.get("status") == "success"
    assert out.get("delivery_gate") != "calendar_out_of_demo"
