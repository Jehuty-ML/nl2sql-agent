"""自进化管理 API：提案列表 / promote / 策略切换。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.core.evolution.proposer import list_proposals, maybe_propose_skills
from app.core.evolution.promote import promote_proposal
from app.core.evolution.registry import fixed_query_keys, get_dashboard_commands
from app.core.evolution.strategy import activate_strategy, list_strategies, load_strategy

router = APIRouter(tags=["evolution"])


def _require_evolution() -> None:
    if not settings.enable_evolution:
        raise HTTPException(
            status_code=503,
            detail=(
                "自进化未开启。请在 .env 设置 ENABLE_EVOLUTION=true 后重启服务。"
                "详见 docs/self-evolution.md"
            ),
        )


class PromoteRequest(BaseModel):
    proposal_id: str = Field(..., min_length=1)
    skip_execute: bool = Field(
        False,
        description="True 则跳过 ClickHouse 试跑（仅 sql_guard）；默认试跑",
    )


class StrategyActivateRequest(BaseModel):
    strategy_id: str = Field(..., min_length=1)


@router.get("/evolution/status")
def evolution_status():
    """开关状态（关闭时也可查询，便于前端/运维确认）。"""
    from app.core.evolution.feedback import list_pending_patches

    return {
        "enabled": bool(settings.enable_evolution),
        "active_strategy_id": settings.active_strategy_id,
        "pattern_threshold": int(settings.evolution_pattern_threshold),
        "pending_strategy_patches": list_pending_patches() if settings.enable_evolution else [],
        "hint": (
            None
            if settings.enable_evolution
            else "在 .env 设置 ENABLE_EVOLUTION=true 并重启以打开自进化"
        ),
    }


@router.get("/evolution/proposals")
def evolution_proposals(pending_only: bool = False):
    _require_evolution()
    maybe_propose_skills()
    return {"proposals": list_proposals(pending_only=pending_only)}


@router.post("/evolution/promote")
def evolution_promote(body: PromoteRequest):
    _require_evolution()
    try:
        out = promote_proposal(body.proposal_id, skip_execute=body.skip_execute)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "promote failed")
    return out


@router.get("/evolution/strategies")
def evolution_strategies():
    _require_evolution()
    active = load_strategy()
    return {
        "active": active.get("id"),
        "strategies": list_strategies(),
        "knobs": active.get("knobs") or {},
    }


@router.post("/evolution/strategies/activate")
def evolution_activate_strategy(body: StrategyActivateRequest):
    _require_evolution()
    try:
        strat = activate_strategy(body.strategy_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "strategy": {"id": strat.get("id"), "knobs": strat.get("knobs")}}


@router.get("/evolution/registry")
def evolution_registry():
    # registry 只读合并结果；关闭进化时仍可读内置+已 promote 的 overlay
    return {
        "evolution_enabled": bool(settings.enable_evolution),
        "fixed_keys": fixed_query_keys(),
        "slash_commands": list(get_dashboard_commands().keys()),
    }
