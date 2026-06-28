"""
Skill: Preset_Management
BA 可预设报表的样式模板 —— 管理报表预设
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from utils.logger import get_logger

logger = get_logger(__name__)


class PresetManager:
    """报表样式预设管理 Skill"""

    # 预设样式定义
    PRESETS = {
        "standard": {
            "name": "标准报表",
            "style": "default",
            "description": "适合日常数据报表，蓝色表头、标准字体",
            "columns": "all",
            "sort": "none",
        },
        "executive": {
            "name": "高管简报",
            "style": "compact",
            "description": "适合管理层汇报，紧凑排版、重点突出",
            "columns": "key",
            "sort": "desc",
        },
        "detailed": {
            "name": "详细分析",
            "style": "colorful",
            "description": "适合深度数据分析，彩色标注、详细展开",
            "columns": "all",
            "sort": "asc",
        },
    }

    def __init__(self, agent: BaseAgent):
        self.agent = agent

    def match_preset(self, query: str) -> dict[str, Any]:
        """根据用户 Query 匹配最佳样式预设"""
        query_lower = query.lower()

        if any(w in query_lower for w in ["高管", "管理层", "领导", "汇报", "简报"]):
            return self.PRESETS["executive"]
        elif any(w in query_lower for w in ["详细", "深入", "分析", "明细"]):
            return self.PRESETS["detailed"]
        else:
            return self.PRESETS["standard"]

    def get_preset(self, name: str) -> dict[str, Any]:
        """获取指定预设"""
        return self.PRESETS.get(name, self.PRESETS["standard"])

    def list_presets(self) -> list[dict]:
        """列出所有可用预设"""
        return [
            {"name": k, "display": v["name"], "description": v["description"]}
            for k, v in self.PRESETS.items()
        ]
