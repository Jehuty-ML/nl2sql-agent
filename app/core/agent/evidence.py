"""证据落盘（.scratchpad/evidence）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / ".scratchpad" / "evidence"


def _maybe_spill(task_id: str, name: str, text: str) -> tuple[str, dict[str, Any] | None]:
    """超大 JSON 写入 spill 文件，返回 (storage_text, spill_meta)。"""
    threshold = max(1024, int(settings.spill_threshold_bytes))
    encoded = text.encode("utf-8")
    if len(encoded) <= threshold:
        return text, None

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    spill_name = f"{task_id}_{name}_spill.json"
    spill_path = EVIDENCE_DIR / spill_name
    spill_path.write_text(text, encoding="utf-8")
    rel = str(spill_path.relative_to(ROOT)).replace("\\", "/")
    summary: dict[str, Any] = {"spill_path": rel, "bytes": len(encoded)}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            summary["ok"] = parsed.get("ok")
            summary["grain"] = parsed.get("grain")
            summary["returned_rows"] = parsed.get("returned_rows")
            summary["truncated"] = parsed.get("truncated")
    except json.JSONDecodeError:
        pass
    wrapper = json.dumps({"spilled": True, **summary}, ensure_ascii=False, indent=2)
    return wrapper, summary


def save_evidence(task_id: str, name: str, payload: Any) -> str:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{task_id}_{name}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if isinstance(payload, dict) and isinstance(payload.get("result"), str):
        full_result = payload["result"]
        stored, spill = _maybe_spill(task_id, name, full_result)
        if spill:
            payload = {**payload, "result": stored, "result_spill": spill}

    if isinstance(payload, dict):
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text, _ = _maybe_spill(task_id, name, text)

    path.write_text(text, encoding="utf-8")
    return str(path.relative_to(ROOT)).replace("\\", "/")


def list_evidence_for_task(task_id: str) -> list[str]:
    """列出某 task 下全部证据相对路径（含工具轮次与终态）。"""
    tid = (task_id or "").strip()
    if not tid or not EVIDENCE_DIR.is_dir():
        return []
    out: list[str] = []
    for p in sorted(EVIDENCE_DIR.glob(f"{tid}_*.json")):
        if p.is_file():
            out.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return out


def attach_evidence_index(result: dict[str, Any], task_id: str) -> dict[str, Any]:
    """在 final_result 上补齐 evidence_files，便于前端展示与打包。"""
    files = list_evidence_for_task(task_id)
    if files:
        result["evidence_files"] = files
        if not result.get("evidence_path"):
            result["evidence_path"] = files[-1]
    return result
