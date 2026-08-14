from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.server.routes import chat, health, task

ROOT = Path(__file__).resolve().parents[2]
WEBUI_DIST = ROOT / "webui" / "dist"
LEGACY_WEB = ROOT / "web"


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(task.router, prefix="/api/v1")

    if WEBUI_DIST.is_dir() and (WEBUI_DIST / "index.html").exists():
        assets = WEBUI_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/")
        def index():
            return FileResponse(
                WEBUI_DIST / "index.html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

    elif (LEGACY_WEB / "index.html").exists():

        @app.get("/")
        def index_legacy():
            return FileResponse(
                LEGACY_WEB / "index.html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

    return app


app = create_app()
