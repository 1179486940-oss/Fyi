"""
Sub-Agent 基类（v2 增强版）
所有子 Agent 继承此基类，提供：
- 会话初始化
- 上下文加载（短期记忆 + 知识库检索 + 多模态理解）
- LLM 调用生成回答
- 思考过程标签包裹
- 流式传输（加标识字段标记待确认消息）
- 统一执行入口（模板方法模式）

v2 增强:
- 接入 core/models.py 统一数据模型（AgentResult, AgentEvent, ConfirmationPayload 等）
- 接入 core/confirmation_service.py 独立确认服务
- 接入 core/query_service.py 独立查询服务
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional

from config import get_settings
from core.llm_provider import get_llm_provider
from core.knowledge_manager import get_knowledge_manager, KBChunk
from core.session_manager import Session, get_session_manager
from core.memory_manager import get_memory_manager
from core.auth_manager import get_auth_manager
from core.guardrails import get_guardrails
from middleware.ws_manager import get_ws_manager
from middleware.confirmation_middleware import ConfirmationMiddleware, get_confirmation_middleware
from utils.logger import get_logger
from utils.helpers import wrap_thinking, wrap_url

# ============================================================
# v2 增强: 导入统一数据模型和独立服务
# 来源: multi_agent_system_2.0/core/agent_base.py
# ============================================================
from core.models import (          # @REAL_CODE: 逐步迁移返回值到 AgentResult
    AgentResult,
    AgentEvent,
    ConfirmationPayload,
    Artifact,
    Attachment,
)
from core.confirmation_service import ConfirmationService  # @REAL_CODE: 独立确认服务
from core.query_service import QueryService, QueryPlan     # @REAL_CODE: 独立查询服务

logger = get_logger(__name__)


class BaseAgent(ABC):
    """子 Agent 基类"""

    # 子类覆写这些属性
    agent_name: str = "base"
    agent_description: str = ""

    # 知识库检索配置
    kb_search_config: dict[str, dict] = {}  # {kb_type: {top_k: int, required: bool}}

    def __init__(self, session_id: str, user_id: str = ""):
        self.session_id = session_id
        self.user_id = user_id
        self._llm = get_llm_provider()
        self._km = get_knowledge_manager()
        self._memory = get_memory_manager()
        self._auth = get_auth_manager()
        self._ws = get_ws_manager()
        self._confirm: ConfirmationMiddleware = get_confirmation_middleware()
        self._session_mgr = get_session_manager()

        self._session: Optional[Session] = None

    # ── 模板方法：统一执行入口 ──────────────────────────

    async def execute(
        self,
        query: str,
        multimodal_files: Optional[list[dict]] = None,
        stream: bool = True,
    ) -> dict[str, Any]:
        """
        统一执行入口（模板方法）
        Args:
            query: 用户查询
            multimodal_files: 多模态文件列表 [{"path": "...", "type": "image/pdf"}]
            stream: 是否流式
        Returns:
            {"status": "success/error", "content": "...", "metadata": {...}}
        """
        # 1. 获取会话
        self._session = self._session_mgr.get_session(self.session_id)
        if not self._session:
            self._session = self._session_mgr.create_session(self.user_id)

        # 2. 多模态理解（如有文件）
        if multimodal_files:
            query = await self._process_multimodal(query, multimodal_files)

        # 3. 加载上下文（短期记忆 + 知识库检索）
        context = await self.load_context(query)

        # 4. 子类实现：核心业务逻辑
        try:
            result = await self.process(query, context)
        except Exception as e:
            logger.error("Agent %s process failed: %s", self.agent_name, e)
            result = {
                "status": "error",
                "content": f"处理请求时出错：{str(e)}",
            }

        # 5. 更新短期记忆
        content = result.get("content", "")
        if content:
            self._memory.add_to_short_term(
                self._session, query, content,
            )

        return result

    # ── 上下文加载 ──────────────────────────────────────

    async def load_context(self, query: str) -> str:
        """
        加载上下文：短期记忆 + 知识库检索
        子类可覆写 _get_kb_search_config() 来自定义检索策略
        """
        # 短期记忆
        short_term = self._memory.get_short_term_context(self._session)

        # 知识库检索（按子类配置）
        all_chunks = await self._search_knowledge_bases(query)

        # 拼接上下文
        context = self._km.assemble_context(all_chunks, short_term)
        return context

    async def _search_knowledge_bases(self, query: str) -> list[KBChunk]:
        """按子类配置检索知识库"""
        config = self.kb_search_config
        if not config:
            return []

        all_chunks: list[KBChunk] = []

        for kb_type, kb_cfg in config.items():
            top_k = kb_cfg.get("top_k", 3)
            required = kb_cfg.get("required", False)

            if required:
                # 必检 KB
                chunks = await self._km.search(kb_type, query, top_k=top_k)
                all_chunks.extend(chunks)
            else:
                # 可选 KB：仅当触发关键词存在时检索
                if self._memory.detect_longterm_memory_trigger(query):
                    chunks = await self._km.search(kb_type, query, top_k=top_k)
                    all_chunks.extend(chunks)

        return all_chunks

    # ── 多模态处理 ──────────────────────────────────────

    async def _process_multimodal(
        self, query: str, files: list[dict],
    ) -> str:
        """处理多模态文件，提取文本拼入 Query"""
        extracted_texts = []
        for file_info in files:
            file_path = file_info.get("path", "")
            file_type = file_info.get("type", "image")
            if file_path and file_type in ("image", "pdf"):
                try:
                    text = await self._llm.understand_multimodal(
                        file_path, file_type,
                        context_query=f"用户提问：{query}\n请提取文件中的相关内容。",
                    )
                    extracted_texts.append(text)
                except Exception as e:
                    logger.error("Multimodal processing failed for %s: %s", file_path, e)

        if extracted_texts:
            multimodal_context = "\n\n【文件内容】\n" + "\n---\n".join(extracted_texts)
            query = f"{query}\n{multimodal_context}"

        return query

    # ── 写操作确认断点 ──────────────────────────────────

    async def _breakpoint_confirm(
        self,
        operation: str,
        table: str,
        found_data: list[dict],
        changes: dict,
    ) -> bool:
        """
        确认断点（方案A：子 Agent 内部调用）
        在 SELECT 之后、执行 UPDATE/INSERT/DELETE 之前调用
        Returns:
            True → 用户确认，继续执行
            False → 用户取消/超时
        """
        result = await self._confirm.intercept(
            operation_type=operation,
            table=table,
            affected_data=found_data,
            changes=changes,
            session_id=self.session_id,
        )
        return result.is_confirmed

    # ── LLM 调用 ────────────────────────────────────────

    async def _call_llm(
        self,
        context: str,
        user_query: str,
        system_prompt: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        """调用 LLM 生成回答"""
        if not system_prompt:
            system_prompt = self._build_default_system_prompt()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"上下文信息：\n{context}\n\n用户提问：{user_query}"},
        ]

        return await self._llm.chat(messages, system_prompt=system_prompt)

    async def _call_llm_stream(
        self,
        context: str,
        user_query: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """流式调用 LLM"""
        if not system_prompt:
            system_prompt = self._build_default_system_prompt()

        messages = [
            {"role": "user", "content": f"上下文信息：\n{context}\n\n用户提问：{user_query}"},
        ]

        async for chunk in self._llm.chat_stream(messages, system_prompt=system_prompt):
            yield chunk

    def _build_default_system_prompt(self) -> str:
        """构建默认 System Prompt"""
        return f"""你是一个智能助手，专门处理{self.agent_description}相关的任务。

要求：
1. 回答准确、简洁、专业
2. 思考过程用 <thinking></thinking> 标签包裹
3. URL 链接用 <url></url> 标签包裹
4. 如果不确定，诚实说明，不要编造
5. 如果是模糊指令，主动澄清"""

    # ── 思考过程展示 ────────────────────────────────────

    def display_thought(self, thought: str) -> str:
        """用标签包裹思考过程"""
        return wrap_thinking(thought)

    def display_url(self, url: str) -> str:
        """用标签包裹 URL"""
        return wrap_url(url)

    # ── 流式推送 ────────────────────────────────────────

    async def push_stream(self, content: str, is_final: bool = False) -> None:
        """通过 WebSocket 推送流式内容到前端"""
        await self._ws.push_stream_chunk(
            session_id=self.session_id,
            content=content,
            is_final=is_final,
        )

    async def push_clarification(self, question: str) -> None:
        """推送澄清问题（带标识字段）"""
        await self._ws.push_stream_chunk(
            session_id=self.session_id,
            content=question,
            is_clarification=True,
            is_final=True,
        )

    # ── 子类必须实现 ────────────────────────────────────

    @abstractmethod
    async def process(self, query: str, context: str) -> dict[str, Any]:
        """
        核心业务处理逻辑（子类覆写）
        Returns:
            {"status": "success/error", "content": "回答文本", ...}
        """
        ...
