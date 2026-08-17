"""报告打包：Markdown + 证据 → zip。"""

import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.routes import download as download_mod
from app.server.routes import reports as reports_mod


def test_bundle_includes_md_and_evidence(tmp_path, monkeypatch):
    scratch = tmp_path / ".scratchpad"
    ev = scratch / "evidence"
    ev.mkdir(parents=True)
    f = ev / "t1_fixed_analysis.json"
    f.write_text('{"ok": true}', encoding="utf-8")
    monkeypatch.setattr(download_mod, "SCRATCHPAD", scratch.resolve())
    monkeypatch.setattr(download_mod, "ROOT", tmp_path.resolve())

    app = FastAPI()
    app.include_router(reports_mod.router, prefix="/api/v1")
    client = TestClient(app)

    md = (
        "# Demo\n\n"
        "### 原始证据\n\n"
        "- [t1_fixed_analysis.json](./evidence/t1_fixed_analysis.json)\n"
    )
    r = client.post(
        "/api/v1/reports/bundle",
        json={
            "title": "Demo",
            "markdown": md,
            "paths": [".scratchpad/evidence/t1_fixed_analysis.json"],
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")

    zf = zipfile.ZipFile(BytesIO(r.content))
    names = set(zf.namelist())
    assert "report.md" in names
    assert "evidence/t1_fixed_analysis.json" in names
    assert b"./evidence/t1_fixed_analysis.json" in zf.read("report.md")
    assert zf.read("evidence/t1_fixed_analysis.json") == b'{"ok": true}'
