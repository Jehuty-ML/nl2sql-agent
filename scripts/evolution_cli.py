"""自进化：列出提案 / promote。

用法（仓库根目录）:
  python scripts/evolution_cli.py list
  python scripts/evolution_cli.py promote prop_xxxx
  python scripts/evolution_cli.py promote prop_xxxx --skip-execute
  python scripts/evolution_cli.py strategies
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="nl2sql-agent evolution CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出 skill 提案")
    p_list.add_argument("--pending-only", action="store_true")

    p_prom = sub.add_parser("promote", help="验收并写入 overlay")
    p_prom.add_argument("proposal_id")
    p_prom.add_argument("--skip-execute", action="store_true")

    sub.add_parser("strategies", help="列出策略与当前激活")
    sub.add_parser("registry", help="当前 fixed keys / slash")
    sub.add_parser("status", help="自进化开关状态")

    args = parser.parse_args()

    from app.config import settings

    if args.cmd == "status":
        print(
            json.dumps(
                {
                    "enabled": bool(settings.enable_evolution),
                    "active_strategy_id": settings.active_strategy_id,
                    "pattern_threshold": int(settings.evolution_pattern_threshold),
                    "hint": (
                        None
                        if settings.enable_evolution
                        else "在 .env 设置 ENABLE_EVOLUTION=true 并重启"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.cmd in ("list", "promote", "strategies") and not settings.enable_evolution:
        print(
            "自进化未开启：请在 .env 设置 ENABLE_EVOLUTION=true 后重试。",
            file=sys.stderr,
        )
        return 2

    if args.cmd == "list":
        from app.core.evolution.proposer import list_proposals, maybe_propose_skills

        maybe_propose_skills()
        rows = list_proposals(pending_only=args.pending_only)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "promote":
        from app.core.evolution.promote import promote_proposal

        out = promote_proposal(args.proposal_id, skip_execute=args.skip_execute)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("ok") else 1

    if args.cmd == "strategies":
        from app.core.evolution.strategy import list_strategies, load_strategy

        active = load_strategy()
        print(
            json.dumps(
                {"active": active.get("id"), "strategies": list_strategies()},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.cmd == "registry":
        from app.core.evolution.registry import fixed_query_keys, get_dashboard_commands

        print(
            json.dumps(
                {
                    "evolution_enabled": bool(settings.enable_evolution),
                    "fixed_keys": fixed_query_keys(),
                    "slash": list(get_dashboard_commands().keys()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
