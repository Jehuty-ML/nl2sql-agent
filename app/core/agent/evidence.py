"""证据落盘（.scratchpad/evidence）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / ".scratchpad" / "evidence"


def save_evidence(task_id: str, name: str, payload: Any) -> str:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{task_id}_{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
