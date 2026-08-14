from fastapi import APIRouter

from app.config import settings
from app.core.tools.clickhouse_tool import ping

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    ch_ok = ping()
    llm = settings.resolve_llm()
    return {
        "status": "ok" if ch_ok else "degraded",
        "service": settings.app_name,
        "clickhouse": "up" if ch_ok else "down",
        "llm_enabled": bool(llm["enabled"]),
        "llm_provider": llm["provider"],
        "llm_model": llm["model"],
    }
