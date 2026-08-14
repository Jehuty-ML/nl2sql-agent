"""只读 SQL 防护单测。"""

from __future__ import annotations

from app.core.tools.sql_guard import guard_readonly_sql


def test_allow_select():
    r = guard_readonly_sql("SELECT 1")
    assert r["ok"] is True
    assert "LIMIT" in r["sql"].upper()


def test_allow_with_cte():
    sql = "WITH a AS (SELECT 1 AS x) SELECT x FROM a LIMIT 10"
    r = guard_readonly_sql(sql)
    assert r["ok"] is True


def test_reject_insert():
    r = guard_readonly_sql("INSERT INTO events VALUES (1)")
    assert r["ok"] is False
    assert "只读" in r["error"] or "SELECT" in r["error"]


def test_reject_drop_in_select_prefix_bypass():
    # 不以 SELECT 开头
    r = guard_readonly_sql("DROP TABLE events")
    assert r["ok"] is False


def test_reject_forbidden_keyword_inside():
    r = guard_readonly_sql("SELECT 1; DROP TABLE events")
    assert r["ok"] is False


def test_reject_update_keyword():
    r = guard_readonly_sql("SELECT * FROM events WHERE 1=1 UPDATE")
    # UPDATE as bare keyword should be caught; if it's identifier-like may differ
    # Our SQL is invalid but still has UPDATE token
    assert r["ok"] is False


def test_reject_multi_statement():
    r = guard_readonly_sql("SELECT 1; SELECT 2")
    assert r["ok"] is False
    assert "多条" in r["error"]
