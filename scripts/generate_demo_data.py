#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LumenLearn 合成数据生成（本仓自带，问数可独立运行）

- 仅生成 Synthetic Demo Data，无真实用户
- 默认输出 CSV 到 data/（不依赖本机已起 ClickHouse）
- 可选 --to-clickhouse，通过 HTTP 导入（需 infra/docker-compose 已就绪）

用法示例（仓库根目录）：
  python scripts/generate_demo_data.py --seed 42 --users 800 --days 90
  python scripts/generate_demo_data.py --seed 42 --to-clickhouse --truncate
  docker compose -f infra/docker-compose.yml up -d
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data"
DDL_PATH = ROOT / "infra" / "clickhouse_ddl.sql"
READONLY_SQL_PATH = ROOT / "infra" / "init_readonly.sql"

PATHS = [
    ("path_python_01", "Python 入门", "backend"),
    ("path_js_01", "JavaScript 基础", "frontend"),
    ("path_sql_01", "SQL 与数据分析", "data"),
    ("path_git_01", "Git 协作入门", "devtools"),
]

LESSONS = {
    "path_python_01": [
        ("les_py_01", "变量与类型", 1),
        ("les_py_02", "控制流", 2),
        ("les_py_03", "函数与模块", 3),
        ("les_py_04", "文件与异常", 4),
    ],
    "path_js_01": [
        ("les_js_01", "语法速览", 1),
        ("les_js_02", "DOM 基础", 2),
        ("les_js_03", "异步入门", 3),
    ],
    "path_sql_01": [
        ("les_sql_01", "SELECT 基础", 1),
        ("les_sql_02", "JOIN 与聚合", 2),
        ("les_sql_03", "窗口函数入门", 3),
    ],
    "path_git_01": [
        ("les_git_01", "仓库与提交", 1),
        ("les_git_02", "分支与合并", 2),
    ],
}

CHALLENGES = [
    ("ch_7day", "7 日学习打卡", 7),
    ("ch_21day", "21 日坚持挑战", 21),
]

CHANNELS = ["organic", "share", "campaign_demo", "search"]
APPS = [("ll_web", "js"), ("ll_mp", "MiniProgram")]
NETWORKS = ["wifi", "4g", "5g"]

EVENT_COLS = [
    "distinct_id",
    "anonymous_id",
    "identity_login_id",
    "event",
    "event_time",
    "dt",
    "app_id",
    "lib",
    "screen_name",
    "title",
    "network_type",
    "register_channel",
    "path_id",
    "path_name",
    "path_category",
    "lesson_id",
    "lesson_name",
    "lesson_index",
    "duration",
    "exercise_id",
    "is_passed",
    "challenge_id",
    "challenge_name",
    "challenge_days",
    "share_type",
]

USER_COLS = [
    "distinct_id",
    "login_id",
    "register_dt",
    "register_channel",
    "app_id",
    "last_active_dt",
]


@dataclass
class Learner:
    distinct_id: str
    login_id: str
    anonymous_id: str
    register_dt: date
    register_channel: str
    app_id: str
    lib: str
    last_active_dt: date
    # 行为偏好
    retention_d1: bool
    retention_d7: bool
    activity: float  # 0~1，越高越活跃


def _empty_event() -> dict:
    return {c: "" for c in EVENT_COLS}


def _fmt_dt64(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _weekday_boost(d: date) -> float:
    # 工作日略高，周末略低（学习社区常见形态）
    return 1.15 if d.weekday() < 5 else 0.75


def build_learners(rng: random.Random, n: int, start: date, end: date) -> list[Learner]:
    days = (end - start).days + 1
    learners: list[Learner] = []
    for i in range(n):
        offset = int(rng.triangular(0, days - 1, days * 0.55))
        reg = start + timedelta(days=min(offset, days - 1))
        app_id, lib = rng.choice(APPS)
        channel = rng.choices(CHANNELS, weights=[45, 25, 20, 10], k=1)[0]
        # 约 35% 次日留存、18% 七日留存（可演示留存分析）
        d1 = rng.random() < 0.35
        d7 = d1 and rng.random() < 0.45
        learners.append(
            Learner(
                distinct_id=f"dev_{10000 + i}",
                login_id=f"u_{10000 + i}",
                anonymous_id=f"anon_{10000 + i}",
                register_dt=reg,
                register_channel=channel,
                app_id=app_id,
                lib=lib,
                last_active_dt=reg,
                retention_d1=d1,
                retention_d7=d7,
                activity=rng.uniform(0.15, 0.95),
            )
        )
    return learners


def _base_event(
    learner: Learner,
    event: str,
    when: datetime,
    *,
    screen: str = "",
    title: str = "",
    path=None,
    lesson=None,
    duration: int = 0,
    exercise_id: str = "",
    is_passed: str = "",
    challenge=None,
    share_type: str = "",
    network: str = "wifi",
) -> dict:
    row = _empty_event()
    row.update(
        {
            "distinct_id": learner.distinct_id,
            "anonymous_id": learner.anonymous_id,
            "identity_login_id": learner.login_id,
            "event": event,
            "event_time": _fmt_dt64(when),
            "dt": when.date().isoformat(),
            "app_id": learner.app_id,
            "lib": learner.lib,
            "screen_name": screen,
            "title": title,
            "network_type": network,
            "register_channel": "",
            "duration": str(duration) if duration else "0",
            "lesson_index": "0",
            "is_passed": is_passed if is_passed != "" else "0",
            "challenge_days": "0",
        }
    )
    if event == "SignUp":
        row["register_channel"] = learner.register_channel
    if path:
        row["path_id"], row["path_name"], row["path_category"] = path
    if lesson:
        lid, lname, lidx = lesson
        row["lesson_id"] = lid
        row["lesson_name"] = lname
        row["lesson_index"] = str(lidx)
    if exercise_id:
        row["exercise_id"] = exercise_id
    if challenge:
        cid, cname, cdays = challenge
        row["challenge_id"] = cid
        row["challenge_name"] = cname
        row["challenge_days"] = str(cdays)
    if share_type:
        row["share_type"] = share_type
    return row


def simulate_user_timeline(
    rng: random.Random,
    learner: Learner,
    end: date,
) -> list[dict]:
    events: list[dict] = []
    reg = learner.register_dt

    def at(day: date, hour: int | None = None, minute: int | None = None) -> datetime:
        h = hour if hour is not None else rng.randint(8, 22)
        m = minute if minute is not None else rng.randint(0, 59)
        s = rng.randint(0, 59)
        return datetime(day.year, day.month, day.day, h, m, s)

    # 注册日
    events.append(_base_event(learner, "SignUp", at(reg, 10), screen="signup", title="注册"))
    view_event = "$MPViewScreen" if learner.app_id == "ll_mp" else "$AppViewScreen"
    events.append(
        _base_event(
            learner,
            view_event,
            at(reg, 10, 5),
            screen="home",
            title="首页",
            network=rng.choice(NETWORKS),
        )
    )
    learner.last_active_dt = reg

    # 次日 / 七日留存：屏浏览
    if learner.retention_d1:
        d1 = reg + timedelta(days=1)
        if d1 <= end:
            events.append(
                _base_event(learner, view_event, at(d1), screen="home", title="首页")
            )
            learner.last_active_dt = max(learner.last_active_dt, d1)
    if learner.retention_d7:
        d7 = reg + timedelta(days=7)
        if d7 <= end:
            events.append(
                _base_event(learner, view_event, at(d7), screen="home", title="首页")
            )
            learner.last_active_dt = max(learner.last_active_dt, d7)

    # 学习漏斗（带掉点）
    path = rng.choice(PATHS)
    path_id = path[0]
    lessons = LESSONS[path_id]

    if rng.random() < 0.72 * learner.activity:
        t0 = at(reg, 11)
        events.append(
            _base_event(
                learner,
                "ViewLearningPath",
                t0,
                screen="path_detail",
                title=path[1],
                path=path,
            )
        )
        # StartLesson
        if rng.random() < 0.78:
            lesson = rng.choice(lessons)
            t1 = t0 + timedelta(minutes=rng.randint(3, 40))
            events.append(
                _base_event(
                    learner,
                    "StartLesson",
                    t1,
                    screen="lesson_player",
                    title=lesson[1],
                    path=path,
                    lesson=lesson,
                )
            )
            # CompleteLesson
            if rng.random() < 0.62:
                dur = rng.randint(180, 1200)
                t2 = t1 + timedelta(seconds=dur)
                events.append(
                    _base_event(
                        learner,
                        "CompleteLesson",
                        t2,
                        screen="lesson_player",
                        title=lesson[1],
                        path=path,
                        lesson=lesson,
                        duration=dur,
                    )
                )
                # SubmitExercise
                if rng.random() < 0.55:
                    t3 = t2 + timedelta(minutes=rng.randint(2, 25))
                    passed = "1" if rng.random() < 0.7 else "0"
                    events.append(
                        _base_event(
                            learner,
                            "SubmitExercise",
                            t3,
                            screen="exercise",
                            title="练习",
                            path=path,
                            lesson=lesson,
                            duration=rng.randint(60, 600),
                            exercise_id=f"ex_{lesson[0]}",
                            is_passed=passed,
                        )
                    )

    # 后续活跃天：随机屏浏览 + 偶尔挑战/分享
    cursor = reg + timedelta(days=1)
    while cursor <= end:
        boost = _weekday_boost(cursor)
        p = learner.activity * 0.22 * boost
        if rng.random() < p:
            events.append(
                _base_event(
                    learner,
                    view_event,
                    at(cursor),
                    screen=rng.choice(["home", "path_detail", "lesson_player"]),
                    title="浏览",
                    network=rng.choice(NETWORKS),
                )
            )
            learner.last_active_dt = max(learner.last_active_dt, cursor)
            if rng.random() < 0.08:
                ch = rng.choice(CHALLENGES)
                events.append(
                    _base_event(
                        learner,
                        "JoinChallenge",
                        at(cursor, 20),
                        screen="challenge",
                        title=ch[1],
                        challenge=ch,
                    )
                )
            if rng.random() < 0.06:
                events.append(
                    _base_event(
                        learner,
                        "ShareProgress",
                        at(cursor, 21),
                        screen="share",
                        title="分享",
                        path=path,
                        share_type=rng.choice(["path", "lesson", "challenge", "streak"]),
                    )
                )
        cursor += timedelta(days=1)

    return events


def write_csv(path: Path, cols: list[str], rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
            n += 1
    return n


def ch_query(
    base_url: str,
    user: str,
    password: str,
    sql: str,
    data: bytes | None = None,
    timeout: int = 120,
) -> str:
    q = urllib.parse.urlencode({"database": "lumenlearn", "query": sql})
    url = f"{base_url.rstrip('/')}/?{q}"
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    if user:
        import base64

        auth = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {auth}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise RuntimeError(f"ClickHouse 请求失败: {e}") from e


def _split_sql_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    stmts: list[str] = []
    buf: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        buf.append(line)
        if ";" in line:
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            buf = []
            if stmt:
                stmts.append(stmt)
    return stmts


def _exec_admin_sql(base_url: str, user: str, password: str, stmt: str) -> None:
    import base64

    q = urllib.parse.urlencode({"query": stmt})
    url = f"{base_url.rstrip('/')}/?{q}"
    req = urllib.request.Request(url, method="POST")
    auth = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


def apply_ddl(base_url: str, user: str, password: str) -> None:
    if not DDL_PATH.exists():
        raise FileNotFoundError(f"找不到 DDL: {DDL_PATH}")
    for stmt in _split_sql_file(DDL_PATH):
        _exec_admin_sql(base_url, user, password, stmt)


def ensure_readonly_user(base_url: str, user: str, password: str) -> None:
    """创建 Agent 专用只读账号 lumen_ro（SETTINGS readonly=1 + GRANT SELECT）。"""
    if not READONLY_SQL_PATH.exists():
        print(f"[CH] 跳过只读账号：找不到 {READONLY_SQL_PATH}")
        return
    for stmt in _split_sql_file(READONLY_SQL_PATH):
        try:
            _exec_admin_sql(base_url, user, password, stmt)
            print(f"[CH] 只读账号 SQL OK: {stmt.split()[0:4]}")
        except Exception as e:
            # 已存在 / 无权限时不阻断灌数；Agent 仍有工具层 + settings.readonly=1
            print(f"[CH] 只读账号步骤跳过: {e}")


def import_csv_http(
    base_url: str,
    user: str,
    password: str,
    table: str,
    csv_path: Path,
) -> None:
    # 跳过表头
    raw = csv_path.read_bytes()
    # 去掉第一行 header
    nl = raw.find(b"\n")
    body = raw[nl + 1 :] if nl >= 0 else raw
    sql = f"INSERT INTO lumenlearn.{table} FORMAT CSV"
    ch_query(base_url, user, password, sql, data=body)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="生成 LumenLearn ClickHouse 合成数据")
    p.add_argument("--seed", type=int, default=42, help="随机种子（可复现）")
    p.add_argument("--users", type=int, default=800, help="合成用户数")
    p.add_argument("--days", type=int, default=90, help="回溯天数")
    p.add_argument(
        "--end-date",
        type=str,
        default="2026-08-01",
        help="数据结束日 YYYY-MM-DD（固定便于复现）",
    )
    p.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT), help="CSV 输出目录")
    p.add_argument(
        "--to-clickhouse",
        action="store_true",
        help="生成后通过 HTTP 导入 ClickHouse",
    )
    p.add_argument("--ch-url", type=str, default="http://127.0.0.1:8123")
    p.add_argument("--ch-user", type=str, default="lumen")
    p.add_argument("--ch-password", type=str, default="lumen_demo")
    p.add_argument(
        "--truncate",
        action="store_true",
        help="导入前 TRUNCATE events/users（需 --to-clickhouse）",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rng = random.Random(args.seed)
    end = date.fromisoformat(args.end_date)
    start = end - timedelta(days=args.days - 1)
    out_dir = Path(args.out_dir)

    print(f"[LumenLearn] seed={args.seed} users={args.users} range={start}~{end}")
    learners = build_learners(rng, args.users, start, end)

    all_events: list[dict] = []
    for u in learners:
        all_events.extend(simulate_user_timeline(rng, u, end))

    # 按时间排序，便于预览
    all_events.sort(key=lambda r: (r["event_time"], r["distinct_id"], r["event"]))

    user_rows = [
        {
            "distinct_id": u.distinct_id,
            "login_id": u.login_id,
            "register_dt": u.register_dt.isoformat(),
            "register_channel": u.register_channel,
            "app_id": u.app_id,
            "last_active_dt": u.last_active_dt.isoformat(),
        }
        for u in learners
    ]

    events_csv = out_dir / "events.csv"
    users_csv = out_dir / "users.csv"
    n_e = write_csv(events_csv, EVENT_COLS, all_events)
    n_u = write_csv(users_csv, USER_COLS, user_rows)
    meta = out_dir / "GENERATION_META.txt"
    meta.write_text(
        "\n".join(
            [
                "LumenLearn Synthetic Demo Data",
                f"seed={args.seed}",
                f"users={n_u}",
                f"events={n_e}",
                f"start={start.isoformat()}",
                f"end={end.isoformat()}",
                "policy=synthetic_demo_only_no_pii",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[OK] 写出 {users_csv} ({n_u} 行)")
    print(f"[OK] 写出 {events_csv} ({n_e} 行)")
    print(f"[OK] 写出 {meta}")

    if args.to_clickhouse:
        print(f"[CH] 连接 {args.ch_url} …")
        try:
            apply_ddl(args.ch_url, args.ch_user, args.ch_password)
            ensure_readonly_user(args.ch_url, args.ch_user, args.ch_password)
            if args.truncate:
                _exec_admin_sql(
                    args.ch_url,
                    args.ch_user,
                    args.ch_password,
                    "TRUNCATE TABLE IF EXISTS lumenlearn.events",
                )
                _exec_admin_sql(
                    args.ch_url,
                    args.ch_user,
                    args.ch_password,
                    "TRUNCATE TABLE IF EXISTS lumenlearn.users",
                )
            import_csv_http(
                args.ch_url, args.ch_user, args.ch_password, "users", users_csv
            )
            import_csv_http(
                args.ch_url, args.ch_user, args.ch_password, "events", events_csv
            )
            cnt_u = ch_query(
                args.ch_url,
                args.ch_user,
                args.ch_password,
                "SELECT count() FROM lumenlearn.users",
            ).strip()
            cnt_e = ch_query(
                args.ch_url,
                args.ch_user,
                args.ch_password,
                "SELECT count() FROM lumenlearn.events",
            ).strip()
            print(f"[CH] 导入完成 users={cnt_u} events={cnt_e}")
        except Exception as e:
            print(f"[CH] 导入失败（CSV 已生成，可稍后重试）: {e}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
