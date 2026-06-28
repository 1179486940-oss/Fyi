"""
Agent 4: PPT_Generate_Agent
PPT 生成 —— 通过 BA 提供的两个 MCP Server 实现
Skills: Content, Design, Outline, Layout, Animation
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from agents.sub_agents.skills.content_skill import PPTContentSkill
from agents.sub_agents.skills.outline_skill import PPTOutlineSkill
from agents.sub_agents.skills.design_skill import PPTDesignSkill
from agents.sub_agents.skills.layout_skill import PPTLayoutSkill
from agents.sub_agents.skills.animation_skill import PPTAnimationSkill
from utils.logger import get_logger

logger = get_logger(__name__)


class PPTGenerateAgent(BaseAgent):
    """Agent 4: PPT 生成"""

    agent_name = "ppt_generate"
    agent_description = "PPT生成：内容撰写、排版设计、动画效果，支持多种模板"

    kb_search_config = {
        "business": {"top_k": 3, "required": True},
        "longterm_memory": {"top_k": 3, "required": False},
        "feedback": {"top_k": 3, "required": False},
    }

    def __init__(self, session_id: str, user_id: str = ""):
        super().__init__(session_id, user_id)
        self._content_skill = PPTContentSkill(self)
        self._outline_skill = PPTOutlineSkill(self)
        self._design_skill = PPTDesignSkill(self)
        self._layout_skill = PPTLayoutSkill(self)
        self._animation_skill = PPTAnimationSkill(self)

    async def process(self, query: str, context: str) -> dict[str, Any]:
        """
        核心流程：
        1. 鉴权
        2. 理解用户需求 → 匹配 PPT 模板
        3. 调用 MCP Server 查询数据
        4. 调用 MCP Server 生成 PPT
        5. 返回下载链接
        """
        logger.info("PPTGenerateAgent processing: %s", query[:100])

        # Step 1: 鉴权
        has_perm = await self._auth.check_subsystem_permission(
            self.user_id, "ppt_generate"
        )
        if not has_perm:
            return {"status": "error", "content": "⚠️ 没有PPT生成子系统的访问权限。"}

        # Step 2: 匹配 PPT 模板（边界判断）
        from agents.sub_agents.mcp.ppt_query_mcp import PPTQueryMCP
        ppt_query = PPTQueryMCP()
        templates = await ppt_query.get_template_list()

        template = await self._match_template(query, templates)
        logger.info("PPT template selected: %s", template["name"])

        # Step 3: 生成大纲 → 内容
        outline_result = await self._outline_skill.generate(query, context)

        # Step 4: 查询 PPT 所需数据
        data_result = await ppt_query.query_ppt_data({"topic": query, "template": template["id"]})

        # Step 5: 生成 PPT（调用 MCP Server 2）
        from agents.sub_agents.mcp.ppt_generate_mcp import PPTGenerateMCP
        ppt_generate = PPTGenerateMCP()

        result = await ppt_generate.generate_ppt(
            template_id=template["id"],
            data=data_result.get("data", {}),
            ppt_config={
                "title": query[:50],
                "subtitle": f"模板: {template['name']}",
            },
        )

        if result.get("status") != "success":
            return {"status": "error", "content": f"PPT生成失败：{result.get('message', '')}"}

        download_url = result.get("download_url", "")
        thought = f"选用模板「{template['name']}」→ 生成大纲 → 调用PPT生成接口"

        return {
            "status": "success",
            "content": (
                f"{self.display_thought(thought)}\n\n"
                f"📊 PPT 已生成 [{self.display_url(download_url)}]({download_url})\n"
                f"模板：{template['name']}"
            ),
            "download_url": download_url,
            "template": template,
        }

    async def _match_template(self, query: str, templates: list[dict]) -> dict:
        """通过边界判断匹配最佳 PPT 模板"""
        query_lower = query.lower()

        # 规则匹配（边界判断）
        rules = {
            "工作汇报": ["汇报", "工作", "总结", "周报", "月报", "年报"],
            "数据展示": ["数据", "分析", "图表", "统计", "指标"],
            "方案策划": ["方案", "策划", "计划", "规划", "提案"],
            "产品展示": ["产品", "介绍", "展示", "演示", "说明"],
        }

        for category, keywords in rules.items():
            if any(kw in query_lower for kw in keywords):
                for t in templates:
                    if t.get("category") == category:
                        return t

        # 默认第一个模板
        return templates[0] if templates else {"id": "tpl_001", "name": "通用模板", "category": "通用"}
