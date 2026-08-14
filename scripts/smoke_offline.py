"""无服务冒烟：校验 slash 路由与工具注册（不要求 CK）。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.agent.react_engine import TOOLS
from app.core.routing.slash_router import route_input


def main() -> None:
    assert "db_query" in TOOLS
    assert "get_fixed_analysis" in TOOLS
    assert route_input("/dau")["execution_path"] == "fixed_slash"
    assert route_input("随便问问日活")["execution_path"] == "agent_loop"
    print("smoke_offline ok")


if __name__ == "__main__":
    main()
