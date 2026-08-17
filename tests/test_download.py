"""`.scratchpad` 下载路由：路径规范化与穿越防护。"""

import pytest
from fastapi import HTTPException

from app.server.routes import download as download_mod
from app.server.routes.download import normalize_scratchpad_relpath, resolve_scratchpad_file


def test_normalize_strips_scratchpad_prefix():
    assert normalize_scratchpad_relpath(".scratchpad/reports/a.md") == "reports/a.md"
    assert normalize_scratchpad_relpath("scratchpad/reports/a.md") == "reports/a.md"
    assert normalize_scratchpad_relpath("reports/a.md") == "reports/a.md"


def test_normalize_rejects_traversal():
    with pytest.raises(HTTPException) as ei:
        normalize_scratchpad_relpath("../requirements.txt")
    assert ei.value.status_code == 400

    with pytest.raises(HTTPException) as ei2:
        normalize_scratchpad_relpath("reports/../../secrets.txt")
    assert ei2.value.status_code == 400


def test_resolve_reads_existing_file(tmp_path, monkeypatch):
    scratch = tmp_path / ".scratchpad"
    target_dir = scratch / "reports"
    target_dir.mkdir(parents=True)
    f = target_dir / "demo.md"
    f.write_text("# hi\n", encoding="utf-8")

    monkeypatch.setattr(download_mod, "SCRATCHPAD", scratch.resolve())
    monkeypatch.setattr(download_mod, "ROOT", tmp_path.resolve())

    got = resolve_scratchpad_file("reports/demo.md")
    assert got == f.resolve()
    assert got.read_text(encoding="utf-8") == "# hi\n"


def test_resolve_missing_file(tmp_path, monkeypatch):
    scratch = tmp_path / ".scratchpad"
    scratch.mkdir()
    monkeypatch.setattr(download_mod, "SCRATCHPAD", scratch.resolve())

    with pytest.raises(HTTPException) as ei:
        resolve_scratchpad_file("reports/missing.md")
    assert ei.value.status_code == 404


def test_download_endpoint(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    scratch = tmp_path / ".scratchpad"
    (scratch / "reports").mkdir(parents=True)
    f = scratch / "reports" / "out.md"
    f.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(download_mod, "SCRATCHPAD", scratch.resolve())

    app = FastAPI()
    app.include_router(download_mod.router)
    client = TestClient(app)

    r = client.get("/download/reports/out.md")
    assert r.status_code == 200
    assert r.text == "ok"

    bad = client.get("/download/../out.md")
    assert bad.status_code in (400, 403, 404)
