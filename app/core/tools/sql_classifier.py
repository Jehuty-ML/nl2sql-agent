"""SQL 形态分类：fixed / aggregate / detail。"""

from __future__ import annotations

import re

from app.core.tools.result_shape import GRAIN_AGGREGATE, GRAIN_DETAIL

_AGG_FUNCS = re.compile(
    r"(?i)\b(count|uniq|uniqexact|sum|avg|min|max|any|anylast|quantile)\s*\("
)
_GROUP_BY = re.compile(r"(?i)\bgroup\s+by\b")
_DETAIL_COLS = re.compile(
    r"(?i)\b(distinct_id|identity_login_id|user_id|login_id)\b"
)
_SELECT_STAR = re.compile(r"(?i)select\s+\*")


def classify_sql(sql: str) -> str:
    """启发式分类 SQL 粒度。"""
    raw = (sql or "").strip()
    if not raw:
        return GRAIN_DETAIL

    has_agg = bool(_AGG_FUNCS.search(raw))
    has_group = bool(_GROUP_BY.search(raw))
    has_detail_col = bool(_DETAIL_COLS.search(raw))
    select_star = bool(_SELECT_STAR.search(raw))

    if has_group or (has_agg and not has_detail_col):
        return GRAIN_AGGREGATE
    if select_star or (has_detail_col and not has_agg):
        return GRAIN_DETAIL
    if has_agg:
        return GRAIN_AGGREGATE
    return GRAIN_DETAIL


def detail_reject_hint() -> str:
    return (
        "当前 SQL 为明细查询，无法直接回答汇总类问题。"
        "请改用 get_fixed_analysis(key=...) 或 "
        "SELECT 维度列, count()/uniqExact(...) ... GROUP BY 维度列。"
    )
