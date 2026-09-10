"""Demo 数据日历诚实门闩（不以措辞白名单为主）。

主规则（抗漏配）：
  真实「今天」已超过 Demo 数据结束日，且本轮确有查数结果，
  同时用户未在问题里写死「落在 Demo 窗内的绝对日期」→
  标 partial，并说明库内可用区间。

相对时间短语解析仅用于把提示写得更具体（可选增强），不是触发条件。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

# 与 scripts/generate_demo_data.py / fixed_analysis 对齐
DEMO_DATA_START = date(2026, 5, 4)
DEMO_DATA_END = date(2026, 8, 1)

_ISO = re.compile(r"20\d{2}-\d{1,2}-\d{1,2}")
_CN_YMD = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?")
_CN_YM = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月")

# 仅用于提示文案细化，不作为是否开门闩的依据
_WEEK = re.compile(
    r"(最近一周|近一周|过去一周|最近１周|最近1周|最近七天|最近7天|近7天|近七日|上周)"
)
_MONTH = re.compile(r"(最近一个月|近一个月|最近３０天|最近30天|近30天|上个月)")
_TODAY = re.compile(r"(今天|今日)")
_THIS_WEEK = re.compile(r"(本周|这周)")
_THIS_MONTH = re.compile(r"(本月|这个月)")
_N_DAYS = re.compile(r"最近\s*(\d+)\s*天")
_RECENT_VAGUE = re.compile(r"(最近的|近期的|近来的|近期|近来|最近)")

_QUERY_TOOLS = frozenset({"get_fixed_analysis", "db_query"})


def demo_available_range() -> tuple[date, date]:
    return DEMO_DATA_START, DEMO_DATA_END


def format_demo_range() -> str:
    return f"{DEMO_DATA_START.isoformat()} ~ {DEMO_DATA_END.isoformat()}"


def _parse_date_parts(y: int, m: int, d: int | None = None) -> date | None:
    try:
        if d is None:
            return date(y, m, 1)
        return date(y, m, d)
    except ValueError:
        return None


def extract_absolute_dates(query: str) -> list[date]:
    """从用户问题抽出绝对日期（ISO / 中文年月日）。"""
    q = query or ""
    found: list[date] = []
    for m in _ISO.finditer(q):
        raw = m.group(0)
        try:
            y, mo, d = raw.split("-")
            dt = _parse_date_parts(int(y), int(mo), int(d))
            if dt:
                found.append(dt)
        except ValueError:
            continue
    for m in _CN_YMD.finditer(q):
        dt = _parse_date_parts(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if dt:
            found.append(dt)
    for m in _CN_YM.finditer(q):
        # 避免与已匹配的 YMD 重复：仅作月份锚点
        dt = _parse_date_parts(int(m.group(1)), int(m.group(2)), 1)
        if dt:
            found.append(dt)
    # 去重保序
    out: list[date] = []
    seen: set[date] = set()
    for d in found:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def user_pins_demo_window(query: str) -> bool:
    """用户是否明确点名 Demo 窗内的绝对日期/月份（视为有意查 Demo）。"""
    dates = extract_absolute_dates(query)
    if not dates:
        return False
    for d in dates:
        if DEMO_DATA_START <= d <= DEMO_DATA_END:
            return True
        # 仅写到「月」：该月与 Demo 窗有交集也算 pin
        month_end = (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(
            days=1
        )
        if d.day == 1 and ranges_overlap(
            d, month_end, DEMO_DATA_START, DEMO_DATA_END
        ):
            return True
    return False


def has_successful_query(tool_traces: list[dict[str, Any]] | None) -> bool:
    for entry in tool_traces or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("tool") or "") not in _QUERY_TOOLS:
            continue
        if entry.get("ok") is True:
            return True
    return False


def resolve_relative_calendar_intent(
    query: str,
    *,
    today: date | None = None,
) -> dict[str, Any] | None:
    """可选：解析相对时间短语，仅用于提示文案。"""
    q = (query or "").strip()
    if not q:
        return None
    today = today or date.today()

    m = _N_DAYS.search(q)
    if m:
        n = max(1, int(m.group(1)))
        end = today
        start = today - timedelta(days=n - 1)
        return {
            "label": f"最近{n}天",
            "start": start,
            "end": end,
            "kind": "last_n_days",
            "n": n,
        }

    if _WEEK.search(q):
        end = today
        start = today - timedelta(days=6)
        return {"label": "最近一周", "start": start, "end": end, "kind": "last_week"}

    if _MONTH.search(q):
        end = today
        start = today - timedelta(days=29)
        return {"label": "最近一个月", "start": start, "end": end, "kind": "last_month"}

    if _TODAY.search(q):
        return {"label": "今天", "start": today, "end": today, "kind": "today"}

    if _THIS_WEEK.search(q):
        start = today - timedelta(days=today.weekday())
        return {"label": "本周", "start": start, "end": today, "kind": "this_week"}

    if _THIS_MONTH.search(q):
        start = today.replace(day=1)
        return {"label": "本月", "start": start, "end": today, "kind": "this_month"}

    if _RECENT_VAGUE.search(q):
        end = today
        start = today - timedelta(days=6)
        return {"label": "最近", "start": start, "end": end, "kind": "recent_vague"}

    return None


def range_fully_inside_demo(start: date, end: date) -> bool:
    return start >= DEMO_DATA_START and end <= DEMO_DATA_END


def ranges_overlap(a0: date, a1: date, b0: date, b1: date) -> bool:
    return a0 <= b1 and b0 <= a1


def assess_calendar_demo_gate(
    query: str,
    *,
    tool_traces: list[dict[str, Any]] | None = None,
    today: date | None = None,
) -> dict[str, Any] | None:
    """主门闩：今天超出 Demo 结束日 + 有查数 + 用户未 pin Demo 内绝对日期。"""
    today = today or date.today()
    avail = format_demo_range()
    q = (query or "").strip()

    if not q:
        return {
            "triggered": False,
            "out_of_range": False,
            "reason": "empty_query",
        }

    if today <= DEMO_DATA_END:
        return {
            "triggered": False,
            "out_of_range": False,
            "reason": "today_inside_or_on_demo_end",
        }

    if not has_successful_query(tool_traces):
        return {
            "triggered": False,
            "out_of_range": False,
            "reason": "no_successful_query",
        }

    if user_pins_demo_window(q):
        return {
            "triggered": False,
            "out_of_range": False,
            "reason": "user_pinned_demo_dates",
        }

    month_hint = f"{today.year}年{today.month}月"
    intent = resolve_relative_calendar_intent(q, today=today)
    if intent and not range_fully_inside_demo(intent["start"], intent["end"]):
        label = str(intent["label"])
        req = f"{intent['start'].isoformat()} ~ {intent['end'].isoformat()}"
        notice = (
            f"【系统提示】库内无 {month_hint}（及真实日历「{label}」）数据；"
            f"按真实日历「{label}」应对齐 {req}，无法按真实日历完整回答。"
            f"库内可用业务日：{avail}。"
            f"本次结果仅来自 Demo 窗，请勿当作真实近况；"
            f"若要查 Demo 窗请写明日期（如 2026-07），或用 /dau 等 slash。"
        )
        requested = req
        intent_label = label
    else:
        notice = (
            f"【系统提示】今日为 {today.isoformat()}，已超过 Demo 数据结束日 "
            f"{DEMO_DATA_END.isoformat()}；库内无 {month_hint} 数据。"
            f"库内可用业务日：{avail}。"
            f"本次查数结果仅覆盖 Demo 窗，不能代表真实日历下的「最近」或当前业务近况；"
            f"若有意查看 Demo，请在问题中写明 Demo 窗内日期（如 2026-07-01~2026-08-01），"
            f"或使用 /dau 等 slash（相对 Demo 结束日）。"
        )
        requested = None
        intent_label = None

    return {
        "triggered": True,
        "out_of_range": True,
        "intent": intent,
        "requested_range": requested,
        "available_range": avail,
        "notice": notice,
        "reason": "calendar_out_of_demo",
        "intent_label": intent_label,
        "today": today.isoformat(),
    }


def assess_relative_vs_demo(
    query: str,
    *,
    today: date | None = None,
    tool_traces: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """兼容旧名：默认按主门闩评估；无 traces 时不假设已查数。"""
    return assess_calendar_demo_gate(query, tool_traces=tool_traces, today=today)


def build_calendar_notice(
    query: str,
    *,
    today: date | None = None,
    tool_traces: list[dict[str, Any]] | None = None,
) -> str | None:
    info = assess_calendar_demo_gate(query, tool_traces=tool_traces, today=today)
    if info and info.get("out_of_range"):
        return str(info["notice"])
    return None
