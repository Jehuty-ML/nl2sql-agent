import threading

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.agent.react_engine import run_agent
from app.core.session import task_store

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="自然语言分析问题")
    sync: bool = Field(False, description="True 则同步返回结果；默认异步任务")


@router.post("/chat")
def chat(req: ChatRequest):
    task_id = task_store.create_task(req.query)
    if req.sync:
        result = run_agent(task_id, req.query)
        return {"task_id": task_id, "status": "succeeded", "result": result}

    threading.Thread(target=run_agent, args=(task_id, req.query), daemon=True).start()
    return {
        "task_id": task_id,
        "status": "accepted",
        "poll": f"/api/v1/task/{task_id}",
    }
