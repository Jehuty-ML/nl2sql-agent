"""sql_classifier 单测。"""

from app.core.tools.sql_classifier import classify_sql


def test_aggregate_group_by():
    sql = "SELECT register_channel, count() AS c FROM events GROUP BY register_channel"
    assert classify_sql(sql) == "aggregate"


def test_detail_distinct_id():
    sql = "SELECT distinct_id, event FROM events LIMIT 100"
    assert classify_sql(sql) == "detail"
