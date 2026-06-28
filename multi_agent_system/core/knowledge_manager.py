"""
知识库管理模块
封装 RAGFlow 检索接口，管理四类知识库
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class KBChunk:
    """知识库检索结果块"""
    content: str
    kb_type: str          # longterm_memory / business / feedback / database
    kb_id: str
    score: float          # 相似度分数
    weight: float         # 权重（用于排序）
    metadata: dict = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.md5(self.content.encode("utf-8")).hexdigest()


class KnowledgeManager:
    """RAGFlow 知识库管理"""

    def __init__(self):
        settings = get_settings()
        self._base_url = settings.ragflow.base_url
        self._api_key = settings.ragflow.api_key
        self._timeout = settings.ragflow.request_timeout

        # 四个 KB 的 ID
        self.kb_ids = {
            "longterm_memory": settings.ragflow.kb_longterm_memory,
            "business":       settings.ragflow.kb_business,
            "feedback":       settings.ragflow.kb_feedback,
            "database":       settings.ragflow.kb_database,
        }

        # 权重配置
        self.kb_weights = {
            "longterm_memory": 0.7,
            "business":        0.8,
            "database":        0.9,
            "feedback":        1.0,
        }

        self.similarity_threshold = settings.ragflow.default_similarity_threshold
        self.dedup_threshold = settings.ragflow.dedup_threshold

    # ── 检索接口 ────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def search(
        self,
        kb_type: str,
        query: str,
        top_k: int = 3,
        similarity_threshold: Optional[float] = None,
    ) -> list[KBChunk]:
        """
        在指定知识库中检索
        Args:
            kb_type: longterm_memory | business | feedback | database
            query: 检索查询
            top_k: 返回条数
            similarity_threshold: 相似度阈值，低于此值的结果被过滤
        Returns:
            KBChunk 列表（按相似度降序）
        """
        kb_id = self.kb_ids.get(kb_type)
        if not kb_id:
            logger.warning("Unknown KB type: %s", kb_type)
            return []

        threshold = similarity_threshold or self.similarity_threshold
        weight = self.kb_weights.get(kb_type, 0.5)

        try:
            chunks = await self._call_ragflow_api(kb_id, query, top_k)
        except Exception as e:
            logger.error("RAGFlow search failed for %s: %s", kb_type, e)
            return []

        results = []
        for item in chunks:
            score = float(item.get("similarity", item.get("score", 0.0)))
            if score < threshold:
                continue
            results.append(KBChunk(
                content=item.get("content", ""),
                kb_type=kb_type,
                kb_id=kb_id,
                score=score,
                weight=weight,
                metadata=item.get("metadata", item),
            ))

        results.sort(key=lambda c: c.score, reverse=True)
        return results

    async def _call_ragflow_api(
        self, kb_id: str, query: str, top_k: int,
    ) -> list[dict]:
        """调用 RAGFlow 检索 API"""
        url = f"{self._base_url}/retrieval"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "kb_ids": [kb_id],
            "question": query,
            "top_k": top_k,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # RAGFlow 返回格式: {"code": 0, "data": {"chunks": [...]}}
        if data.get("code") == 0:
            return data.get("data", {}).get("chunks", [])
        logger.warning("RAGFlow API non-zero code: %s", data)
        return []

    # ── 批量检索 ────────────────────────────────────────

    async def multi_search(
        self,
        kb_types: list[str],
        query: str,
        top_k_map: Optional[dict[str, int]] = None,
    ) -> dict[str, list[KBChunk]]:
        """
        并行检索多个知识库
        Args:
            kb_types: 要检索的KB类型列表
            query: 检索查询
            top_k_map: 每个KB类型的top_k映射
        Returns:
            {kb_type: [chunks]}
        """
        import asyncio

        top_k_map = top_k_map or {}
        tasks = []
        for kb_type in kb_types:
            top_k = top_k_map.get(kb_type, 3)
            tasks.append(self.search(kb_type, query, top_k))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for kb_type, result in zip(kb_types, results):
            if isinstance(result, Exception):
                logger.error("Multi-search failed for %s: %s", kb_type, result)
                output[kb_type] = []
            else:
                output[kb_type] = result

        return output

    # ── 语义去重 ────────────────────────────────────────

    def deduplicate(
        self,
        chunks: list[KBChunk],
        threshold: Optional[float] = None,
    ) -> list[KBChunk]:
        """
        语义去重：相似度超过阈值的保留权重高的
        """
        if not chunks:
            return []

        threshold = threshold or self.dedup_threshold
        # 简化为基于内容哈希的去重
        seen: dict[str, KBChunk] = {}

        for chunk in chunks:
            h = chunk.content_hash
            if h in seen:
                # 保留权重高的
                if chunk.weight > seen[h].weight:
                    seen[h] = chunk
            else:
                seen[h] = chunk

        return list(seen.values())

    # ── 上下文拼接 ───────────────────────────────────────

    def assemble_context(
        self,
        chunks: list[KBChunk],
        conversation_history: Optional[str] = None,
    ) -> str:
        """
        按规则拼接上下文:
        1. 按权重排序
        2. 语义去重
        3. 按拼接顺序: 原生KB → 长期记忆 → 反馈 → 数据库
        """
        if not chunks:
            return conversation_history or ""

        # 1. 按权重降序
        sorted_chunks = sorted(chunks, key=lambda c: c.weight, reverse=True)

        # 2. 语义去重
        deduped = self.deduplicate(sorted_chunks)

        # 3. 按拼接顺序分组
        splice_order = ["business", "longterm_memory", "feedback", "database"]
        groups: dict[str, list[KBChunk]] = {k: [] for k in splice_order}
        for c in deduped:
            kb = c.kb_type
            if kb in groups:
                groups[kb].append(c)

        # 4. 拼接
        sections = []
        for kb_type in splice_order:
            group = groups[kb_type]
            if not group:
                continue
            label_map = {
                "business": "【业务知识】",
                "longterm_memory": "【长期记忆】",
                "feedback": "【历史反馈】",
                "database": "【数据库信息】",
            }
            label = label_map.get(kb_type, f"【{kb_type}】")
            content = "\n---\n".join(c.content for c in group)
            sections.append(f"{label}\n{content}")

        context = "\n\n".join(sections)

        # 拼接对话历史
        if conversation_history:
            context = f"【对话历史】\n{conversation_history}\n\n{context}"

        return context

    # ── CRUD 操作（长期记忆写入/删除）─────────────────────

    async def write_to_longterm_memory(
        self,
        content: str,
        summary: str,
        session_id: str,
        trigger_keyword: str,
    ) -> bool:
        """将用户记忆写入长期记忆KB"""
        import json

        kb_id = self.kb_ids["longterm_memory"]
        url = f"{self._base_url}/documents"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "kb_id": kb_id,
            "name": f"memory_{session_id}_{summary[:30]}",
            "content": json.dumps({
                "original": content,
                "summary": summary,
                "session_id": session_id,
                "trigger_keyword": trigger_keyword,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
            }, ensure_ascii=False),
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            logger.info("Long-term memory written: session=%s", session_id)
            return True
        except Exception as e:
            logger.error("Failed to write long-term memory: %s", e)
            return False

    async def delete_from_longterm_memory(
        self,
        session_id: str,
        query: str,
    ) -> bool:
        """从长期记忆KB中删除对应内容（通过检索+删除实现）"""
        chunks = await self.search("longterm_memory", query, top_k=5)
        if not chunks:
            logger.info("No matching long-term memory found to delete")
            return False

        # 尝试通过 RAGFlow API 删除文档
        for chunk in chunks:
            doc_id = chunk.metadata.get("doc_id") or chunk.metadata.get("id")
            if not doc_id:
                continue
            url = f"{self._base_url}/documents/{doc_id}"
            headers = {"Authorization": f"Bearer {self._api_key}"}
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.delete(url, headers=headers)
                    if resp.status_code == 200:
                        logger.info("Deleted long-term memory doc: %s", doc_id)
            except Exception as e:
                logger.error("Failed to delete memory doc %s: %s", doc_id, e)

        return True


# 全局单例
_knowledge_manager: Optional[KnowledgeManager] = None


def get_knowledge_manager() -> KnowledgeManager:
    global _knowledge_manager
    if _knowledge_manager is None:
        _knowledge_manager = KnowledgeManager()
    return _knowledge_manager
