#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基础交付冒烟：slash 固定分析必须全部可跑通。"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:6010"


def get(path: str, timeout: float = 10):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.status, r.read()


def chat_sync(query: str, timeout: float = 60) -> dict:
    data = json.dumps({"query": query, "sync": True}).encode()
    req = urllib.request.Request(
        BASE + "/api/v1/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def chat_async_wait(query: str, timeout: float = 30) -> dict:
    data = json.dumps({"query": query, "sync": False}).encode()
    req = urllib.request.Request(
        BASE + "/api/v1/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        accepted = json.load(r)
    tid = accepted["task_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        with urllib.request.urlopen(f"{BASE}/api/v1/task/{tid}", timeout=10) as r:
            task = json.load(r)
        if task.get("status") in {"succeeded", "failed"}:
            return task
        time.sleep(0.2)
    raise TimeoutError(f"async task timeout: {tid}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    failed = 0

    try:
        st, body = get("/health")
        health = json.loads(body)
        print("health", st, health.get("clickhouse"), "llm=", health.get("llm_enabled"))
        if health.get("clickhouse") != "up":
            print("FAIL clickhouse down")
            return 1
    except Exception as e:
        print("FAIL health", e)
        return 1

    try:
        st, body = get("/")
        html = body.decode("utf-8", "replace")
        ok = "/assets/" in html
        print(("OK" if ok else "FAIL"), "index assets")
        if not ok:
            failed += 1
    except Exception as e:
        print("FAIL index", e)
        failed += 1

    for q in ["/dau", "/funnel", "/retention", "/overview", "/channel", "/help"]:
        try:
            r = chat_sync(q)
            res = r.get("result") or {}
            mode = res.get("mode")
            if q == "/help":
                ok = mode == "slash_help"
            else:
                data = res.get("data") or {}
                ok = (
                    mode == "fixed_slash"
                    and bool(data.get("analysis_key"))
                    and isinstance(data.get("rows"), list)
                )
            print(
                ("OK" if ok else "FAIL"),
                "sync",
                q,
                mode,
                "rows=",
                len((res.get("data") or {}).get("rows") or []),
            )
            if not ok:
                print(" ", (res.get("answer") or "")[:300])
                failed += 1
        except Exception as e:
            print("FAIL sync", q, e)
            failed += 1

    for q in ["/dau", "/channel"]:
        try:
            task = chat_async_wait(q)
            fr = task.get("final_result") or {}
            ok = task.get("status") == "succeeded" and fr.get("mode") == "fixed_slash"
            print(("OK" if ok else "FAIL"), "async", q, task.get("status"), fr.get("mode"))
            if not ok:
                failed += 1
        except Exception as e:
            print("FAIL async", q, e)
            failed += 1

    from app.core.tools.clickhouse_tool import run_query
    from app.core.tools.fixed_analysis import run_fixed_analysis

    bad = run_query("SELECT channel FROM users LIMIT 1")
    ok = bad.get("ok") is False and "register_channel" in (bad.get("hint") or "")
    print(("OK" if ok else "FAIL"), "sql_error_hint")
    if not ok:
        failed += 1

    for key in ("dau", "funnel", "retention", "overview", "channel_completion"):
        out = run_fixed_analysis(key)
        ok = bool(out.get("ok")) and isinstance(out.get("rows"), list)
        print(("OK" if ok else "FAIL"), "tool", key, "rows=", out.get("row_count"))
        if not ok:
            print(" ", out.get("error"))
            failed += 1

    print("---")
    print("FAILED" if failed else "ALL_PASS", "count=", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
