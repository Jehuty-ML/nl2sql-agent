"""固定看板执行：注册 SQL + 画图 + Markdown 报告（不经 LLM）。"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Callable

from app.bi.fixed_dashboard import get_dashboard_config, metric_label
from app.core.tools.fixed_analysis import run_fixed_analysis
from app.core.tools.report_tool import (
    generate_chart,
    generate_metric_dashboard_chart,
    rows_to_markdown_table,
    tool_export_analysis_report,
)

# 与合成 demo 数据结束日对齐（见 fixed_analysis.default_date_range）
_DEMO_END = date(2026, 8, 1)

ProgressCb = Callable[[str, str], None]


def resolve_date_range(lookback_days: int) -> tuple[str, str]:
    """按 lookback 偏移生成 [start, end]；end 固定 demo 日。"""
    end = _DEMO_END
    start = end - timedelta(days=max(0, int(lookback_days)))
    return start.isoformat(), end.isoformat()


def _format_cell(key: str, value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "是" if value else "否"
    kl = str(key).lower()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        num = float(value)
        if kl.endswith(("_rate", "_pct", "_ratio")):
            if 0 <= num <= 1:
                return f"{num * 100:.2f}%"
            return f"{num:.2f}%"
        if isinstance(value, float) and not num.is_integer():
            return f"{num:.4g}"
        if isinstance(value, float) and num.is_integer():
            return f"{int(num):,}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)
    return str(value).replace("|", "\\|").replace("\n", " ") or "-"


def _build_metric_table(row: dict[str, Any], metrics: list[str] | None = None) -> str:
    fields = [m for m in (metrics or list(row.keys())) if m in row]
    if not fields:
        fields = list(row.keys())
    lines = ["| 指标 | 数值 |", "| --- | ---: |"]
    for field in fields:
        lines.append(
            f"| {metric_label(field)} | {_format_cell(field, row.get(field))} |"
        )
    return "\n".join(lines)


def _build_answer_markdown(
    *,
    title: str,
    start_date: str,
    end_date: str,
    rows: list[dict[str, Any]],
    columns: list[str],
    chart_path: str,
    config: dict[str, Any],
) -> str:
    lines = [
        f"## {title}",
        "- 模式：固定看板（不经 LLM）",
        f"- 时间范围：{start_date} 至 {end_date}",
        f"- 行数：{len(rows)}",
        "",
    ]
    if not rows:
        lines.append("当前时间范围未查询到数据。")
        return "\n".join(lines)

    table_mode = config.get("table_mode") or "list"
    metrics = config.get("metrics")
    if table_mode == "dashboard_summary" and len(rows) == 1:
        lines.append(_build_metric_table(rows[0], metrics if isinstance(metrics, list) else None))
    else:
        cols = list(columns) if columns else list(rows[0].keys())
        lines.append(rows_to_markdown_table(cols, rows))

    if chart_path and not str(chart_path).startswith("Error:"):
        lines.extend(["", f"![图表]({chart_path})"])
    return "\n".join(lines)


def _make_chart(
    rows: list[dict[str, Any]],
    cfg: dict[str, Any],
    task_id: str = "",
) -> str:
    """按看板配置画图；失败返回 `Error: ...`。"""
    if not rows:
        return "Error: Data is empty."
    if cfg.get("skip_chart"):
        return ""

    prefix = str(cfg.get("filename_prefix") or "dashboard")
    safe_task = (task_id or "x").replace("/", "_")
    filename = f"{prefix}_{safe_task}.png"
    title = str(cfg.get("title") or "看板")
    mode = str(cfg.get("chart_mode") or "metric_dashboard")

    if mode == "metric_dashboard":
        return generate_metric_dashboard_chart(
            data=rows,
            title=title,
            filename=filename,
            x_axis=cfg.get("x_axis"),
            metrics=cfg.get("metrics"),
        )
    if mode == "line":
        return generate_chart(
            data=rows,
            chart_type="line",
            title=title,
            filename=filename,
            x_axis=cfg.get("x_axis"),
            y_axis=cfg.get("y_axis"),
        )
    return generate_chart(
        data=rows,
        chart_type="bar",
        title=title,
        filename=filename,
        x_axis=cfg.get("x_axis"),
        y_axis=cfg.get("y_axis"),
    )


def _emit(progress_cb: ProgressCb | None, step: str, detail: str = "") -> None:
    if progress_cb:
        progress_cb(step, detail)


def run_fixed_dashboard(
    command: str,
    task_id: str,
    progress_cb: ProgressCb | None = None,
) -> dict[str, Any]:
    """执行固定看板：查数 → 画图 → 写 Markdown 报告。全程不调用 LLM。"""
    cfg = get_dashboard_config(command)
    if not cfg:
        return {
            "ok": False,
            "answer": f"未知看板指令：{command}",
            "error": f"未知看板指令：{command}",
            "data": {},
        }

    resolved = str(cfg.get("resolved_command") or command)
    analysis_key = str(cfg["analysis_key"])
    lookback = int(cfg.get("lookback_days", 29))
    start_date, end_date = resolve_date_range(lookback)
    title = str(cfg.get("title") or analysis_key)

    routing = {
        "execution_path": "fixed_slash",
        "resolved_command": resolved,
        "analysis_key": analysis_key,
        "name": title,
        "dashboard": True,
        "lookback_days": lookback,
        "reason_codes": ["slash_fixed_dashboard"],
        "human_reason": f"固定看板 slash 拦截：{resolved}",
    }

    _emit(
        progress_cb,
        "固定看板 slash",
        f"{resolved} → {analysis_key}（跳过 LLM，查数 + 画图 + 报告）",
    )

    payload = run_fixed_analysis(analysis_key, start_date, end_date)
    if not payload.get("ok"):
        err = str(payload.get("error") or "固定看板查询失败")
        _emit(progress_cb, "查询失败", err[:320])
        return {
            "ok": False,
            "answer": err,
            "error": err,
            "routing": routing,
            "data": payload,
        }

    rows = [r for r in (payload.get("rows") or []) if isinstance(r, dict)]
    columns = list(payload.get("columns") or (list(rows[0].keys()) if rows else []))
    _emit(progress_cb, "查询完成", f"{len(rows)} 行 · {start_date}~{end_date}")

    chart_path = ""
    if rows and not cfg.get("skip_chart"):
        _emit(progress_cb, "生成图表", title)
        chart_raw = _make_chart(rows, cfg, task_id=task_id)
        if chart_raw and not str(chart_raw).startswith("Error:"):
            chart_path = chart_raw
        elif chart_raw:
            _emit(progress_cb, "图表跳过", str(chart_raw)[:240])

    answer = _build_answer_markdown(
        title=title,
        start_date=start_date,
        end_date=end_date,
        rows=rows,
        columns=columns,
        chart_path=chart_path,
        config=cfg,
    )

    report: dict[str, Any] | None = None
    _emit(progress_cb, "导出报告", "写入 Markdown 报告文件")
    report_payload = {
        **payload,
        "name": title,
        "chart_path": chart_path,
        "rows": rows,
        "columns": columns,
    }
    try:
        report = json.loads(
            tool_export_analysis_report(
                json.dumps(report_payload, ensure_ascii=False),
                title=title,
            )
        )
    except Exception as exc:  # noqa: BLE001 — 报告失败不阻断看板答案
        _emit(progress_cb, "报告跳过", str(exc)[:240])
        report = {"ok": False, "error": str(exc)}

    data = {
        "analysis_key": analysis_key,
        "name": title,
        "row_count": len(rows),
        "columns": columns,
        "rows": rows,
        "sql": payload.get("sql"),
        "start_date": start_date,
        "end_date": end_date,
        "chart_path": chart_path or None,
    }
    out: dict[str, Any] = {
        "ok": True,
        "answer": answer,
        "routing": routing,
        "data": data,
    }
    if chart_path:
        out["chart_path"] = chart_path
    if report:
        out["report"] = report
    return out
