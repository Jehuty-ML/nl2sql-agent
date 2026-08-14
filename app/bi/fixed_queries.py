"""ClickHouse 固定分析 SQL（仅 CK / LumenLearn）。"""

from __future__ import annotations

from typing import Any


def _screen_filter() -> str:
    return "event IN ('$AppViewScreen', '$MPViewScreen')"


FIXED_QUERIES: dict[str, dict[str, Any]] = {
    "overview": {
        "name": "学习概览",
        "keywords": ["概览", "总览", "overview", "今天怎么样", "整体"],
        "description": "区间内新增、DAU、完课与练习核心指标",
        "sql": f"""
SELECT
  new_learners,
  dau,
  start_lesson_cnt,
  complete_lesson_cnt,
  if(start_lesson_cnt = 0, 0, complete_lesson_cnt / start_lesson_cnt) AS completion_rate,
  exercise_users
FROM
(
  SELECT
    (SELECT countDistinct(distinct_id) FROM events
     WHERE event = 'SignUp' AND dt BETWEEN {{start_date}} AND {{end_date}}) AS new_learners,
    (SELECT countDistinct(identity_login_id) FROM events
     WHERE {_screen_filter()}
       AND identity_login_id != ''
       AND dt BETWEEN {{start_date}} AND {{end_date}}) AS dau,
    (SELECT count() FROM events
     WHERE event = 'StartLesson' AND dt BETWEEN {{start_date}} AND {{end_date}}) AS start_lesson_cnt,
    (SELECT count() FROM events
     WHERE event = 'CompleteLesson' AND dt BETWEEN {{start_date}} AND {{end_date}}) AS complete_lesson_cnt,
    (SELECT countDistinct(distinct_id) FROM events
     WHERE event = 'SubmitExercise' AND dt BETWEEN {{start_date}} AND {{end_date}}) AS exercise_users
)
""".strip(),
    },
    "dau": {
        "name": "日活 DAU",
        "keywords": ["日活", "dau", "活跃"],
        "description": "按日 DAU（登录账号级）",
        "sql": f"""
SELECT
  dt,
  countDistinct(identity_login_id) AS dau
FROM events
WHERE {_screen_filter()}
  AND identity_login_id != ''
  AND dt BETWEEN {{start_date}} AND {{end_date}}
GROUP BY dt
ORDER BY dt
""".strip(),
    },
    "retention": {
        "name": "注册留存",
        "keywords": ["留存", "次日", "七日", "retention", "cohort"],
        "description": "SignUp cohort 的 D1/D7 留存率（设备级 distinct_id）",
        # 先按用户打 retained_d1/d7 标记再汇总，避免多表 JOIN 放大行数
        "sql": f"""
WITH registrations AS (
  SELECT
    distinct_id,
    min(dt) AS reg_date
  FROM events
  WHERE event = 'SignUp'
    AND distinct_id != ''
    AND dt BETWEEN {{start_date}} AND {{end_date}}
  GROUP BY distinct_id
),
active_days AS (
  SELECT DISTINCT
    distinct_id,
    dt AS active_date
  FROM events
  WHERE {_screen_filter()}
    AND distinct_id != ''
    AND dt >= {{start_date}}
    AND dt <= addDays({{end_date}}, 7)
),
user_flags AS (
  SELECT
    r.distinct_id,
    r.reg_date,
    max(if(a.active_date = addDays(r.reg_date, 1), toUInt8(1), toUInt8(0))) AS retained_d1,
    max(if(a.active_date = addDays(r.reg_date, 7), toUInt8(1), toUInt8(0))) AS retained_d7
  FROM registrations r
  LEFT JOIN active_days a ON r.distinct_id = a.distinct_id
  GROUP BY r.distinct_id, r.reg_date
)
SELECT
  count() AS cohort_size,
  sum(retained_d1) AS d1_retained,
  sum(retained_d7) AS d7_retained,
  if(cohort_size = 0, 0, d1_retained / cohort_size) AS d1_rate,
  if(cohort_size = 0, 0, d7_retained / cohort_size) AS d7_rate
FROM user_flags
""".strip(),
    },
    "funnel": {
        "name": "学习漏斗",
        "keywords": ["漏斗", "转化", "完课", "练习转化", "funnel"],
        "description": "浏览路径→开课→完课→交练习 UV 漏斗",
        "sql": """
SELECT
  countDistinctIf(distinct_id, event = 'ViewLearningPath') AS view_path_uv,
  countDistinctIf(distinct_id, event = 'StartLesson') AS start_lesson_uv,
  countDistinctIf(distinct_id, event = 'CompleteLesson') AS complete_lesson_uv,
  countDistinctIf(distinct_id, event = 'SubmitExercise') AS submit_exercise_uv
FROM events
WHERE dt BETWEEN {start_date} AND {end_date}
""".strip(),
    },
    "channel_completion": {
        "name": "渠道完课对比",
        "keywords": ["渠道", "channel", "注册来源"],
        "description": "按 users.register_channel 看完课 UV",
        "sql": """
SELECT
  u.register_channel,
  countDistinctIf(e.distinct_id, e.event = 'CompleteLesson') AS complete_uv,
  countDistinct(u.distinct_id) AS user_cnt
FROM users u
LEFT JOIN events e
  ON u.distinct_id = e.distinct_id
 AND e.dt BETWEEN {start_date} AND {end_date}
GROUP BY u.register_channel
ORDER BY complete_uv DESC
""".strip(),
    },
}


def render_sql(sql_template: str, start_date: str, end_date: str) -> str:
    """填充日期占位（ClickHouse Date 字面量）。"""
    return (
        sql_template.replace("{start_date}", f"toDate('{start_date}')")
        .replace("{end_date}", f"toDate('{end_date}')")
    )


def match_fixed_query(user_query: str) -> str | None:
    """仅供测试/调试查看关键词表；**禁止**用于请求路由（自然语言不靠关键词抢跑）。"""
    q = user_query.lower()
    scored: list[tuple[int, str]] = []
    for key, meta in FIXED_QUERIES.items():
        for kw in meta.get("keywords") or []:
            if kw.lower() in q:
                scored.append((len(kw), key))
                break
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][1]
