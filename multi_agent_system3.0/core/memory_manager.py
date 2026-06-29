"""
记忆管理模块
- 短期记忆：会话历史（由 SessionManager 管理，窗口 10-15 轮）
- 长期记忆：触发关键词检测 → RAGFlow 写入/检索
"""

from __future__ import annotations

from typing import Optional

from config import get_settings
from core.knowledge_manager import get_knowledge_manager
from core.session_manager import Session
from utils.logger import get_logger
from utils.helpers import extract_keywords, timestamp_now

logger = get_logger(__name__)


class MemoryManager:
    """记忆管理器"""

    def __init__(self):
        settings = get_settings()
        self._longterm_enabled = True
        self._trigger_keywords = settings.longterm_memory_triggers
        self._delete_keywords = settings.longterm_memory_delete_triggers

    # ── 触发检测 ─────────────────────────────────────────

    def detect_longterm_memory_trigger(self, query: str) -> Optional[str]:
        """
        检测 Query 是否包含长期记忆触发关键词
        Returns:
            匹配到的关键词，无匹配返回 None
        """
        matched = extract_keywords(query, self._trigger_keywords)
        if matched:
            return matched[0]  # 返回第一个匹配的触发词
        return None

    def detect_delete_trigger(self, query: str) -> Optional[str]:
        """检测是否包含删除记忆的关键词"""
        matched = extract_keywords(query, self._delete_keywords)
        if matched:
            return matched[0]
        return None

    # ── 短期记忆 ─────────────────────────────────────────

    def get_short_term_context(self, session: Session) -> str:
        """获取短期记忆上下文（最近 10-15 轮对话历史）"""
        return session.history_text

    def add_to_short_term(
        self,
        session: Session,
        user_query: str,
        assistant_response: str,
    ) -> None:
        """添加一轮对话到短期记忆"""
        session.add_message("user", user_query)
        session.add_message("assistant", assistant_response)

    # ── 长期记忆：检测并写入 ──────────────────────────────

    async def try_write_longterm_memory(
        self,
        query: str,
        session: Session,
    ) -> Optional[str]:
        """
        检测触发关键词，如果匹配则写入长期记忆
        Returns:
            "✅ 已记住：xxx" 或 None（无触发）
        """
        trigger = self.detect_longterm_memory_trigger(query)
        if not trigger:
            return None

        km = get_knowledge_manager()

        # 生成摘要（简化版：取 query 前 100 字）
        summary = query.replace(trigger, "").strip()[:100]
        if not summary:
            summary = query[:100]

        success = await km.write_to_longterm_memory(
            content=query,
            summary=summary,
            session_id=session.session_id,
            trigger_keyword=trigger,
        )

        if success:
            logger.info("Long-term memory triggered: kw=%s, session=%s",
                         trigger, session.session_id)
            return f"✅ 已记住：{summary}"
        return "⚠️ 记忆写入失败，请稍后重试"

    # ── 长期记忆：检测并删除 ──────────────────────────────

    async def try_delete_longterm_memory(
        self,
        query: str,
        session: Session,
    ) -> Optional[str]:
        """检测删除关键词，匹配则从长期记忆中删除"""
        trigger = self.detect_delete_trigger(query)
        if not trigger:
            return None

        km = get_knowledge_manager()
        await km.delete_from_longterm_memory(
            session_id=session.session_id,
            query=query.replace(trigger, "").strip(),
        )
        return "✅ 已忘记相关内容"

    # ── 长期记忆检索 ─────────────────────────────────────

    async def search_longterm_memory(
        self,
        query: str,
        top_k: int = 3,
    ) -> list:
        """从长期记忆KB中检索相关内容"""
        km = get_knowledge_manager()
        return await km.search("longterm_memory", query, top_k=top_k)

    # ── 上下文检测 ─────────────────────────────────────

    def detect_context_reset(self, query: str) -> bool:
        """检测是否需要重置上下文"""
        settings = get_settings()
        return any(kw in query for kw in settings.context_reset_triggers)

    def detect_context_restore(self, query: str) -> bool:
        """检测是否需要恢复上下文"""
        settings = get_settings()
        return any(kw in query for kw in settings.context_restore_triggers)


# 全局单例
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
