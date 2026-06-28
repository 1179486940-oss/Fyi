"""
MCP: PPT 数据查询接口
封装 BA 提供的接口1 —— 数据查询
"""

from __future__ import annotations

from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class PPTQueryMCP:
    """PPT 数据查询 MCP Server
    封装 BA 提供的接口1，负责查询生成 PPT 所需的源数据
    """

    def __init__(self):
        # TODO: 配置 BA 接口1 的实际地址
        self._api_base_url = ""
        self._api_key = ""

    async def query_ppt_data(
        self,
        query_params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        调用 BA 接口1 查询数据
        Args:
            query_params: 查询参数（由 PPT Agent 根据用户需求构造）
        Returns:
            BA 接口返回的数据
        """
        logger.info("PPT query MCP called: params=%s", query_params)

        # TODO: 对接 BA 真实接口
        # 当前返回 Mock 数据用于开发
        return {
            "status": "success",
            "data": [
                {"title": "示例PPT数据", "content": "这是PPT生成所需的示例数据"},
            ],
        }

    async def get_template_list(self) -> list[dict]:
        """获取可用的 PPT 模板列表"""
        # TODO: 对接 BA 接口获取模板列表
        return [
            {"id": "tpl_001", "name": "汇报总结", "category": "工作汇报", "pages": 10},
            {"id": "tpl_002", "name": "数据分析", "category": "数据展示", "pages": 8},
            {"id": "tpl_003", "name": "项目方案", "category": "方案策划", "pages": 12},
            {"id": "tpl_004", "name": "产品介绍", "category": "产品展示", "pages": 6},
            {"id": "tpl_005", "name": "年度总结", "category": "工作总结", "pages": 15},
        ]

    async def get_template_detail(self, template_id: str) -> Optional[dict]:
        """获取指定模板的详细信息"""
        templates = await self.get_template_list()
        for t in templates:
            if t["id"] == template_id:
                return t
        return None
