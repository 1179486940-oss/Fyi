"""
Skill: Common_KB_QA
兜底 Agent 核心 —— 通用知识库问答
模块一：必检业务KB（top_k=5）
模块二：触发关键词检测 → 可选长期记忆KB + 反馈KB（top_k=3）
模块三：上下文拼接（反馈1.0 > 业务0.8 > 长期记忆0.7）
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from core.knowledge_manager import KBChunk
from utils.logger import get_logger

logger = get_logger(__name__)


class CommonKBQA:
    """通用 KB 问答 Skill"""

    def __init__(self, agent: BaseAgent):
        self.agent = agent
        self._km = agent._km
        self._memory = agent._memory

    async def answer(self, query: str, context: str) -> dict[str, Any]:
        """
        执行通用 KB 问答
        流程：检索业务KB → 可选长期记忆/反馈 → 上下文拼接 → LLM 回答
        """
        # 模块一：必检业务KB（top_k=5）
        biz_chunks = await self._km.search("business", query, top_k=5)
        logger.debug("Fallback: business KB retrieved %d chunks", len(biz_chunks))

        # 模块二：触发关键词检测 → 可选检索
        extra_chunks: list[KBChunk] = []
        if self._memory.detect_longterm_memory_trigger(query):
            lt_chunks = await self._km.search("longterm_memory", query, top_k=3)
            fb_chunks = await self._km.search("feedback", query, top_k=3)
            extra_chunks.extend(lt_chunks)
            extra_chunks.extend(fb_chunks)
            logger.debug("Fallback: extra KBs: lt=%d, fb=%d", len(lt_chunks), len(fb_chunks))

        # 模块三：上下文拼接
        all_chunks = list(biz_chunks) + extra_chunks
        full_context = self._km.assemble_context(all_chunks, context)

        if not biz_chunks and not extra_chunks:
            # 没有任何知识库内容
            return {
                "status": "success",
                "content": (
                    "抱歉，我在当前知识库中没有找到与您问题直接相关的内容。\n\n"
                    "您可以尝试：\n"
                    "1. 换个更具体的方式描述您的问题\n"
                    "2. 询问数据库查询、图表生成、报表或PPT相关的问题\n"
                    "3. 联系管理员补充相关知识库内容"
                ),
            }

        # LLM 生成回答
        response = await self.agent._call_llm(
            context=full_context,
            user_query=query,
            system_prompt=self._build_qa_prompt(),
        )

        thought = f"兜底QA：检索业务KB（{len(biz_chunks)}条）→ LLM生成回答"
        return {
            "status": "success",
            "content": f"{self.agent.display_thought(thought)}\n\n{response}",
        }

    def _build_qa_prompt(self) -> str:
        return """你是一个智能知识库问答助手。请基于提供的上下文信息回答用户问题。

要求：
1. 回答准确、基于给定的上下文信息
2. 如果上下文信息不足以回答问题，诚实说明
3. 用自然友好的语气
4. 思考过程用 <thinking></thinking> 包裹
5. URL 用 <url></url> 包裹"""
