"""Parallel Tool Calls（PTC）：同一步内并行执行互不依赖的只读工具。

调度约定（对齐 deepseek-harness 思路的精简版）：
- 工具可声明并发安全；缺省 / 未知 → exclusive（屏障）
- 连续的 parallel 调用组成一组；exclusive 单独成组并形成屏障
- 组内用有界线程池并行；组间串行
- 返回结果始终按模型原始 tool_call 顺序（与完成先后无关）
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable


# 只读查数：可与其他 parallel 调用重叠
PARALLEL_SAFE_TOOLS = frozenset({"db_query", "get_fixed_analysis"})

# 写盘 / 副作用：必须独占，形成屏障
EXCLUSIVE_TOOLS = frozenset({"export_report"})


@dataclass
class PendingToolCall:
    """已解析、待调度的一次工具调用（模型顺序下标 = index）。"""

    index: int
    call_id: str
    name: str
    args: dict[str, Any]
    raw_call: dict[str, Any] = field(repr=False)


@dataclass
class ToolCallOutcome:
    """一次工具执行的结果（始终按 PendingToolCall.index 排序提交）。"""

    index: int
    call_id: str
    name: str
    args: dict[str, Any]
    result: str
    model_content: str
    projection: dict[str, Any]
    parallel: bool
    group_id: int


def is_concurrency_safe(name: str, args: dict[str, Any] | None = None) -> bool:
    """一元分类器：仅显式只读工具可并行；其余 fail-closed 为 exclusive。

    args 预留作输入敏感分类（例如将来写工具按路径判断）；当前未使用。
    """
    del args  # 预留
    if not name or name in EXCLUSIVE_TOOLS:
        return False
    return name in PARALLEL_SAFE_TOOLS


def partition_execution_groups(
    calls: list[PendingToolCall],
) -> list[tuple[bool, list[PendingToolCall]]]:
    """按模型顺序切分为执行组。

    返回 [(is_parallel_group, calls), ...]：
    - 连续 safe 调用并入同一 parallel 组
    - unsafe 调用各自成为 exclusive 单例组（屏障）
    """
    groups: list[tuple[bool, list[PendingToolCall]]] = []
    pending_parallel: list[PendingToolCall] = []

    def flush_parallel() -> None:
        nonlocal pending_parallel
        if pending_parallel:
            groups.append((True, pending_parallel))
            pending_parallel = []

    for call in calls:
        if is_concurrency_safe(call.name, call.args):
            pending_parallel.append(call)
        else:
            flush_parallel()
            groups.append((False, [call]))
    flush_parallel()
    return groups


def parse_tool_calls(
    tool_calls: list[dict[str, Any]],
    *,
    round_i: int = 0,
) -> list[PendingToolCall]:
    """从 LLM message.tool_calls 解析为 PendingToolCall 列表。"""
    import json

    pending: list[PendingToolCall] = []
    for i, call in enumerate(tool_calls):
        fn = (call.get("function") or {}).get("name") or "?"
        raw_args = (call.get("function") or {}).get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        call_id = call.get("id") or f"call_{round_i}_{i}_{fn}"
        pending.append(
            PendingToolCall(
                index=i,
                call_id=str(call_id),
                name=fn,
                args=args,
                raw_call=call,
            )
        )
    return pending


def _invoke_one(
    call: PendingToolCall,
    tools: dict[str, Callable[..., str]],
) -> ToolCallOutcome:
    from app.core.tools.pipeline import get_tool_pipeline

    pipeline = get_tool_pipeline()
    pipeline.set_tools(tools)

    pre = pipeline.pre_execute(call.name, call.args)
    if pre.blocked:
        full = pre.result_json
        _, model_str, meta = pipeline.post_execute(call.name, call.args, full)
    else:
        full = pipeline.execute(call.name, call.args)
        full, model_str, meta = pipeline.post_execute(call.name, call.args, full)

    return ToolCallOutcome(
        index=call.index,
        call_id=call.call_id,
        name=call.name,
        args=call.args,
        result=full,
        model_content=model_str,
        projection=meta,
        parallel=False,
        group_id=0,
    )


def run_tool_groups(
    calls: list[PendingToolCall],
    tools: dict[str, Callable[..., str]],
    *,
    max_parallel: int = 4,
) -> list[ToolCallOutcome]:
    """执行全部工具调用，返回按模型顺序排列的结果。

    max_parallel <= 1 时整批串行（便于回退与对照）。
    """
    if not calls:
        return []

    cap = max(1, int(max_parallel))
    force_serial = cap <= 1
    groups = partition_execution_groups(calls)
    outcomes_by_index: dict[int, ToolCallOutcome] = {}

    for group_id, (is_parallel, group) in enumerate(groups):
        run_parallel = is_parallel and not force_serial and len(group) > 1

        if not run_parallel:
            for c in group:
                oc = _invoke_one(c, tools)
                oc.parallel = False
                oc.group_id = group_id
                outcomes_by_index[c.index] = oc
            continue

        workers = min(cap, len(group))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_invoke_one, c, tools): c for c in group}
            for fut in as_completed(futures):
                c = futures[fut]
                try:
                    oc = fut.result()
                except Exception as e:
                    import json

                    full = json.dumps(
                        {"ok": False, "error": f"工具执行异常: {e}"},
                        ensure_ascii=False,
                    )
                    from app.core.tools.pipeline import get_tool_pipeline

                    pipe = get_tool_pipeline()
                    _, model_str, meta = pipe.post_execute(c.name, c.args, full)
                    oc = ToolCallOutcome(
                        index=c.index,
                        call_id=c.call_id,
                        name=c.name,
                        args=c.args,
                        result=full,
                        model_content=model_str,
                        projection=meta,
                        parallel=True,
                        group_id=group_id,
                    )
                oc.parallel = True
                oc.group_id = group_id
                outcomes_by_index[c.index] = oc

    outcomes: list[ToolCallOutcome] = []
    for c in calls:
        outcomes.append(outcomes_by_index[c.index])
    return outcomes
