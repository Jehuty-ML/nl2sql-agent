"""交付完整性薄地板单测。"""

from app.core.agent.delivery_floor import (
    NOTICE_EMPTY_ROWS,
    NOTICE_NO_OK_QUERY,
    apply_delivery_soft_floor,
    assess_query_evidence,
)


def test_assess_ok_with_rows():
    traces = [
        {
            "tool": "db_query",
            "ok": True,
            "row_count": 3,
            "table": {"rows": [{"a": 1}], "row_count": 3},
        }
    ]
    a = assess_query_evidence(traces)
    assert a["has_ok_query"] is True
    assert a["has_nonempty_rows"] is True
    assert a["reason"] == "none"


def test_assess_ok_empty_rows():
    traces = [{"tool": "get_fixed_analysis", "ok": True, "row_count": 0}]
    a = assess_query_evidence(traces)
    assert a["has_ok_query"] is True
    assert a["reason"] == "empty_rows"


def test_assess_missing_ok():
    traces = [
        {"tool": "db_query", "ok": False, "result_preview": '{"ok": false}'},
        {"tool": "export_report", "ok": True},
    ]
    a = assess_query_evidence(traces)
    assert a["called_query"] is True
    assert a["has_ok_query"] is False
    assert a["reason"] == "missing_ok_query"


def test_soft_floor_keeps_answer_on_missing():
    original = "### 核心结论：日活很好"
    out = apply_delivery_soft_floor(
        {
            "mode": "agent_loop",
            "answer": original,
            "tool_traces": [],
        }
    )
    assert out["status"] == "partial"
    assert out["delivery_gate"] == "missing_ok_query"
    assert NOTICE_NO_OK_QUERY in out["answer"]
    assert original in out["answer"]
    assert out["tool_traces"] == []


def test_soft_floor_empty_rows_prefix():
    out = apply_delivery_soft_floor(
        {
            "mode": "agent_loop",
            "answer": "【数据限制】无行",
            "tool_traces": [{"tool": "db_query", "ok": True, "row_count": 0}],
        }
    )
    assert out["status"] == "partial"
    assert NOTICE_EMPTY_ROWS in out["answer"]
    assert "【数据限制】无行" in out["answer"]


def test_soft_floor_passthrough_with_evidence():
    out = apply_delivery_soft_floor(
        {
            "mode": "agent_loop",
            "answer": "结论 OK",
            "tool_traces": [
                {
                    "tool": "db_query",
                    "ok": True,
                    "row_count": 2,
                    "table": {"rows": [{"x": 1}, {"x": 2}], "row_count": 2},
                }
            ],
        }
    )
    assert out.get("status") == "success"
    assert out["answer"] == "结论 OK"
    assert "delivery_notice" not in out


def test_soft_floor_ignores_slash():
    out = apply_delivery_soft_floor(
        {"mode": "fixed_slash", "answer": "报表", "tool_traces": []}
    )
    assert "delivery_notice" not in out
    assert out["answer"] == "报表"


def test_soft_floor_no_duplicate_notice():
    body = f"{NOTICE_NO_OK_QUERY}\n\n已说明"
    out = apply_delivery_soft_floor(
        {"mode": "agent_loop", "answer": body, "tool_traces": []}
    )
    assert out["answer"].count(NOTICE_NO_OK_QUERY) == 1
