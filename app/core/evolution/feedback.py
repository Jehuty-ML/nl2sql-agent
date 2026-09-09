"""L1 反馈闭环：注入后的门闩结果 → tip 升降权 / 策略补丁候选。"""

from __future__ import annotations

import time
from typing import Any

from app.core.evolution import store


def apply_tip_feedback(
    *,
    delivery_reason: str,
    injected_classes: list[str],
) -> dict[str, Any]:
    """根据本轮 delivery_floor 结果，调整上一轮已注入 tip 的权重。

    - 同类失败再次出现 → 降权（教训未改进行为）
    - 本轮 success / reason=none 且曾注入过教训 → 小幅升权
    """
    if not injected_classes:
        return {"updated": []}

    data = store.load_negative()
    tips = data.setdefault("tips", {})
    updated: list[dict[str, Any]] = []
    reason = (delivery_reason or "").strip() or "none"

    for ec in injected_classes:
        row = tips.get(ec)
        if not isinstance(row, dict):
            continue
        w = float(row.get("weight") or 1.0)
        before = w
        if reason == "none":
            w = min(2.0, w * 1.15)
            row["effective_count"] = int(row.get("effective_count") or 0) + 1
            row["last_feedback"] = "effective"
        elif reason == ec or (
            ec == "incomplete_or_detail" and reason == "incomplete_evidence"
        ) or (ec == "empty_or_failed" and reason == "empty_rows"):
            w = max(0.15, w * 0.65)
            row["ineffective_count"] = int(row.get("ineffective_count") or 0) + 1
            row["last_feedback"] = "ineffective"
        else:
            # 注入了教训但本轮是别的失败类型：不升降，仅记一次观测
            row["last_feedback"] = "other_failure"
        row["weight"] = round(w, 4)
        row["updated_at"] = time.time()
        tips[ec] = row
        updated.append(
            {
                "error_class": ec,
                "weight_before": before,
                "weight_after": row["weight"],
                "feedback": row["last_feedback"],
            }
        )

    if updated:
        store.save_negative(data)
    return {"updated": updated}


def maybe_queue_strategy_patch(error_class: str, hit_count: int) -> dict[str, Any] | None:
    """同类门闩失败累计达阈值 → 写入策略补丁候选（待人工 activate）。"""
    if hit_count < 3:
        return None
    if error_class not in ("missing_ok_query", "incomplete_evidence", "incomplete_or_detail"):
        return None

    doc = store.read_json("strategy_patches.json", {"patches": []})
    patches = list(doc.get("patches") or [])
    for p in patches:
        if (
            isinstance(p, dict)
            and p.get("based_on") == error_class
            and p.get("status") == "pending"
        ):
            return None

    patch = {
        "id": f"patch_{error_class}_{int(time.time())}",
        "based_on": error_class,
        "status": "pending",
        "created_at": time.time(),
        "diff_summary": _patch_summary(error_class),
        "suggested_prompt_addon": _patch_addon(error_class),
    }
    patches.append(patch)
    store.write_json("strategy_patches.json", {"patches": patches})
    return patch


def _patch_summary(error_class: str) -> str:
    return {
        "missing_ok_query": "强化：禁止无查数交卷；必须先 get_fixed_analysis/db_query。",
        "incomplete_evidence": "强化：禁止仅用截断/明细样本写汇总结论。",
        "incomplete_or_detail": "强化：汇总题必须 GROUP BY 或 fixed analysis。",
    }.get(error_class, f"针对 {error_class} 加强策略约束")


def _patch_addon(error_class: str) -> str:
    return {
        "missing_ok_query": (
            "\n【进化补丁·强制查数】用户要结论/建议时，若尚未成功查数，"
            "禁止输出运营建议正文；必须先调用查数工具。"
        ),
        "incomplete_evidence": (
            "\n【进化补丁·完备证据】不得仅依据 truncated/detail 样本写总和/排名；"
            "必须改用聚合或 get_fixed_analysis。"
        ),
        "incomplete_or_detail": (
            "\n【进化补丁·禁明细汇总】汇总类问题禁止明细 SQL。"
        ),
    }.get(error_class, "")


def list_pending_patches() -> list[dict[str, Any]]:
    doc = store.read_json("strategy_patches.json", {"patches": []})
    return [
        p
        for p in (doc.get("patches") or [])
        if isinstance(p, dict) and p.get("status") == "pending"
    ]
