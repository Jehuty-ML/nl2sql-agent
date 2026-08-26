"""输入路由：slash 前置拦截。

- `/xxx` 固定看板指令 → fixed_slash（不进 LLM：查数 + 画图 + 报告）
- 其它自然语言 → agent_loop（有 LLM 则 ReAct；无 LLM 则提示用 slash）
"""

from __future__ import annotations

from typing import Any

from app.bi.fixed_dashboard import (
    FIXED_DASHBOARD_COMMANDS,
    SLASH_ALIASES,
)


def normalize_slash(text: str) -> str:
    token = (text or "").strip().split()[0].lower() if (text or "").strip() else ""
    if not token.startswith("/"):
        return ""
    return SLASH_ALIASES.get(token, token)


def route_input(text: str) -> dict[str, Any]:
    """返回 routing 决策（execution_path / resolved_command / analysis_key 等）。"""
    stripped = (text or "").strip()
    if not stripped:
        return {
            "execution_path": "unknown",
            "reason_codes": ["empty_input"],
            "human_reason": "空输入",
        }

    if stripped.startswith("/"):
        cmd = normalize_slash(stripped)
        if cmd == "/help":
            return {
                "execution_path": "slash_help",
                "resolved_command": "/help",
                "reason_codes": ["slash_help"],
                "human_reason": "帮助指令",
            }
        if cmd in FIXED_DASHBOARD_COMMANDS:
            meta = FIXED_DASHBOARD_COMMANDS[cmd]
            return {
                "execution_path": "fixed_slash",
                "resolved_command": cmd,
                "analysis_key": meta["analysis_key"],
                "name": meta["title"],
                "dashboard": True,
                "lookback_days": meta.get("lookback_days", 29),
                "reason_codes": ["slash_fixed_dashboard"],
                "human_reason": f"固定看板 slash 拦截：{cmd}",
            }
        return {
            "execution_path": "unknown_slash",
            "resolved_command": cmd,
            "reason_codes": ["unknown_slash_command"],
            "human_reason": f"未知 slash 指令 `{cmd}`",
        }

    return {
        "execution_path": "agent_loop",
        "reason_codes": ["natural_language"],
        "human_reason": "自然语言，进入 Agent 循环",
    }


def help_text() -> str:
    lines = [
        "固定看板指令（**不经过大模型**，查数 + 画图 + 报告）：",
        "",
    ]
    for cmd, meta in FIXED_DASHBOARD_COMMANDS.items():
        lines.append(f"- `{cmd}`：{meta['title']}")
    lines.append("- `/help`：查看本帮助")
    lines.append("")
    lines.append("自然语言问题会进入 Agent（需配置 LLM）；也可在 Agent 内调用 get_fixed_analysis 工具。")
    return "\n".join(lines)
