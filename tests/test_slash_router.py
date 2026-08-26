"""固定看板 slash：路由 + 画图（不经 LLM，可无 ClickHouse）。"""

from __future__ import annotations

from pathlib import Path

from app.bi.fixed_dashboard import FIXED_DASHBOARD_COMMANDS, get_dashboard_config
from app.core.agent.fixed_dashboard import _build_answer_markdown, _make_chart, resolve_date_range
from app.core.routing.slash_router import normalize_slash, route_input
from app.core.tools.report_tool import generate_chart, generate_metric_dashboard_chart


def test_fixed_slash_dau_is_dashboard():
    r = route_input("/dau")
    assert r["execution_path"] == "fixed_slash"
    assert r["analysis_key"] == "dau"
    assert r["dashboard"] is True
    assert r["resolved_command"] == "/dau"


def test_today_dashboard_is_first_class():
    r = route_input("/today_dashboard")
    assert r["execution_path"] == "fixed_slash"
    assert r["resolved_command"] == "/today_dashboard"
    assert r["analysis_key"] == "overview"
    assert r["lookback_days"] == 0


def test_daily_dashboard_alias():
    assert normalize_slash("/daily_dashboard") == "/today_dashboard"
    r = route_input("/daily_dashboard")
    assert r["resolved_command"] == "/today_dashboard"


def test_weekly_commands():
    assert route_input("/weekly_dau")["analysis_key"] == "dau"
    assert route_input("/weekly_retention")["analysis_key"] == "retention"
    assert route_input("/weekly_dashboard")["resolved_command"] == "/weekly_dau"


def test_natural_language_goes_agent_loop():
    r = route_input("最近日活怎么样")
    assert r["execution_path"] == "agent_loop"


def test_unknown_slash():
    r = route_input("/not_exist")
    assert r["execution_path"] == "unknown_slash"


def test_normalize():
    assert normalize_slash("/Funnel extra") == "/funnel"


def test_all_commands_have_analysis_keys():
    for cmd, meta in FIXED_DASHBOARD_COMMANDS.items():
        assert meta.get("analysis_key")
        assert get_dashboard_config(cmd) is not None


def test_resolve_date_range():
    start, end = resolve_date_range(6)
    assert end == "2026-08-01"
    assert start == "2026-07-26"
    start0, end0 = resolve_date_range(0)
    assert start0 == end0 == "2026-08-01"


def test_generate_line_chart(tmp_path, monkeypatch):
    import app.core.tools.report_tool as rt

    monkeypatch.setattr(rt, "ROOT", tmp_path)
    monkeypatch.setattr(rt, "SCRATCHPAD", tmp_path / ".scratchpad")
    monkeypatch.setattr(rt, "REPORT_DIR", tmp_path / ".scratchpad" / "reports")

    rows = [{"dt": "2026-07-30", "dau": 10}, {"dt": "2026-07-31", "dau": 12}]
    path = generate_chart(
        rows,
        chart_type="line",
        title="DAU",
        filename="test_dau.png",
        x_axis="dt",
        y_axis="dau",
    )
    assert not path.startswith("Error:")
    assert path.endswith(".png")
    assert (tmp_path / ".scratchpad" / "reports" / Path(path).name).is_file()


def test_generate_metric_dashboard_chart(tmp_path, monkeypatch):
    import app.core.tools.report_tool as rt

    monkeypatch.setattr(rt, "ROOT", tmp_path)
    monkeypatch.setattr(rt, "SCRATCHPAD", tmp_path / ".scratchpad")
    monkeypatch.setattr(rt, "REPORT_DIR", tmp_path / ".scratchpad" / "reports")

    rows = [{"new_learners": 3, "dau": 20, "completion_rate": 0.4}]
    path = generate_metric_dashboard_chart(
        rows,
        title="概览",
        filename="test_overview.png",
        metrics=["new_learners", "dau", "completion_rate"],
    )
    assert not path.startswith("Error:")
    assert (tmp_path / ".scratchpad" / "reports" / Path(path).name).is_file()


def test_make_chart_and_answer_markdown(tmp_path, monkeypatch):
    import app.core.agent.fixed_dashboard as fd
    import app.core.tools.report_tool as rt

    monkeypatch.setattr(rt, "ROOT", tmp_path)
    monkeypatch.setattr(rt, "SCRATCHPAD", tmp_path / ".scratchpad")
    monkeypatch.setattr(rt, "REPORT_DIR", tmp_path / ".scratchpad" / "reports")

    cfg = get_dashboard_config("/funnel")
    assert cfg is not None
    rows = [
        {
            "view_path_uv": 100,
            "start_lesson_uv": 60,
            "complete_lesson_uv": 40,
            "submit_exercise_uv": 20,
        }
    ]
    chart = _make_chart(rows, cfg, task_id="t_demo")
    assert chart and not chart.startswith("Error:")
    md = _build_answer_markdown(
        title=cfg["title"],
        start_date="2026-07-02",
        end_date="2026-08-01",
        rows=rows,
        columns=list(rows[0].keys()),
        chart_path=chart,
        config=cfg,
    )
    assert "固定看板（不经 LLM）" in md
    assert "![图表]" in md
    assert "浏览路径 UV" in md
