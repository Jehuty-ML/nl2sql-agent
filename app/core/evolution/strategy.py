"""可版本化策略包：system prompt + 运行时旋钮。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.config import settings
from app.core.evolution import store

STRATEGIES_DIR = Path(__file__).resolve().parent / "strategies"

_DEFAULT_PROMPT = """你是 LumenLearn 学习社区的数据分析智能体（ReAct 工具循环）。
只能使用工具【只读】查询 ClickHouse（events/users），禁止编造数字。
【只读硬约束】db_query 只能发 SELECT / WITH … SELECT；禁止 INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER/CREATE 等任何写库或 DDL；禁止一次提交多条语句。写操作会被工具与数据库拒绝。
标准指标优先调用 get_fixed_analysis；需要下钻时再用 db_query。
Demo 数据业务日仅在 2026-05-04 ~ 2026-08-01。调用 get_fixed_analysis 时**默认不要传 start_date/end_date**（省略即用该窗口）；禁止臆造 2024/2025 日期。
表字段（勿臆造列名）：
- users: distinct_id, login_id, register_dt, register_channel, app_id, last_active_dt
- events: distinct_id, identity_login_id, event, dt, app_id, lib, path_id, lesson_id, register_channel, …
渠道字段是 register_channel（不是 channel）。工具若返回 ok=false，请根据 error/hint 改写 SQL 再查，不要直接放弃。
口径：DAU=屏浏览且登录 ID 非空；留存=SignUp cohort + 次日/七日屏浏览；漏斗=浏览路径→开课→完课→交练习。

【并行工具 · PTC】
彼此独立的查数（多个 get_fixed_analysis / db_query）请在同一轮回复里一次发起多个 tool_calls，系统会并行执行以降低延迟。
有依赖的查询（后一条要用前一条结果）再分多轮。
禁止把 export_report 与查数工具一起并行；默认不要调用 export_report。

【不要自动导出】
普通问答只查数 + 在回复里写结论/表格/建议即可。
除非用户明确说「导出报告 / 下载报告 / 保存报告」，否则禁止调用 export_report。
会话收尾落盘请用户用界面「整理并下载报告」，不要自行导出。

【交付格式 · 仅本 Agent 路径】
最终回复用 Markdown：
1. `### …核心结论：` — 趋势与判断；精确 KPI 优先写「见系统表格」；数字必须来自工具；不足则写 `【数据限制】`。
2. `### 支撑数据` — **勿粘贴大段 Markdown 表格**（系统会从查数结果自动展示表格）；可写一两句口径说明。
3. `### 运营策略建议` — 仅在有数据特征可绑定时写；禁止空话；证据不足则明确写不足以给建议并说明缺什么。
（注意：用户若走 /dau 等 slash，系统不会进本 Agent，也不会生成建议——那是固定 SQL 报表通道。）
"""


def list_strategies() -> list[str]:
    if not STRATEGIES_DIR.is_dir():
        return ["v1_baseline"]
    ids = sorted(p.stem for p in STRATEGIES_DIR.glob("*.yaml"))
    return ids or ["v1_baseline"]


def load_strategy(strategy_id: str | None = None) -> dict[str, Any]:
    sid = (strategy_id or "").strip() or store.load_active_strategy_id(
        settings.active_strategy_id
    )
    path = STRATEGIES_DIR / f"{sid}.yaml"
    if not path.is_file():
        return {
            "id": "v1_baseline",
            "prompt": _DEFAULT_PROMPT,
            "knobs": {},
        }
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    prompt = str(data.get("prompt") or _DEFAULT_PROMPT)
    knobs = data.get("knobs") if isinstance(data.get("knobs"), dict) else {}
    return {"id": sid, "prompt": prompt, "knobs": knobs, "meta": data.get("meta") or {}}


def activate_strategy(strategy_id: str) -> dict[str, Any]:
    sid = strategy_id.strip()
    if sid not in list_strategies() and not (STRATEGIES_DIR / f"{sid}.yaml").is_file():
        raise ValueError(f"未知策略: {sid}")
    store.save_active_strategy_id(sid)
    return load_strategy(sid)


def apply_strategy_knobs(strategy: dict[str, Any] | None = None) -> dict[str, Any]:
    """返回生效旋钮（策略覆盖 settings 默认值，不写回全局 settings）。"""
    strat = strategy or load_strategy()
    knobs = dict(strat.get("knobs") or {})
    return {
        "max_parallel_tool_calls": int(
            knobs.get("max_parallel_tool_calls", settings.max_parallel_tool_calls)
        ),
        "model_row_cap": int(knobs.get("model_row_cap", settings.model_row_cap)),
        "reject_detail_sql": bool(
            knobs.get("reject_detail_sql", settings.reject_detail_sql)
        ),
        "enable_plan_mode": bool(
            knobs.get("enable_plan_mode", settings.enable_plan_mode)
        ),
        "enable_numeric_audit": bool(
            knobs.get("enable_numeric_audit", settings.enable_numeric_audit)
        ),
    }
