"""报表导出（Markdown / 简易表）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = ROOT / ".scratchpad" / "reports"


def ensure_report_dir() -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR


def export_markdown(title: str, content: str, filename: str = "") -> str:
    ensure_report_dir()
    name = filename or f"report_{title}.md"
    name = name.replace("/", "_").replace("\\", "_")
    if not name.endswith(".md"):
        name += ".md"
    path = REPORT_DIR / name
    path.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
    return json.dumps(
        {"ok": True, "path": str(path.relative_to(ROOT)), "abs_path": str(path)},
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
    header = "| " + " | ".join(cols) + " |"
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
    return export_markdown(title, "\n".join(body), filename=f"{title}.md")
