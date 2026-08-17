"""下载 `.scratchpad/` 下的产物（报告 / 证据等）。"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["download"])

ROOT = Path(__file__).resolve().parents[3]
SCRATCHPAD = (ROOT / ".scratchpad").resolve()


def normalize_scratchpad_relpath(file_path: str) -> str:
    """把客户端传入的路径规范成相对 `.scratchpad/` 的相对路径。"""
    raw = (file_path or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or ":" in raw.split("/")[0]:
        raise HTTPException(status_code=400, detail="invalid path")
    while raw.startswith("./"):
        raw = raw[2:]
    if raw.startswith(".scratchpad/"):
        raw = raw[len(".scratchpad/") :]
    elif raw.startswith("scratchpad/"):
        raw = raw[len("scratchpad/") :]
    raw = raw.lstrip("/")
    if not raw or ".." in raw.split("/"):
        raise HTTPException(status_code=400, detail="invalid path")
    return raw


def resolve_scratchpad_file(file_path: str) -> Path:
    rel = normalize_scratchpad_relpath(file_path)
    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
    target = (SCRATCHPAD / rel).resolve()
    try:
        target.relative_to(SCRATCHPAD)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {rel}")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Requested path is not a file")
    return target


@router.get("/download/{file_path:path}")
def download_scratchpad_file(file_path: str):
    """下载项目 `.scratchpad/` 目录内的单个文件（禁止目录穿越）。"""
    target = resolve_scratchpad_file(file_path)
    guessed, _ = mimetypes.guess_type(str(target))
    media_type = guessed or "application/octet-stream"
    # 图片可内联预览；其余强制下载
    inline_preview = target.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
    if inline_preview:
        return FileResponse(target, media_type=media_type)
    return FileResponse(
        target,
        filename=target.name,
        media_type=media_type,
    )
