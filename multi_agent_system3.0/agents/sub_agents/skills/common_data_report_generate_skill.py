"""
Skill: Common_Data_Report_Generate
Data_Report_Agent 核心 —— 根据查询结果生成 Excel 表格报表
复用 Common_Data_Query → 样式预设 → Excel 生成
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from agents.sub_agents.skills.common_data_query_skill import CommonDataQuery
from agents.sub_agents.skills.preset_skill import PresetManager
from utils.logger import get_logger

logger = get_logger(__name__)


class CommonDataReportGenerate:
    """数据报表生成 Skill"""

    def __init__(self, agent: BaseAgent):
        self.agent = agent
        self._data_query = CommonDataQuery(agent)
        self._preset_mgr = PresetManager(agent)

    async def generate(self, query: str, context: str) -> dict[str, Any]:
        """
        生成 Excel 报表
        流程：数据查询 → 样式预设 → Excel 生成 → 返回下载链接
        """
        # Step 1: 数据鉴权（在调用此 Skill 前由 Agent 完成）

        # Step 2: 分析查询参数（类型范围）
        from agents.sub_agents.skills.type_range_skill import TypeRangeJudgment
        type_analyzer = TypeRangeJudgment(self.agent)
        query_params = await type_analyzer.analyze(query)
        logger.info("Report query params: %s", query_params)

        # Step 3: 复用 Common_Data_Query 查数据
        data_result = await self._data_query.query(query, context)
        if data_result.get("status") != "success":
            return data_result

        rows = data_result.get("rows", [])
        if not rows:
            return {
                "status": "error",
                "content": "未查询到可用于生成报表的数据。",
            }

        # Step 4: 匹配样式预设
        preset = self._preset_mgr.match_preset(query)

        # Step 5: 生成 Excel
        from agents.sub_agents.mcp.excel_mcp import ExcelMCP
        excel_mcp = ExcelMCP()
        result = await excel_mcp.generate_excel(
            data=rows,
            sheet_name=query_params.get("data_type", "Sheet1"),
            title=f"{query_params.get('data_type', '数据报表')} - {query_params.get('time_range', '')}",
            style_preset=preset.get("style", "default"),
        )

        if result.get("status") != "success":
            return {"status": "error", "content": f"报表生成失败：{result.get('message', '')}"}

        download_url = result.get("download_url", "")
        thought = f"数据查询（{len(rows)} 条）→ 应用 {preset['name']} 样式 → 生成 Excel"

        return {
            "status": "success",
            "content": (
                f"{self.agent.display_thought(thought)}\n\n"
                f"📊 报表已生成 [{self.agent.display_url(download_url)}]({download_url})\n"
                f"样式：{preset['name']} | 数据量：{len(rows)} 条"
            ),
            "download_url": download_url,
            "row_count": len(rows),
            "preset": preset,
        }
