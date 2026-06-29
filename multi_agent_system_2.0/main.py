from __future__ import annotations

from agents.router_agent import RouterAgent


def build_demo_router() -> RouterAgent:
    return RouterAgent()


def main() -> None:
    router = build_demo_router()
    demo_result = router.handle(
        session_id="demo-session",
        user_id="demo-user",
        query="查询上个月销售数据并生成图表和PPT",
    )
    print(demo_result)


if __name__ == "__main__":
    main()
