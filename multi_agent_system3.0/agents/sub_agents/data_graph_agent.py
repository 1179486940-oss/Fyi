"""
Agent 2: Data_Graph_Agent
数据分析图生成 —— 柱状图、折线图、饼图、瀑布图、甘特图
Skills: Report_Version_Matching, Common_Graph_Generate
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from agents.sub_agents.skills.report_version_skill import ReportVersionMatcher
from agents.sub_agents.skills.common_graph_generate_skill import CommonGraphGenerate
from utils.logger import get_logger

logger = get_logger(__name__)


class DataGraphAgent(BaseAgent):
    """Agent 2: 数据分析图生成"""

    agent_name = "data_graph"
    agent_description = "数据分析图生成：柱状图、折线图、饼图、瀑布图、甘特图等"

    kb_search_config = {
        "database": {"top_k": 1, "required": True},
        "longterm_memory": {"top_k": 3, "required": False},
        "feedback": {"top_k": 3, "required": False},
    }

    def __init__(self, session_id: str, user_id: str = ""):
        super().__init__(session_id, user_id)
        self._version_matcher = ReportVersionMatcher(self)
        self._graph_generator = CommonGraphGenerate(self)

    async def process(self, query: str, context: str) -> dict[str, Any]:
        """
        核心流程：
        1. 鉴权
        2. Report Version 匹配（三要素提取 + 模糊匹配 + double confirm）
        3. 以 Report Version 查询数据
        4. 生成图表
        """
        logger.info("DataGraphAgent processing: %s", query[:100])

        # Step 1: 鉴权
        has_perm = await self._auth.check_subsystem_permission(
            self.user_id, "data_graph"
        )
        if not has_perm:
            return {"status": "error", "content": "⚠️ 没有数据分析图子系统的访问权限。"}

        # Step 2: Report Version 匹配
        match_result = await self._version_matcher.match(query)

        if match_result["status"] == "error":
            return {"status": "error", "content": match_result.get("message", "Report Version 匹配失败")}

        if match_result["status"] == "need_confirm":
            # 需要 double confirm —— 返回候选列表让用户选择
            candidates = match_result.get("candidates", [])
            candidate_list = "\n".join(f"{i+1}. {c}" for i, c in enumerate(candidates))
            return {
                "status": "need_confirm",
                "content": (
                    f"{self.display_thought('Report Version 模糊匹配，找到以下候选：')}\n\n"
                    f"请选择一个 Report Version：\n{candidate_list}\n\n"
                    f"提取到的信息：{match_result.get('extracted_info', {})}"
                ),
                "candidates": candidates,
                "__needs_confirmation__": True,
            }

        # Step 3 & 4: 查询数据 → 生成图表
        report_version = match_result["report_version"]
        chart_query = f"{query} (Report Version: {report_version})"

        result = await self._graph_generator.generate(chart_query, context)
        return result
