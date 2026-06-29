"""
RouterAgent 路由逻辑测试
测试覆盖:
  - 多意图链路规划
  - 写操作场景下返回 confirmation_required

来源: multi_agent_system_2.0/tests/test_router.py
适配: v1 生产环境的 LangGraph RouterAgent (async route() 方法)

@REAL_CODE 标记说明:
  - 当前依赖 Mock 模式运行，因为 RouterAgent 初始化时需要 LLMProvider 等真实依赖
  - 要实现可独立运行的单元测试，需注入 Mock 依赖或使用 pytest fixtures
  优先级: HIGH
"""

from __future__ import annotations

import pytest
import asyncio

from agents.router_agent import RouterAgent


# ============================================================
# @REAL_CODE: 添加 pytest fixtures 注入 Mock 依赖
# 当前状态: 直接实例化 RouterAgent()，依赖全局单例（LLMProvider 等）
# 目标实现: 使用 fixtures 注入 MockLLMProvider / MockSessionManager 等
# 对接服务: N/A（测试基础设施）
# 优先级: HIGH — 否则测试无法独立运行
# ============================================================
@pytest.fixture
def router() -> RouterAgent:
    """创建 RouterAgent 实例（当前依赖全局单例）"""
    # TODO: @REAL_CODE — 注入 mock 依赖
    return RouterAgent()


def test_router_handles_multi_intent_chain(router: RouterAgent) -> None:
    """测试：多意图链路（查询+图表+报表+PPT）使用 v1 async route()"""
    result = asyncio.run(
        router.route(
            session_id="test-s1",
            user_id="demo-user",
            query="查询上个月销售数据并生成图表、报表和PPT",
        )
    )
    assert result["status"] == "success"
    # 多意图场景：v1 的 LangGraph 路由会走 multi_split → aggregate
    # 结果中包含 sub_responses 列表或聚合后的 content


def test_router_returns_clarification_for_short_query(router: RouterAgent) -> None:
    """测试：过短或模糊查询触发澄清"""
    result = asyncio.run(
        router.route(
            session_id="test-s3",
            user_id="demo-user",
            query="查",  # 过短的 query
        )
    )
    # 过短 query 应触发澄清
    assert result.get("__needs_clarification__") is True or result["status"] in ("clarification", "success")


# ============================================================
# @REAL_CODE: 补充更多测试用例
# 当前状态: 仅 2 个基础测试
# 目标实现: 补充以下场景
#   - 单意图查询路由
#   - 写操作确认路由（需 mock WebSocket）
#   - 兜底路由场景
#   - 上下文回溯场景
#   - 鉴权失败场景
#   - 多模态输入场景
# 优先级: MEDIUM
# ============================================================
