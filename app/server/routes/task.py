from fastapi import APIRouter, HTTPException

from app.core.session import task_store

router = APIRouter(tags=["task"])


@router.get("/task/{task_id}")
def get_task(task_id: str):
    t = task_store.get_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task not found")
    return t
