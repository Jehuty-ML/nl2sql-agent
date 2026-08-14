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
    return str(path.relative_to(ROOT))
