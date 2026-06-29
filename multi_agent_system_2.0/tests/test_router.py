from __future__ import annotations

from agents.router_agent import RouterAgent


def test_router_handles_multi_intent_chain() -> None:
    router = RouterAgent()
    result = router.handle(
        session_id="s1",
        user_id="demo-user",
        query="查询上个月销售数据并生成图表、报表和PPT",
    )
    assert result["status"] == "success"
    assert len(result["planned_tasks"]) >= 3


def test_router_returns_confirmation_for_write_queries() -> None:
    router = RouterAgent()
    result = router.handle(
        session_id="s2",
        user_id="demo-user",
        query="把状态表里面运行中的状态改成终止",
    )
    first_result = result["results"][0]
    assert first_result["status"] == "confirmation_required"
    assert first_result["confirmation_required"] is True
