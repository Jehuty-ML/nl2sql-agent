from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.session import task_store

router = APIRouter(tags=["task"])


class AbortBody(BaseModel):
    reason: str = Field("用户中止或僵尸任务清理", description="中止原因")


@router.get("/task/{task_id}")
def get_task(task_id: str):
    t = task_store.get_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task not found")
    return t


@router.post("/task/{task_id}/abort")
def abort_task(task_id: str, body: AbortBody | None = None):
    reason = (body.reason if body else None) or "用户中止或僵尸任务清理"
    t = task_store.abort_task(task_id, reason)
    if not t:
        raise HTTPException(status_code=404, detail="task not found")
    return t
