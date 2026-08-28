"""JSON 安全化：剔除 NaN/Inf，避免 FastAPI / 标准 JSON 序列化 500。"""

from __future__ import annotations

import math
from typing import Any


def json_safe(obj: Any) -> Any:
    """递归把非 JSON 合规的 float 换成 None，其它结构原样拷贝。"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if isinstance(obj, tuple):
        return [json_safe(v) for v in obj]
    return obj
