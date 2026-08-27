"""numeric_audit 单测。"""

from app.core.agent.numeric_audit import audit_answer


def test_warn_missing_kpi():
    traces = [
        {
            "tool": "db_query",
            "ok": True,
            "table": {"rows": [{"dau": 1523}], "columns": ["dau"]},
        }
    ]
    report = audit_answer("### 核心结论：日活 1800，需关注。", traces)
    assert len(report.flagged) >= 1


def test_no_warn_when_match():
    traces = [
        {
            "tool": "db_query",
            "ok": True,
            "table": {"rows": [{"dau": 1523}], "columns": ["dau"]},
        }
    ]
    report = audit_answer("### 核心结论：日活 1523。", traces)
    assert report.flagged == []


def test_approx_no_warn():
    traces = [
        {
            "tool": "db_query",
            "ok": True,
            "table": {"rows": [{"dau": 1523}], "columns": ["dau"]},
        }
    ]
    report = audit_answer("日活约 1500", traces)
    assert report.flagged == []
