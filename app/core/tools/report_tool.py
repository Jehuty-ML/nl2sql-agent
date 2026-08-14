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


def rows_to_markdown_table(columns: list[str], rows: list[dict[str, Any]]) -> str:
    if not columns:
        return "_空结果_"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, sep]
    for r in rows[:50]:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in columns) + " |")
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
