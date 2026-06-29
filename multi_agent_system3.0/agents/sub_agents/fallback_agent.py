"""
Agent 5: Fallback_Agent (兜底Agent)
当用户 Query 不属于任何业务子 Agent 时，走通用 KB-QA 路线
Skill: Common_KB_QA
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from agents.sub_agents.skills.common_kb_qa import CommonKBQA
from utils.logger import get_logger

logger = get_logger(__name__)


class FallbackAgent(BaseAgent):
    """Agent 5: 兜底 Agent —— 通用知识库问答"""

    agent_name = "fallback"
    agent_description = "通用知识库问答：当用户问题不匹配任何业务场景时走此路线"

    kb_search_config = {
        "business": {"top_k": 5, "required": True},
        "longterm_memory": {"top_k": 3, "required": False},
        "feedback": {"top_k": 3, "required": False},
    }

    def __init__(self, session_id: str, user_id: str = ""):
        super().__init__(session_id, user_id)
        self._qa_skill = CommonKBQA(self)

    async def process(self, query: str, context: str) -> dict[str, Any]:
        """
        核心流程：
        1. 检索业务KB（必检 top_k=5）
        2. 触发关键词检测 → 可选长期记忆 + 反馈
        3. 上下文拼接 → LLM 生成回答
        """
        logger.info("FallbackAgent processing: %s", query[:100])
        return await self._qa_skill.answer(query, context)
