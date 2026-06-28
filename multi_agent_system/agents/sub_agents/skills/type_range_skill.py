"""
Skill: Type_Range_Judgment
类型范围判断 —— 根据用户 Query 判断报表数据的类型和范围
用于 Data_Report_Agent 的前置过滤逻辑
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from utils.logger import get_logger

logger = get_logger(__name__)


class TypeRangeJudgment:
    """类型范围判断 Skill"""

    def __init__(self, agent: BaseAgent):
        self.agent = agent
        self._llm = agent._llm

    async def analyze(self, query: str) -> dict[str, Any]:
        """
        分析用户 Query，提取：
        - 数据类型（销售、库存、人力…）
        - 时间范围
        - 聚合维度
        - 排序要求
        """
        prompt = f"""分析以下用户提问，提取数据查询的关键参数。

用户提问：{query}

请以 JSON 格式返回（只返回 JSON，不要其他内容）：
{{
    "data_type": "数据类型（如：销售数据、库存数据、人力数据…）",
    "time_range": "时间范围（如：上个月、最近一周、2026年Q2…）",
    "group_by": "聚合维度（如：按日期、按部门、按产品…）",
    "order_by": "排序要求（如：升序、降序、按金额…）",
    "filters": ["过滤条件列表"]
}}"""

        try:
            response = await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            # 提取 JSON
            json_match = response.strip()
            if "```json" in json_match:
                json_match = json_match.split("```json")[1].split("```")[0]
            return json.loads(json_match)
        except Exception as e:
            logger.warning("Type range analysis failed: %s", e)
            return {
                "data_type": "unknown",
                "time_range": "未指定",
                "group_by": "未指定",
                "order_by": "未指定",
                "filters": [],
            }
