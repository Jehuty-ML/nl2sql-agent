"""pipeline pre_execute 单测。"""

import json

from app.config import settings
from app.core.tools.pipeline import ToolPipeline


def test_reject_detail_sql_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "reject_detail_sql", True)
    pipe = ToolPipeline()
    pre = pipe.pre_execute(
        "db_query",
        {"sql": "SELECT distinct_id, event FROM events LIMIT 10"},
    )
    assert pre.blocked is True
    parsed = json.loads(pre.result_json)
    assert parsed["ok"] is False
    assert "hint" in parsed


def test_post_enriches_grain(monkeypatch):
    monkeypatch.setattr(settings, "reject_detail_sql", False)
    tools = {
        "db_query": lambda sql: json.dumps(
            {
                "ok": True,
                "sql": "SELECT register_channel, count() c FROM events GROUP BY register_channel",
                "rows": [{"register_channel": "a", "c": 1}],
                "columns": ["register_channel", "c"],
            },
            ensure_ascii=False,
        )
    }
    pipe = ToolPipeline(tools)
    full = pipe.execute("db_query", {"sql": "SELECT register_channel, count() c FROM events GROUP BY register_channel"})
    full, model, meta = pipe.post_execute("db_query", {}, full)
    parsed = json.loads(full)
    assert parsed.get("grain") == "aggregate"
    assert meta["kind"] == "complete"
