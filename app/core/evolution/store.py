"""进化产物本地存储（.scratchpad/evolution/，默认不入库）。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
EVOLUTION_DIR = _ROOT / ".scratchpad" / "evolution"
_LOCK = threading.RLock()


def evolution_dir() -> Path:
    EVOLUTION_DIR.mkdir(parents=True, exist_ok=True)
    return EVOLUTION_DIR


def _path(*parts: str) -> Path:
    p = evolution_dir().joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read_json(rel: str, default: Any) -> Any:
    path = _path(rel)
    if not path.is_file():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def write_json(rel: str, data: Any) -> None:
    path = _path(rel)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _LOCK:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)


def append_jsonl(rel: str, row: dict[str, Any]) -> None:
    path = _path(rel)
    with _LOCK:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_positive() -> dict[str, Any]:
    return read_json("positive_patterns.json", {"patterns": {}})


def save_positive(data: dict[str, Any]) -> None:
    write_json("positive_patterns.json", data)


def load_negative() -> dict[str, Any]:
    return read_json("negative_tips.json", {"tips": {}})


def save_negative(data: dict[str, Any]) -> None:
    write_json("negative_tips.json", data)


def load_proposals() -> dict[str, Any]:
    return read_json("proposed_skills.json", {"proposals": []})


def save_proposals(data: dict[str, Any]) -> None:
    write_json("proposed_skills.json", data)


def load_overlay() -> dict[str, Any]:
    return read_json(
        "promoted/overlay.json",
        {"fixed_queries": {}, "dashboard_commands": {}, "slash_aliases": {}},
    )


def save_overlay(data: dict[str, Any]) -> None:
    write_json("promoted/overlay.json", data)


def load_active_strategy_id(default: str = "v1_baseline") -> str:
    meta = read_json("active_strategy.json", {})
    sid = str(meta.get("strategy_id") or "").strip()
    return sid or default


def save_active_strategy_id(strategy_id: str) -> None:
    write_json("active_strategy.json", {"strategy_id": strategy_id})


def session_memory_path(session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (session_id or "anon"))
    return _path("sessions", f"{safe}.json")


def load_session_memory(session_id: str) -> dict[str, Any]:
    if not session_id:
        return {"turns": []}
    path = session_memory_path(session_id)
    if not path.is_file():
        return {"session_id": session_id, "turns": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("turns", [])
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"session_id": session_id, "turns": []}


def save_session_memory(session_id: str, data: dict[str, Any]) -> None:
    if not session_id:
        return
    path = session_memory_path(session_id)
    tmp = path.with_suffix(".tmp")
    with _LOCK:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
