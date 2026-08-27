"""工具结果投影：audit 全文 vs model-view。"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.config import settings
from app.core.tools.result_shape import GRAIN_FIXED, SAMPLE_HINT, is_complete_evidence

PRUNE_MARKER = "\n\n[... tool result middle pruned ...]\n\n"


def _json_chars(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _char_prune(text: str, cap: int, head: int, tail: int) -> str:
    if len(text) <= cap:
        return text
    h = text[:head]
    t = text[-tail:] if tail else ""
    return f"{h}{PRUNE_MARKER}{t}"


def project_for_model(full_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """将完整工具 payload 投影为进 LLM 的版本。

    返回 (model_payload, projection_meta)。
    """
    if not isinstance(full_payload, dict):
        meta = {"kind": "raw", "incomplete": True}
        return full_payload, meta

    if not full_payload.get("ok", True) and full_payload.get("ok") is not None:
        return full_payload, {"kind": "error", "incomplete": False}

    cap = max(1, int(settings.model_row_cap))
    sample_n = max(1, int(settings.model_sample_rows))
    char_cap = max(256, int(settings.model_json_char_cap))

    grain = str(full_payload.get("grain") or "")
    truncated = bool(full_payload.get("truncated"))
    rows = full_payload.get("rows") if isinstance(full_payload.get("rows"), list) else []
    returned = int(full_payload.get("returned_rows") or len(rows))

    complete = is_complete_evidence(full_payload) and returned <= cap

    if complete:
        model = deepcopy(full_payload)
        text = _json_chars(model)
        if len(text) > char_cap:
            head = min(char_cap // 2, max(256, char_cap - 1024))
            tail = min(1024, char_cap - head - len(PRUNE_MARKER))
            pruned = _char_prune(text, char_cap, head, tail)
            model = {
                "ok": full_payload.get("ok"),
                "grain": grain,
                "truncated": False,
                "returned_rows": returned,
                "projection_note": "content char-pruned for model context",
                "content_preview": pruned,
            }
            return model, {
                "kind": "pruned_chars",
                "incomplete": False,
                "model_chars": len(pruned),
            }
        return model, {
            "kind": "complete",
            "incomplete": False,
            "model_chars": len(text),
        }

    # 样本包
    sample_rows = rows[:sample_n]
    model: dict[str, Any] = {
        "ok": full_payload.get("ok"),
        "grain": grain or "detail",
        "truncated": True if (truncated or returned > cap or grain not in (GRAIN_FIXED, "aggregate")) else truncated,
        "returned_rows": returned,
        "columns": full_payload.get("columns"),
        "sample_rows": sample_rows,
        "hint": full_payload.get("hint") or SAMPLE_HINT,
    }
    if full_payload.get("analysis_key"):
        model["analysis_key"] = full_payload["analysis_key"]
        model["name"] = full_payload.get("name")
    if full_payload.get("sql"):
        model["sql"] = _char_prune(str(full_payload["sql"]), 600, 400, 150)

    meta = {
        "kind": "sample",
        "incomplete": True,
        "model_chars": len(_json_chars(model)),
    }
    return model, meta


def project_result_string(full_result: str) -> tuple[str, str, dict[str, Any]]:
    """full JSON 字符串 → (full, model_json_str, meta)。"""
    try:
        parsed = json.loads(full_result)
    except (json.JSONDecodeError, TypeError):
        return full_result, full_result, {"kind": "raw", "incomplete": True}

    if not isinstance(parsed, dict):
        return full_result, full_result, {"kind": "raw", "incomplete": True}

    model_payload, meta = project_for_model(parsed)
    model_str = json.dumps(model_payload, ensure_ascii=False, allow_nan=False)
    return full_result, model_str, meta
