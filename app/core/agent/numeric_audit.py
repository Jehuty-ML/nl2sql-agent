"""交卷后软数字对账（仅 warn，不改 answer）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

QUERY_TOOLS = frozenset({"get_fixed_analysis", "db_query"})

NOTICE_NUMERIC = (
    "【系统提示】结论中部分具体数字未在查数结果中出现，请对照 Run Log / 上表核对；"
    "勿仅依据模型叙述做决策。"
)

_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_NUM = re.compile(r"(?<!\d)([\d]{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\d)")
_APPROX = re.compile(r"(约|大约|左右|接近)\s*")
_DATE = re.compile(r"\b20\d{2}[-/年]\d{1,2}([-/月]\d{1,2})?\b")
_RATE_COL = re.compile(r"(?i)(rate|ratio|pct|率|占比)")


@dataclass
class NumericClaim:
    text: str
    value: float
    approximate: bool


@dataclass
class AuditReport:
    flagged: list[NumericClaim]
    checked_count: int


def _parse_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _expand_equivalents(x: float, *, rate_context: bool) -> set[str]:
    out: set[str] = set()
    if abs(x - round(x)) < 1e-9:
        out.add(str(int(round(x))))
    out.add(f"{x:.6f}".rstrip("0").rstrip("."))
    out.add(f"{x:.2f}")
    if 0 < x <= 1:
        pct = x * 100
        out.add(f"{pct:.2f}".rstrip("0").rstrip("."))
        out.add(f"{int(round(pct))}")
    if rate_context and 1 < x <= 100:
        out.add(f"{x / 100:.4f}".rstrip("0").rstrip("."))
    return out


def _iter_cell_values(trace: dict[str, Any]) -> list[tuple[Any, str]]:
    table = trace.get("table") or {}
    rows = table.get("rows") or []
    cols = table.get("columns") or []
    out: list[tuple[Any, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for k, v in row.items():
            col = str(k)
            out.append((v, col))
        for c in cols:
            if c not in row:
                out.append((None, str(c)))
    return out


def build_evidence_numbers(traces: list[dict[str, Any]]) -> tuple[set[str], bool]:
    canonical: set[str] = set()
    has_rate = False
    for t in traces:
        if str(t.get("tool") or "") not in QUERY_TOOLS or not t.get("ok"):
            continue
        for v, col in _iter_cell_values(t):
            if _RATE_COL.search(col):
                has_rate = True
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                canonical |= _expand_equivalents(float(v), rate_context=has_rate)
            elif isinstance(v, str):
                f = _parse_float(v.rstrip("%"))
                if f is not None:
                    canonical |= _expand_equivalents(f, rate_context=has_rate)
    return canonical, has_rate


def prose_for_audit(answer: str) -> str:
    parts = re.split(r"(?m)^###\s*支撑数据", answer, maxsplit=1)
    text = parts[0]
    # 去掉 markdown 表格行
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("|")]
    return "\n".join(lines)


def extract_numeric_claims(answer: str) -> list[NumericClaim]:
    text = prose_for_audit(answer)
    claims: list[NumericClaim] = []
    seen: set[tuple[str, float]] = set()

    for m in _PCT.finditer(text):
        start = max(0, m.start() - 8)
        prefix = text[start : m.start()]
        approx = bool(_APPROX.search(prefix))
        val = _parse_float(m.group(1))
        if val is None:
            continue
        key = ("pct", val)
        if key in seen:
            continue
        seen.add(key)
        claims.append(NumericClaim(text=m.group(0), value=val, approximate=approx))

    for m in _NUM.finditer(text):
        raw = m.group(1)
        if _DATE.search(m.group(0)):
            continue
        start = max(0, m.start() - 8)
        prefix = text[start : m.start()]
        if _APPROX.search(prefix):
            continue
        val = _parse_float(raw)
        if val is None:
            continue
        if val < 10:
            continue
        key = ("num", val)
        if key in seen:
            continue
        seen.add(key)
        claims.append(NumericClaim(text=raw, value=val, approximate=False))

    return claims


def claim_matches(claim: NumericClaim, canonical: set[str], *, has_rate: bool) -> bool:
    if claim.approximate:
        return True
    forms = _expand_equivalents(claim.value, rate_context=has_rate)
    return bool(forms & canonical)


def audit_answer(answer: str, traces: list[dict[str, Any]]) -> AuditReport:
    canonical, has_rate = build_evidence_numbers(traces)
    claims = extract_numeric_claims(answer)
    flagged = [c for c in claims if not claim_matches(c, canonical, has_rate=has_rate)]
    return AuditReport(flagged=flagged, checked_count=len(claims))


def apply_numeric_audit(result: dict[str, Any]) -> dict[str, Any]:
    from app.config import settings

    if not settings.enable_numeric_audit:
        return result
    if result.get("mode") != "agent_loop":
        return result
    assessment = result.get("delivery_assessment") or {}
    if assessment.get("reason") != "none":
        return result
    if not assessment.get("has_complete_evidence"):
        return result

    report = audit_answer(str(result.get("answer") or ""), result.get("tool_traces") or [])
    result["numeric_audit"] = {
        "flagged": [{"text": c.text, "value": c.value} for c in report.flagged],
        "checked_claims": report.checked_count,
    }
    if not report.flagged:
        return result

    notice = NOTICE_NUMERIC
    existing = str(result.get("delivery_notice") or "")
    if notice not in existing:
        result["delivery_notice"] = f"{existing}\n{notice}".strip() if existing else notice
    answer = str(result.get("answer") or "")
    if notice not in answer:
        result["answer"] = f"{notice}\n\n{answer}".strip() if answer else notice
    return result
