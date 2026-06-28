"""
Agent 3: Data_Report_Agent
数据表格报表生成 —— 支持样式预设
Skills: Type_Range_Judgment, Preset_Management, Common_Data_Report_Generate
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from agents.sub_agents.skills.common_data_report_generate_skill import CommonDataReportGenerate
from utils.logger import get_logger

logger = get_logger(__name__)


class DataReportAgent(BaseAgent):
    """Agent 3: 数据表格报表生成"""

    agent_name = "data_report"
    agent_description = "数据表格报表生成：Excel格式，支持样式预设和下载"

    kb_search_config = {
        "database": {"top_k": 1, "required": True},
        "longterm_memory": {"top_k": 3, "required": False},
        "feedback": {"top_k": 3, "required": False},
    }

    def __init__(self, session_id: str, user_id: str = ""):
        super().__init__(session_id, user_id)
        self._report_generator = CommonDataReportGenerate(self)

    async def process(self, query: str, context: str) -> dict[str, Any]:
        """
        核心流程：
        1. 数据鉴权
        2. 类型范围判断 → 匹配数据表 scope
        3. 复用 Common_Data_Query 查数据
        4. 样式预设匹配
        5. Excel 生成 → 返回下载链接
        """
        logger.info("DataReportAgent processing: %s", query[:100])

        # Step 1: 鉴权
        has_perm = await self._auth.check_subsystem_permission(
            self.user_id, "data_report"
        )
        if not has_perm:
            return {"status": "error", "content": "⚠️ 没有数据报表子系统的访问权限。"}

        # Step 2-5: 委托给 CommonDataReportGenerate
        result = await self._report_generator.generate(query, context)
        return result
