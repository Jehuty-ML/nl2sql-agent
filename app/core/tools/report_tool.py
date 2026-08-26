"""报表导出 + 图表生成（Markdown / PNG；不经 LLM）。"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from app.bi.fixed_dashboard import metric_label

ROOT = Path(__file__).resolve().parents[3]
SCRATCHPAD = ROOT / ".scratchpad"
REPORT_DIR = SCRATCHPAD / "reports"

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def ensure_report_dir() -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR


def _rel_scratchpad(path: Path) -> str:
    return path.resolve().relative_to(SCRATCHPAD.resolve()).as_posix()


def _unique_png_path(filename: str) -> Path:
    ensure_report_dir()
    name = Path(filename).name.replace("/", "_").replace("\\", "_")
    if not name.endswith(".png"):
        name += ".png"
    path = REPORT_DIR / name
    if path.exists():
        stem = path.stem
        path = REPORT_DIR / f"{stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    return path


def export_markdown(title: str, content: str, filename: str = "") -> str:
    ensure_report_dir()
    name = filename or f"report_{title}.md"
    name = name.replace("/", "_").replace("\\", "_")
    if not name.endswith(".md"):
        name += ".md"
    path = REPORT_DIR / name
    path.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
    return json.dumps(
        {
            "ok": True,
            "path": f".scratchpad/{_rel_scratchpad(path)}",
            "abs_path": str(path),
        },
        ensure_ascii=False,
    )


def format_cell_value(key: str, value: Any) -> str:
    """表格单元格展示：比率转百分比，控制浮点精度。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        kl = str(key).lower()
        num = float(value)
        if kl.endswith("_rate") or kl.endswith("_pct") or kl.endswith("_ratio"):
            if 0 <= num <= 1:
                return f"{num * 100:.2f}%"
            return f"{num:.2f}%"
        if isinstance(value, float) and not num.is_integer():
            return f"{num:.4g}"
        if isinstance(value, float) and num.is_integer():
            return str(int(num))
        return str(value)
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text


def rows_to_markdown_table(columns: list[str], rows: list[dict[str, Any]]) -> str:
    cols = list(columns) if columns else (list(rows[0].keys()) if rows else [])
    if not cols:
        return "_空结果_"
    header = "| " + " | ".join(metric_label(c) for c in cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines = [header, sep]
    for r in rows[:50]:
        lines.append(
            "| " + " | ".join(format_cell_value(c, r.get(c, "")) for c in cols) + " |"
        )
    return "\n".join(lines)


def tool_export_analysis_report(payload_json: str, title: str = "分析报告") -> str:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as e:
        return json.dumps({"ok": False, "error": f"JSON 解析失败: {e}"}, ensure_ascii=False)
    cols = payload.get("columns") or []
    rows = payload.get("rows") or []
    chart_path = str(payload.get("chart_path") or "").strip()
    body = [
        f"- analysis: {payload.get('name') or payload.get('analysis_key') or '-'}",
        f"- range: {payload.get('start_date')} ~ {payload.get('end_date')}",
        f"- rows: {payload.get('row_count', len(rows))}",
        "",
        "## SQL",
        "```sql",
        str(payload.get("sql") or ""),
        "```",
        "",
        "## 结果",
        rows_to_markdown_table(cols, rows),
    ]
    if chart_path:
        body.extend(["", "## 图表", f"![图表]({chart_path})"])
    return export_markdown(title, "\n".join(body), filename=f"{title}.md")


def _format_chart_value(value: Any) -> str:
    try:
        numeric = float(pd.to_numeric(value, errors="coerce"))
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(numeric):
        return str(value)
    if abs(numeric) >= 1000:
        return f"{numeric:,.0f}"
    if float(numeric).is_integer():
        return str(int(numeric))
    return f"{numeric:,.2f}".rstrip("0").rstrip(".")


def _as_row_dicts(data: list[dict[str, Any]] | dict[str, Any] | str) -> list[dict[str, Any]]:
    if isinstance(data, str):
        parsed = json.loads(data)
        return _as_row_dicts(parsed)
    if isinstance(data, dict):
        if isinstance(data.get("rows"), list):
            return [r for r in data["rows"] if isinstance(r, dict)]
        if isinstance(data.get("data"), list):
            return [r for r in data["data"] if isinstance(r, dict)]
        return [data]
    return [r for r in data if isinstance(r, dict)]


def generate_chart(
    data: list[dict[str, Any]] | dict[str, Any] | str,
    chart_type: str = "bar",
    title: str = "图表",
    filename: str = "chart.png",
    x_axis: str | None = None,
    y_axis: str | None = None,
) -> str:
    """生成单图（bar/line）。成功返回 `.scratchpad/reports/...` 相对路径，失败返回 `Error: ...`。"""
    try:
        rows = _as_row_dicts(data)
        if not rows:
            return "Error: Data is empty."
        df = pd.DataFrame(rows)
        cols = list(df.columns)
        if not x_axis or x_axis not in cols:
            x_axis = cols[0]
        if not y_axis or y_axis not in cols:
            y_axis = next((c for c in cols if c != x_axis), cols[-1])

        df = df.copy()
        df[y_axis] = pd.to_numeric(df[y_axis], errors="coerce").fillna(0)

        fig, ax = plt.subplots(figsize=(10, 5.5), dpi=160)
        x_labels = df[x_axis].astype(str)
        y_values = df[y_axis]

        if chart_type == "line":
            ax.plot(x_labels, y_values, marker="o", linewidth=2.4, color="#3B6EA5")
            ax.fill_between(range(len(y_values)), y_values, alpha=0.12, color="#3B6EA5")
        else:
            colors = plt.cm.Blues([0.45 + 0.4 * (i / max(len(df), 1)) for i in range(len(df))])
            ax.bar(x_labels, y_values, color=colors, edgecolor="white", linewidth=1.1)

        ax.set_title(title, fontsize=14, fontweight="bold", color="#333333", pad=14)
        ax.set_xlabel(metric_label(x_axis), color="#666666")
        ax.set_ylabel(metric_label(y_axis), color="#666666")
        ax.tick_params(axis="x", rotation=35, labelsize=9, colors="#555555")
        ax.tick_params(axis="y", labelsize=9, colors="#555555")
        ax.grid(axis="y", linestyle="--", alpha=0.45)
        ax.grid(axis="x", visible=False)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        fig.tight_layout()

        path = _unique_png_path(filename)
        fig.savefig(path)
        plt.close(fig)
        return f".scratchpad/{_rel_scratchpad(path)}"
    except Exception as e:
        plt.close("all")
        return f"Error: {e}"


def generate_metric_dashboard_chart(
    data: list[dict[str, Any]] | dict[str, Any] | str,
    title: str,
    filename: str,
    x_axis: str | None = None,
    metrics: list[str] | None = None,
) -> str:
    """多指标看板：单行→横向条图；多行→按指标折线子图。"""
    try:
        rows = _as_row_dicts(data)
        if not rows:
            return "Error: Data is empty."
        df = pd.DataFrame(rows)
        cols = list(df.columns)
        if not x_axis or x_axis not in cols:
            x_axis = cols[0] if len(df) > 1 else None

        metric_columns = metrics or [c for c in cols if c != x_axis]
        metric_columns = [c for c in metric_columns if c in cols and c != x_axis]
        if not metric_columns:
            return "Error: No valid metric columns found for dashboard chart."

        if len(df) == 1:
            fig_height = max(4.2, len(metric_columns) * 0.85 + 1.2)
            fig, axes = plt.subplots(
                len(metric_columns),
                1,
                figsize=(10.5, fig_height),
                dpi=160,
            )
            axes_list = axes.flatten().tolist() if hasattr(axes, "flatten") else [axes]
            values = (
                pd.to_numeric(df.iloc[0][metric_columns], errors="coerce")
                .fillna(0)
                .tolist()
            )
            colors = plt.cm.Blues([0.35 + 0.5 * (i / max(len(metric_columns), 1)) for i in range(len(metric_columns))])
            for axis, metric, value, color in zip(axes_list, metric_columns, values, colors):
                label = metric_label(metric)
                numeric = float(value)
                axis.barh([label], [numeric], color=color, edgecolor="white", height=0.55)
                axis.set_xlim(0, max(numeric * 1.18, 1.0))
                axis.set_title(label, fontsize=11, fontweight="bold", color="#333333", loc="left", pad=6)
                axis.grid(axis="x", linestyle="--", alpha=0.4)
                axis.grid(axis="y", visible=False)
                axis.tick_params(axis="y", length=0, labelsize=9, colors="#555555")
                axis.tick_params(axis="x", labelsize=8, colors="#555555")
                for spine in ("top", "right"):
                    axis.spines[spine].set_visible(False)
                axis.text(
                    numeric * 1.02 if numeric > 0 else 0.05,
                    0,
                    _format_chart_value(numeric),
                    va="center",
                    ha="left",
                    fontsize=10,
                    color="#333333",
                    fontweight="bold",
                )
            fig.suptitle(title, fontsize=14, fontweight="bold", color="#333333")
            fig.tight_layout(rect=[0, 0, 1, 0.97])
        else:
            chart_cols = 2 if len(metric_columns) > 1 else 1
            chart_rows = math.ceil(len(metric_columns) / chart_cols)
            fig, axes = plt.subplots(
                chart_rows,
                chart_cols,
                figsize=(chart_cols * 5.8, chart_rows * 3.4),
                dpi=160,
            )
            axes_list = axes.flatten().tolist() if hasattr(axes, "flatten") else [axes]
            x_values = df[x_axis].astype(str) if x_axis else df.index.astype(str)
            for axis, metric in zip(axes_list, metric_columns):
                y_values = pd.to_numeric(df[metric], errors="coerce").fillna(0)
                axis.plot(x_values, y_values, marker="o", linewidth=2.2, color="#3B6EA5")
                axis.set_title(metric_label(metric), fontsize=11, fontweight="bold", color="#333333")
                axis.set_xlabel(metric_label(x_axis or "index"), color="#666666", fontsize=9)
                axis.set_ylabel("数值", color="#666666", fontsize=9)
                axis.tick_params(axis="x", rotation=30, labelsize=8, colors="#555555")
                axis.tick_params(axis="y", labelsize=8, colors="#555555")
                axis.grid(axis="y", linestyle="--", alpha=0.45)
                for spine in ("top", "right"):
                    axis.spines[spine].set_visible(False)
            for axis in axes_list[len(metric_columns) :]:
                axis.set_visible(False)
            fig.suptitle(title, fontsize=14, fontweight="bold", color="#333333")
            fig.tight_layout(rect=[0, 0, 1, 0.96])

        path = _unique_png_path(filename)
        fig.savefig(path)
        plt.close(fig)
        return f".scratchpad/{_rel_scratchpad(path)}"
    except Exception as e:
        plt.close("all")
        return f"Error: {e}"
