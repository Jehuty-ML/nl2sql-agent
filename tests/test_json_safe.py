"""json_safe 单测。"""

import json
import math

from app.core.json_safe import json_safe


def test_nan_inf_to_none():
    cleaned = json_safe({"a": float("nan"), "b": float("inf"), "c": -float("inf"), "d": 1.5})
    assert cleaned["a"] is None
    assert cleaned["b"] is None
    assert cleaned["c"] is None
    assert cleaned["d"] == 1.5
    # 必须能被标准 JSON 编码
    json.dumps(cleaned, allow_nan=False)


def test_nested():
    cleaned = json_safe({"rows": [{"x": math.nan}, {"x": 2}]})
    assert cleaned["rows"][0]["x"] is None
    assert cleaned["rows"][1]["x"] == 2
