"""
反馈系统模块
- 用户反馈收集（前端 feedback 按钮）
- 反馈数据存储到 RAGFlow 反馈KB
- 维度：问题 + 答案 + 反馈
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.knowledge_manager import get_knowledge_manager
from utils.logger import get_logger
from utils.helpers import timestamp_now, generate_uuid

logger = get_logger(__name__)


@dataclass
class FeedbackRecord:
    """反馈记录"""
    feedback_id: str = field(default_factory=generate_uuid)
    question: str = ""           # 用户问题
    answer: str = ""             # 助手回答
    feedback: str = ""           # 用户反馈（"thumbs_up" | "thumbs_down" | 文字）
    rating: int = 0              # 评分 1-5（可选）
    session_id: str = ""
    user_id: str = ""
    agent_name: str = ""         # 处理该问题的 Agent 名称
    timestamp: str = field(default_factory=timestamp_now)
    tags: list[str] = field(default_factory=list)  # 标签（后期分析用）

    def to_chunk_content(self) -> str:
        """转为适合存入 KB 的文本格式"""
        import json
        return json.dumps({
            "question": self.question,
            "answer": self.answer,
            "feedback": self.feedback,
            "rating": self.rating,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "timestamp": self.timestamp,
        }, ensure_ascii=False)


class FeedbackSystem:
    """反馈管理"""

    def __init__(self):
        self._km = get_knowledge_manager()

    async def record_feedback(
        self,
        question: str,
        answer: str,
        feedback: str,
        session_id: str,
        user_id: str = "",
        agent_name: str = "",
        rating: int = 0,
    ) -> bool:
        """
        记录用户反馈并存入 RAGFlow 反馈KB
        Returns:
            True 写入成功
        """
        record = FeedbackRecord(
            question=question,
            answer=answer,
            feedback=feedback,
            rating=rating,
            session_id=session_id,
            user_id=user_id,
            agent_name=agent_name,
        )

        # 写入 RAGFlow 反馈KB
        try:
            success = await self._write_to_feedback_kb(record)
            if success:
                logger.info("Feedback recorded: session=%s, agent=%s, feedback=%s",
                             session_id, agent_name, feedback[:30])
            return success
        except Exception as e:
            logger.error("Failed to record feedback: %s", e)
            return False

    async def search_feedback(
        self,
        query: str,
        top_k: int = 3,
    ) -> list:
        """检索相关反馈（触发时检索，top_k=3）"""
        return await self._km.search("feedback", query, top_k=top_k)

    async def _write_to_feedback_kb(self, record: FeedbackRecord) -> bool:
        """将反馈写入 RAGFlow 反馈KB"""
        import httpx

        kb_id = self._km.kb_ids["feedback"]
        url = f"{self._km._base_url}/documents"
        headers = {
            "Authorization": f"Bearer {self._km._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "kb_id": kb_id,
            "name": f"feedback_{record.feedback_id}",
            "content": record.to_chunk_content(),
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("Write to feedback KB failed: %s", e)
            return False

    # ── 反馈统计（可选）─────────────────────────────────

    async def get_feedback_stats(self, session_id: Optional[str] = None) -> dict:
        """获取反馈统计"""
        # 简化实现：从 KB 中检索统计
        # TODO: 接真实 RAGFlow 后端或独立数据库
        return {
            "total": 0,
            "positive": 0,
            "negative": 0,
        }


# 全局单例
_feedback_system: Optional[FeedbackSystem] = None


def get_feedback_system() -> FeedbackSystem:
    global _feedback_system
    if _feedback_system is None:
        _feedback_system = FeedbackSystem()
    return _feedback_system
