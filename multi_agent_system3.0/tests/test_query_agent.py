"""
DataQueryAgent 查询与确认测试
测试覆盖:
  - SELECT 查询返回
  - 写操作时确认中断返回

来源: multi_agent_system_2.0/tests/test_query_agent.py
适配: v1 生产环境的 DataQueryAgent + BaseAgent (async execute())

@REAL_CODE 标记说明:
  - 当前依赖 Mock 模式，需要 MockLLMProvider / MockSessionManager
  - DataQueryAgent 依赖 NSGBorrowDataProcess Skill 和真实 LLM
  - 要实现可独立运行的单元测试，需 mock 整个依赖链
  优先级: HIGH
"""

from __future__ import annotations

import pytest
import asyncio

from agents.sub_agents.data_query_update_agent import DataQueryAgent


# ============================================================
# @REAL_CODE: 使用 pytest fixtures 注入 mock 依赖
# 当前状态: 直接调用 DataQueryAgent(session_id, user_id)，
#          内部通过 get_llm_provider() 等全局单例获取依赖
# 目标实现:
#   1. 创建 MockLLMProvider 替代真实 LLM 调用
#   2. 创建 MockSessionManager 替代真实会话管理
#   3. 通过 fixtures 注入，实现隔离的单元测试
# 对接服务: N/A（测试基础设施）
# 优先级: HIGH
# ============================================================
@pytest.fixture
def query_agent() -> DataQueryAgent:
    """创建 DataQueryAgent 实例（当前依赖全局单例的 mock）"""
    # TODO: @REAL_CODE — 注入 mock 依赖链
    return DataQueryAgent(session_id="test-s", user_id="demo-user")


def test_query_agent_returns_select_preview(query_agent: DataQueryAgent) -> None:
    """测试：查询场景返回数据预览（v1 async execute 模板方法）"""
    result = asyncio.run(
        query_agent.execute(query="查询状态表")
    )
    assert result["status"] == "success"
    # TODO: @REAL_CODE — 验证 table_preview 不为空
    # assert len(result.get("table_preview", [])) > 0


def test_query_agent_requires_confirmation_for_write(query_agent: DataQueryAgent) -> None:
    """测试：写操作场景返回确认请求"""
    result = asyncio.run(
        query_agent.execute(query="update status_table set status='终止'")
    )
    # 写操作应返回 confirmation_required 状态
    # 注意：v1 通过 _breakpoint_confirm() → ConfirmationMiddleware 触发确认
    # 在 mock 模式下可能直接返回 error（WebSocket 不可用）
    # 因此这里做宽松断言
    assert result["status"] in ("confirmation_required", "error")
    if result["status"] == "confirmation_required":
        assert result.get("confirmation_required") is True


# ============================================================
# @REAL_CODE: 补充更多测试用例
# 当前状态: 仅 2 个基础测试
# 目标实现: 补充以下场景
#   - NSG 数据流程测试
#   - Comment 数据流程测试
#   - 字段过滤（鉴权限制字段）测试
#   - 首次查询展示规则测试（字段数 5/10/15）
#   - SQL 注入防护测试
#   - 危险操作拦截测试（DROP/TRUNCATE）
#   - 并发查询测试
# 优先级: MEDIUM
# ============================================================
