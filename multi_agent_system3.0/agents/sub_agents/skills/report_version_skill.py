"""
Skill: Report_Version_Matching
Data_Graph_Agent 专用 —— 从用户 Query 中提取三要素
（日期/车型/周数），匹配 Report Version 字段

流程：
1. 提取：日期(如20260611) + 车型(如A12) + 周数(如SW22)
2. 查询 Report Version 全集
3. 模糊匹配 → 精确命中 → 直接使用
4. 模糊匹配 → Top3 相似 → double confirm 确认
"""

from __future__ import annotations

import re
from typing import Any, Optional

from core.agent_base import BaseAgent
from utils.logger import get_logger

logger = get_logger(__name__)


class ReportVersionMatcher:
    """Report Version 匹配 Skill"""

    def __init__(self, agent: BaseAgent):
        self.agent = agent
        self._llm = agent._llm

    async def match(self, query: str) -> dict[str, Any]:
        """
        从 Query 中提取关键信息并匹配 Report Version
        Returns:
            {"status": "success/need_confirm", "report_version": "..." or None,
             "candidates": [...], "extracted_info": {...}}
        """
        # Step 1: 提取三要素
        extracted = self._extract_key_info(query)

        # Step 2: 查询 Report Version 全集
        from agents.sub_agents.mcp.db_mcp import DatabaseMCP
        db_mcp = DatabaseMCP()
        versions_result = await db_mcp.execute_query(
            "SELECT DISTINCT \"Report Version\" FROM report_data ORDER BY \"Report Version\"",
            max_preview_fields=1,
        )
        all_versions = [r["Report Version"] for r in versions_result.get("rows", [])
                        if r.get("Report Version")]

        if not all_versions:
            # Mock 数据
            all_versions = ["20260611_A12_SW22", "20260611_A13_SW22",
                           "20260611_A12_SW23", "20260610_A12_SW22", "20260611_A14_SW21"]

        # Step 3: 模糊匹配
        best_match, candidates = self._fuzzy_match(extracted, all_versions)

        if best_match:
            # 精确命中
            logger.info("Report Version matched exactly: %s", best_match)
            return {
                "status": "success",
                "report_version": best_match,
                "extracted_info": extracted,
            }

        if candidates:
            # Top3 → double confirm
            logger.info("Report Version fuzzy: top %d candidates", len(candidates))
            return {
                "status": "need_confirm",
                "report_version": None,
                "candidates": candidates[:3],
                "extracted_info": extracted,
            }

        return {
            "status": "error",
            "report_version": None,
            "message": "无法匹配到任何 Report Version",
        }

    async def confirm_candidate(
        self, candidates: list[str], user_choice: str,
    ) -> Optional[str]:
        """
        用户从 Top3 候选中选择一个
        user_choice: "1" / "第一个" / "20260611_A12_SW22"
        """
        # 尝试按序号解析
        try:
            idx = int(user_choice) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
        except ValueError:
            pass

        # 尝试按文本匹配
        for c in candidates:
            if c == user_choice or user_choice in c:
                return c

        return None

    # ── 提取关键信息 ─────────────────────────────────────

    def _extract_key_info(self, query: str) -> dict[str, Optional[str]]:
        """从 Query 中提取日期、车型、周数"""
        info = {
            "date": None,
            "car_model": None,
            "week_number": None,
        }

        # 提取日期：8位数字 YYYYMMDD
        date_match = re.search(r'\b(\d{8})\b', query)
        if date_match:
            info["date"] = date_match.group(1)

        # 提取车型：字母+数字（如 A12, B3, X200）
        car_match = re.search(r'\b([A-Za-z]\d{1,3})\b', query)
        if car_match:
            info["car_model"] = car_match.group(1)

        # 提取周数：SW + 数字（如 SW22）
        week_match = re.search(r'\b(SW\d{1,2})\b', query, re.IGNORECASE)
        if week_match:
            info["week_number"] = week_match.group(1).upper()

        logger.debug("Extracted key info: %s", info)
        return info

    def _fuzzy_match(
        self, extracted: dict, versions: list[str],
    ) -> tuple[Optional[str], list[str]]:
        """
        模糊匹配：完全匹配 → 部分匹配 → Top N 候选
        Returns:
            (精确匹配结果, 候选列表)
        """
        candidates = []

        for version in versions:
            score = self._match_score(extracted, version)
            if score >= 3:
                return version, []  # 精确命中
            elif score >= 1:
                candidates.append((version, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return None, [c[0] for c in candidates[:3]]

    def _match_score(self, extracted: dict, version: str) -> int:
        """匹配得分：每个要素匹配得1分"""
        score = 0
        if extracted["date"] and extracted["date"] in version:
            score += 1
        if extracted["car_model"] and extracted["car_model"].lower() in version.lower():
            score += 1
        if extracted["week_number"] and extracted["week_number"].lower() in version.lower():
            score += 1
        return score
