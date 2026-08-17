"""会话报告打包：Markdown + 原始证据 → zip。"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.server.routes.download import resolve_scratchpad_file

router = APIRouter(tags=["reports"])

ROOT = Path(__file__).resolve().parents[3]


class ReportBundleRequest(BaseModel):
    title: str = "分析报告"
    markdown: str = Field(..., min_length=1)
    """要打进 zip 的 `.scratchpad/` 相对路径（通常是 evidence/*.json）。"""
    paths: list[str] = Field(default_factory=list)


def _safe_entry_name(path: str, used: set[str]) -> str:
    name = Path(path.replace("\\", "/")).name or "file.bin"
    name = re.sub(r"[^\w.\-()+]+", "_", name)
    base = name
    i = 1
    while name in used:
        stem = Path(base).stem
        suffix = Path(base).suffix
        name = f"{stem}_{i}{suffix}"
        i += 1
    used.add(name)
    return name


@router.post("/reports/bundle")
def bundle_session_report(body: ReportBundleRequest):
    """
    打包下载：
    - report.md（内含指向 ./evidence/xxx 的相对链接）
    - evidence/*.json（原始证据）
    解压后用编辑器打开 report.md，可直接点击跳转到证据文件。
    """
    used: set[str] = set()
    files: list[tuple[str, Path]] = []  # (zip_inner_path, abs_path)

    for raw in body.paths:
        try:
            target = resolve_scratchpad_file(raw)
        except HTTPException:
            continue
        entry = f"evidence/{_safe_entry_name(str(target), used)}"
        files.append((entry, target))

    md = body.markdown
    # 若调用方已写相对链接则原样；否则在文末补一份索引（按实际打进 zip 的文件）
    if files and "./evidence/" not in md:
        lines = ["", "## 原始证据（打包内相对路径）", ""]
        for entry, _ in files:
            lines.append(f"- [{Path(entry).name}](./{entry})")
        lines.append("")
        md = md.rstrip() + "\n" + "\n".join(lines)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.md", md.encode("utf-8"))
        for entry, target in files:
            zf.write(target, arcname=entry)

    buf.seek(0)
    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", (body.title or "分析报告").strip()) or "分析报告"
    filename = f"{safe_title[:48]}_bundle.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
