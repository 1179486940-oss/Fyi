"""
Skill: Common_Graph_Generate
Data_Graph_Agent 核心 —— 根据数据查询结果生成分析图
复用 Common_Data_Query 逻辑查询数据 → 调用 chart_mcp 生成图表
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from agents.sub_agents.skills.common_data_query_skill import CommonDataQuery
from utils.logger import get_logger

logger = get_logger(__name__)


class CommonGraphGenerate:
    """图表生成 Skill"""

    CHART_TYPES = {
        "折线图": "line",
        "柱状图": "bar",
        "饼图": "pie",
        "瀑布图": "waterfall",
        "甘特图": "gantt",
        "散点图": "scatter",
    }

    def __init__(self, agent: BaseAgent):
        self.agent = agent
        self._data_query = CommonDataQuery(agent)

    async def generate(
        self,
        query: str,
        context: str,
        chart_type: str = "auto",
    ) -> dict[str, Any]:
        """
        生成分析图表
        Args:
            query: 用户查询
            context: 对话上下文
            chart_type: 图表类型（auto 时由 AI 判断）
        Returns:
            {"status": "success/error", "content": "...", "download_url": "..."}
        """
        # Step 1: 复用 Common_Data_Query 查数据
        data_result = await self._data_query.query(query, context)
        if data_result.get("status") != "success":
            return data_result

        rows = data_result.get("rows", [])
        if not rows:
            return {
                "status": "error",
                "content": "未查询到可用于生成图表的数据。",
            }

        # Step 2: 判断图表类型 & 选择字段
        if chart_type == "auto":
            chart_type, x_field, y_field = await self._infer_chart_config(query, rows)
        else:
            # 用户指定了图表类型
            x_field, y_field = self._auto_select_fields(rows)
            chart_type = self.CHART_TYPES.get(chart_type, "bar")

        # Step 3: 调用 chart_mcp 生成图表
        from agents.sub_agents.mcp.chart_mcp import ChartMCP
        chart_mcp = ChartMCP()

        if chart_type == "pie":
            result = await chart_mcp.generate_pie_chart(
                data=rows, label_field=x_field, value_field=y_field,
                title=query[:30],
            )
        else:
            result = await chart_mcp._generate_chart(
                chart_type=chart_type, data=rows,
                x_field=x_field, y_field=y_field,
                title=query[:30], output_format="html",
            )

        if result.get("status") != "success":
            return {"status": "error", "content": f"图表生成失败：{result.get('message', '')}"}

        download_url = result.get("download_url", "")
        thought = f"数据查询完成（{len(rows)} 条）→ 生成{chart_type}图"

        return {
            "status": "success",
            "content": f"{self.agent.display_thought(thought)}\n\n"
                       f"📊 图表已生成 [{self.agent.display_url(download_url)}]({download_url})",
            "download_url": download_url,
            "chart_type": chart_type,
            "data": rows,
        }

    # ── 辅助方法 ────────────────────────────────────────

    def _auto_select_fields(self, rows: list[dict]) -> tuple[str, str]:
        """自动选择 x 轴和 y 轴字段"""
        if not rows:
            return ("name", "value")

        columns = list(rows[0].keys())
        # 优先找数值型字段作为 y
        numeric_cols = []
        text_cols = []
        for col in columns:
            sample = rows[0].get(col)
            if isinstance(sample, (int, float)):
                numeric_cols.append(col)
            else:
                text_cols.append(col)

        y_field = numeric_cols[0] if numeric_cols else (columns[1] if len(columns) > 1 else columns[0])
        x_field = text_cols[0] if text_cols else (columns[0] if columns[0] != y_field else columns[1] if len(columns) > 1 else "id")

        return (x_field, y_field)

    async def _infer_chart_config(
        self, query: str, rows: list[dict],
    ) -> tuple[str, str, str]:
        """AI 推断最佳图表类型和字段"""
        x_field, y_field = self._auto_select_fields(rows)

        # 简单规则判断
        query_lower = query.lower()
        if any(w in query_lower for w in ["占比", "比例", "饼图", "百分比"]):
            return ("pie", x_field, y_field)
        elif any(w in query_lower for w in ["趋势", "变化", "折线", "走势"]):
            return ("line", x_field, y_field)
        else:
            return ("bar", x_field, y_field)
