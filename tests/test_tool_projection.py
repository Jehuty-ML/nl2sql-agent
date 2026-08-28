"""tool_projection 单测。"""

import json

from app.core.agent.tool_projection import project_for_model, project_result_string


def test_complete_small_aggregate():
    payload = {
        "ok": True,
        "grain": "aggregate",
        "truncated": False,
        "returned_rows": 2,
        "rows": [{"a": 1}, {"a": 2}],
        "columns": ["a"],
    }
    model, meta = project_for_model(payload)
    assert meta["kind"] == "complete"
    assert meta["incomplete"] is False
    assert len(model["rows"]) == 2


def test_sample_when_truncated():
    payload = {
        "ok": True,
        "grain": "detail",
        "truncated": True,
        "returned_rows": 500,
        "rows": [{"id": i} for i in range(10)],
        "columns": ["id"],
    }
    model, meta = project_for_model(payload)
    assert meta["kind"] == "sample"
    assert meta["incomplete"] is True
    assert "sample_rows" in model
    assert len(model["sample_rows"]) <= 5
    assert "rows" not in model or len(model.get("rows") or []) <= 5


def test_project_result_string_roundtrip():
    full = json.dumps({"ok": True, "grain": "fixed", "truncated": False, "returned_rows": 1, "rows": [{"x": 1}]})
    full_out, model_str, meta = project_result_string(full)
    assert full_out == full
    model = json.loads(model_str)
    assert model["rows"][0]["x"] == 1
    assert meta["kind"] == "complete"
