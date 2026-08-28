"""table_selection 单测。"""

from app.core.agent.table_selection import select_display_tables


def test_select_complete_traces():
    traces = [
        {
            "tool": "get_fixed_analysis",
            "ok": True,
            "grain": "fixed",
            "truncated": False,
            "projection": {"kind": "complete", "incomplete": False},
            "table": {
                "name": "DAU",
                "rows": [{"dau": 1}],
                "columns": ["dau"],
            },
        },
        {
            "tool": "db_query",
            "ok": True,
            "grain": "detail",
            "truncated": True,
            "projection": {"kind": "sample", "incomplete": True},
            "table": {"name": "x", "rows": [{"a": 1}], "columns": ["a"]},
        },
    ]
    tables = select_display_tables(traces)
    assert len(tables) == 1
    assert tables[0]["label"] == "DAU"
