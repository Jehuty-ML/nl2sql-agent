"""LumenLearn 固定看板配置：slash → 查数 + 画图 + 报告（不经 LLM）。"""

from __future__ import annotations

from typing import Any

# 字段中文标签（表格 / 图表轴）
METRIC_LABELS: dict[str, str] = {
    "dt": "日期",
    "new_learners": "新增学员",
    "dau": "DAU",
    "start_lesson_cnt": "开课次数",
    "complete_lesson_cnt": "完课次数",
    "completion_rate": "完课率",
    "exercise_users": "练习人数",
    "cohort_size": "Cohort 用户数",
    "d1_retained": "次日留存人数",
    "d7_retained": "七日留存人数",
    "d1_rate": "次日留存率",
    "d7_rate": "七日留存率",
    "view_path_uv": "浏览路径 UV",
    "start_lesson_uv": "开课 UV",
    "complete_lesson_uv": "完课 UV",
    "submit_exercise_uv": "交练习 UV",
    "register_channel": "注册渠道",
    "complete_uv": "完课 UV",
    "user_cnt": "用户数",
}

_OVERVIEW_METRICS = [
    "new_learners",
    "dau",
    "start_lesson_cnt",
    "complete_lesson_cnt",
    "completion_rate",
    "exercise_users",
]
_FUNNEL_METRICS = [
    "view_path_uv",
    "start_lesson_uv",
    "complete_lesson_uv",
    "submit_exercise_uv",
]
_RETENTION_METRICS = [
    "cohort_size",
    "d1_retained",
    "d7_retained",
    "d1_rate",
    "d7_rate",
]

# lookback_days：相对 demo 结束日 2026-08-01 的回看偏移（0=当日，6=近7天）
FIXED_DASHBOARD_COMMANDS: dict[str, dict[str, Any]] = {
    "/overview": {
        "title": "学习概览看板",
        "analysis_key": "overview",
        "lookback_days": 29,
        "filename_prefix": "overview",
        "chart_mode": "metric_dashboard",
        "metrics": _OVERVIEW_METRICS,
        "table_mode": "dashboard_summary",
    },
    "/today_dashboard": {
        "title": "今日学习看板",
        "analysis_key": "overview",
        "lookback_days": 0,
        "filename_prefix": "today_dashboard",
        "chart_mode": "metric_dashboard",
        "metrics": _OVERVIEW_METRICS,
        "table_mode": "dashboard_summary",
    },
    "/dau": {
        "title": "日活 DAU 趋势看板",
        "analysis_key": "dau",
        "lookback_days": 29,
        "filename_prefix": "dau",
        "chart_mode": "line",
        "x_axis": "dt",
        "y_axis": "dau",
        "table_mode": "list",
    },
    "/weekly_dau": {
        "title": "近7日 DAU 看板",
        "analysis_key": "dau",
        "lookback_days": 6,
        "filename_prefix": "weekly_dau",
        "chart_mode": "line",
        "x_axis": "dt",
        "y_axis": "dau",
        "table_mode": "list",
    },
    "/retention": {
        "title": "注册留存看板",
        "analysis_key": "retention",
        "lookback_days": 29,
        "filename_prefix": "retention",
        "chart_mode": "metric_dashboard",
        "metrics": _RETENTION_METRICS,
        "table_mode": "dashboard_summary",
    },
    "/weekly_retention": {
        "title": "近7日注册留存看板",
        "analysis_key": "retention",
        "lookback_days": 6,
        "filename_prefix": "weekly_retention",
        "chart_mode": "metric_dashboard",
        "metrics": _RETENTION_METRICS,
        "table_mode": "dashboard_summary",
    },
    "/funnel": {
        "title": "学习漏斗看板",
        "analysis_key": "funnel",
        "lookback_days": 29,
        "filename_prefix": "funnel",
        "chart_mode": "metric_dashboard",
        "metrics": _FUNNEL_METRICS,
        "table_mode": "dashboard_summary",
    },
    "/channel": {
        "title": "渠道完课对比看板",
        "analysis_key": "channel_completion",
        "lookback_days": 29,
        "filename_prefix": "channel",
        "chart_mode": "bar",
        "x_axis": "register_channel",
        "y_axis": "complete_uv",
        "table_mode": "list",
    },
}

SLASH_ALIASES: dict[str, str] = {
    "/daily_dashboard": "/today_dashboard",
    "/weekly_dashboard": "/weekly_dau",
    "/留存": "/retention",
    "/日活": "/dau",
    "/漏斗": "/funnel",
    "/概览": "/overview",
    "/渠道": "/channel",
}


def metric_label(field: str) -> str:
    """列名 → 中文展示名；未知字段原样返回。"""
    key = str(field or "").strip()
    return METRIC_LABELS.get(key, key)


def normalize_dashboard_command(command: str) -> str:
    token = (command or "").strip().split()[0].lower() if (command or "").strip() else ""
    if not token.startswith("/"):
        return ""
    return SLASH_ALIASES.get(token, token)


def get_dashboard_config(command: str) -> dict[str, Any] | None:
    """返回看板配置副本；未知指令返回 None。"""
    resolved = normalize_dashboard_command(command)
    meta = FIXED_DASHBOARD_COMMANDS.get(resolved)
    if not meta:
        return None
    out = dict(meta)
    out["resolved_command"] = resolved
    return out
