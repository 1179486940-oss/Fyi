"""
Agent 1: Data_Query_Agent
数据表增删改查 —— 数据类操作的核心 Agent
Skills: NSG_Borrow_Data_Process, Comment_Data_Process
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from agents.sub_agents.skills.nsg_borrow_data_process import NSGBorrowDataProcess
from agents.sub_agents.skills.comment_data_process import CommentDataProcess
from utils.logger import get_logger

logger = get_logger(__name__)


class DataQueryAgent(BaseAgent):
    """Agent 1: 数据表增删改查"""

    agent_name = "data_query"
    agent_description = "数据表增删改查、数据转存、数据清洗"

    # 知识库检索配置
    kb_search_config = {
        "database": {"top_k": 1, "required": True},
        "longterm_memory": {"top_k": 3, "required": False},
        "feedback": {"top_k": 3, "required": False},
    }

    def __init__(self, session_id: str, user_id: str = ""):
        super().__init__(session_id, user_id)
        self._nsg_skill = NSGBorrowDataProcess(self)
        self._comment_skill = CommentDataProcess(self)

    async def process(self, query: str, context: str) -> dict[str, Any]:
        """
        核心业务处理：
        判断用户 Query 涉及哪个数据流程（NSG 或 Comment），
        然后调用对应 Skill 处理。
        """
        logger.info("DataQueryAgent processing: %s", query[:100])

        # 判断数据流程类型
        process_type = self._detect_process_type(query)

        try:
            if process_type == "nsg":
                return await self._nsg_skill.execute(query, context)
            elif process_type == "comment":
                return await self._comment_skill.execute(query, context)
            else:
                # 默认走 NSG 流程
                return await self._nsg_skill.execute(query, context)
        except Exception as e:
            logger.error("DataQueryAgent error: %s", e)
            return {
                "status": "error",
                "content": f"数据查询处理出错：{str(e)}",
            }

    def _detect_process_type(self, query: str) -> str:
        """判断用户 Query 涉及哪个数据流程"""
        query_lower = query.lower()

        # Comment 相关关键词
        comment_keywords = ["评论", "留言", "comment", "回复", "评价", "反馈内容"]
        if any(kw in query_lower for kw in comment_keywords):
            return "comment"

        # 默认 NSG
        return "nsg"
