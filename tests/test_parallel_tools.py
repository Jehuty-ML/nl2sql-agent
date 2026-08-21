"""PTC（Parallel Tool Calls）调度单测。"""

from __future__ import annotations

import json
import threading
import time

from app.core.agent.parallel_tools import (
    PendingToolCall,
    is_concurrency_safe,
    parse_tool_calls,
    partition_execution_groups,
    run_tool_groups,
)


def _call(i: int, name: str, args: dict | None = None) -> PendingToolCall:
    return PendingToolCall(
        index=i,
        call_id=f"id_{i}",
        name=name,
        args=args or {},
        raw_call={},
    )


def test_concurrency_classifier():
    assert is_concurrency_safe("db_query", {"sql": "SELECT 1"}) is True
    assert is_concurrency_safe("get_fixed_analysis", {"key": "dau"}) is True
    assert is_concurrency_safe("export_report", {"payload_json": "{}"}) is False
    assert is_concurrency_safe("unknown_tool", {}) is False
    assert is_concurrency_safe("", {}) is False


def test_partition_parallel_then_barrier():
    calls = [
        _call(0, "db_query", {"sql": "SELECT 1"}),
        _call(1, "get_fixed_analysis", {"key": "dau"}),
        _call(2, "export_report", {"payload_json": "{}"}),
        _call(3, "db_query", {"sql": "SELECT 2"}),
    ]
    groups = partition_execution_groups(calls)
    assert len(groups) == 3
    assert groups[0][0] is True and [c.index for c in groups[0][1]] == [0, 1]
    assert groups[1][0] is False and [c.index for c in groups[1][1]] == [2]
    assert groups[2][0] is True and [c.index for c in groups[2][1]] == [3]


def test_parse_tool_calls_json_args():
    raw = [
        {
            "id": "c1",
            "function": {
                "name": "db_query",
                "arguments": json.dumps({"sql": "SELECT 1"}),
            },
        },
        {
            "id": "c2",
            "function": {"name": "get_fixed_analysis", "arguments": "{bad"},
        },
    ]
    pending = parse_tool_calls(raw, round_i=0)
    assert pending[0].args == {"sql": "SELECT 1"}
    assert pending[1].args == {}
    assert pending[1].call_id == "c2"


def test_run_preserves_model_order_despite_completion_order():
    """慢调用先提交、快调用后完成时，outcomes 仍按 index 排序。"""
    lock = threading.Lock()
    started: list[str] = []

    def slow_db(**kwargs):
        with lock:
            started.append("slow")
        time.sleep(0.08)
        return json.dumps({"ok": True, "tag": "slow", "args": kwargs}, ensure_ascii=False)

    def fast_db(**kwargs):
        with lock:
            started.append("fast")
        time.sleep(0.01)
        return json.dumps({"ok": True, "tag": "fast", "args": kwargs}, ensure_ascii=False)

    def dispatch(sql: str = "") -> str:
        if "slow" in sql:
            return slow_db(sql=sql)
        return fast_db(sql=sql)

    tools = {"db_query": dispatch}
    calls = [
        _call(0, "db_query", {"sql": "SELECT slow"}),
        _call(1, "db_query", {"sql": "SELECT fast"}),
    ]
    t0 = time.perf_counter()
    outcomes = run_tool_groups(calls, tools, max_parallel=4)
    elapsed = time.perf_counter() - t0

    assert [o.index for o in outcomes] == [0, 1]
    assert json.loads(outcomes[0].result)["tag"] == "slow"
    assert json.loads(outcomes[1].result)["tag"] == "fast"
    assert outcomes[0].parallel is True and outcomes[1].parallel is True
    # 并行应接近最慢者，而非两者相加
    assert elapsed < 0.14
    assert set(started) == {"slow", "fast"}


def test_export_report_is_barrier_between_queries():
    order: list[str] = []

    def db_query(sql: str = "") -> str:
        order.append(f"db:{sql}")
        time.sleep(0.02)
        return json.dumps({"ok": True, "sql": sql})

    def export_report(payload_json: str = "", title: str = "") -> str:
        order.append("export")
        return json.dumps({"ok": True, "path": "/tmp/x.md", "title": title})

    tools = {"db_query": db_query, "export_report": export_report}
    calls = [
        _call(0, "db_query", {"sql": "A"}),
        _call(1, "db_query", {"sql": "B"}),
        _call(2, "export_report", {"payload_json": "{}", "title": "t"}),
        _call(3, "db_query", {"sql": "C"}),
    ]
    outcomes = run_tool_groups(calls, tools, max_parallel=4)
    assert [o.name for o in outcomes] == [
        "db_query",
        "db_query",
        "export_report",
        "db_query",
    ]
    # export 必须在 A/B 完成后、C 开始前（屏障）
    assert order.index("export") > order.index("db:A")
    assert order.index("export") > order.index("db:B")
    assert order.index("export") < order.index("db:C")
    assert outcomes[2].parallel is False
    assert outcomes[3].parallel is False  # 单元素 parallel 组不标并行


def test_max_parallel_one_forces_serial():
    active = 0
    peak = 0
    lock = threading.Lock()

    def db_query(sql: str = "") -> str:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return json.dumps({"ok": True, "sql": sql})

    calls = [_call(i, "db_query", {"sql": str(i)}) for i in range(3)]
    outcomes = run_tool_groups(calls, {"db_query": db_query}, max_parallel=1)
    assert len(outcomes) == 3
    assert peak == 1
    assert all(o.parallel is False for o in outcomes)
