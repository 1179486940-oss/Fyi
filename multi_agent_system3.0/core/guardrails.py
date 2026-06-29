"""
边界判断 & 动态阈值 & 兜底降级 & 澄清触发
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config import get_settings
from core.llm_provider import get_llm_provider
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class IntentScore:
    """意图匹配评分"""
    skill_name: str
    skill_description: str
    similarity: float           # Embedding 相似度 (0~1)
    above_threshold: bool = True


@dataclass
class IntentResult:
    """意图识别结果"""
    is_single_intent: bool = True
    is_clarification_needed: bool = False
    clarification_question: str = ""
    matched_skills: list[IntentScore] = field(default_factory=list)
    multi_intent_groups: list[list[IntentScore]] = field(default_factory=list)

    # 上下文回溯
    should_reset_context: bool = False
    should_restore_context: bool = False

    @property
    def best_match(self) -> Optional[IntentScore]:
        """得分最高的匹配"""
        if self.matched_skills:
            return self.matched_skills[0]
        return None

    @property
    def needs_fallback(self) -> bool:
        """是否需要走兜底"""
        return len(self.matched_skills) == 0


class Guardrails:
    """边界判断与兜底降级"""

    def __init__(self):
        settings = get_settings()
        self._llm = get_llm_provider()
        self._skill_registry = settings.skill_registry
        self._min_threshold = settings.embedding_min_threshold

        # 上下文回溯关键词
        self._reset_triggers = settings.context_reset_triggers
        self._restore_triggers = settings.context_restore_triggers

    # ── 意图识别 ────────────────────────────────────────

    async def recognize_intent(self, query: str) -> IntentResult:
        """
        识别用户 Query 的意图
        1. 先检测上下文回溯
        2. Embedding 相似度打分
        3. 动态阈值过滤
        4. 多意图检测
        5. 澄清判断
        """
        result = IntentResult()

        # Step 0: 上下文回溯检测
        result.should_reset_context = self._detect_context_reset(query)
        result.should_restore_context = self._detect_context_restore(query)
        if result.should_reset_context or result.should_restore_context:
            # 回溯操作不需要意图识别
            return result

        # Step 1: 多意图检测
        if self._detect_multi_intent(query):
            result.is_single_intent = False
            result.multi_intent_groups = await self._score_multi_intent(query)
            return result

        # Step 2: 单意图 Embedding 打分
        scores = await self._score_all_skills(query)

        # Step 3: 动态阈值过滤
        threshold = self._compute_dynamic_threshold(scores)
        filtered = [s for s in scores if s.similarity >= threshold]

        if not filtered:
            # 全部低于阈值 → 检查是否需要澄清
            if self._should_clarify(query, scores):
                result.is_clarification_needed = True
                result.clarification_question = await self._generate_clarification(query)
            # 否则走兜底（needs_fallback = True）
            return result

        # 按相似度降序
        filtered.sort(key=lambda s: s.similarity, reverse=True)
        result.matched_skills = filtered

        # Step 4: 边界判断 — 多个 Skill 相似度接近时靠 description 界定
        if len(filtered) > 1:
            top, second = filtered[0], filtered[1]
            gap = top.similarity - second.similarity
            if gap < 0.05:  # 差距太小，需要进一步界定
                logger.info("Close match: %s(%.3f) vs %s(%.3f)",
                             top.skill_name, top.similarity,
                             second.skill_name, second.similarity)
                result.matched_skills = await self._disambiguate(query, filtered[:3])

        return result

    # ── Embedding 打分 ──────────────────────────────────

    async def _score_all_skills(self, query: str) -> list[IntentScore]:
        """对每个 Skill 计算 Embedding 相似度"""
        query_emb = await self._llm.get_embedding(query)
        scores = []

        for skill_name, skill_desc in self._skill_registry.items():
            desc_emb = await self._llm.get_embedding(skill_desc)
            similarity = self._llm.compute_similarity(query_emb, desc_emb)
            scores.append(IntentScore(
                skill_name=skill_name,
                skill_description=skill_desc,
                similarity=similarity,
                above_threshold=similarity >= self._min_threshold,
            ))

        scores.sort(key=lambda s: s.similarity, reverse=True)
        return scores

    async def _score_multi_intent(self, query: str) -> list[list[IntentScore]]:
        """
        多意图拆分打分
        将 query 按分隔词拆开，对每个子部分单独打分
        """
        # 简单按多意图分隔符拆分
        separators = ["然后", "同时", "另外", "还有", "并且", "之后", "接着"]
        parts = [query]
        for sep in separators:
            new_parts = []
            for p in parts:
                new_parts.extend(p.split(sep))
            parts = [p.strip() for p in new_parts if p.strip()]

        if len(parts) <= 1:
            return [[await self._score_all_skills(query)[:1]]]

        groups = []
        for part in parts:
            scores = await self._score_all_skills(part)
            if scores:
                groups.append(scores[:1])  # 每部分取最高分
        return groups

    # ── 动态阈值 ─────────────────────────────────────────

    def _compute_dynamic_threshold(self, scores: list[IntentScore]) -> float:
        """
        动态阈值计算：
        - 至少有一个 Skill 得分较高时，提高阈值以确保精准匹配
        - 所有 Skill 得分都低时，降低阈值避免漏网
        """
        if not scores:
            return self._min_threshold

        max_score = max(s.similarity for s in scores)
        avg_score = sum(s.similarity for s in scores) / len(scores)

        if max_score > 0.8:
            # 有明确高分 → 提高阈值
            return max(self._min_threshold, 0.55)
        elif max_score < 0.4:
            # 普遍低分 → 降低阈值
            return max(self._min_threshold - 0.1, 0.30)
        else:
            return self._min_threshold

    # ── 澄清判断 ─────────────────────────────────────────

    def _should_clarify(self, query: str, scores: list[IntentScore]) -> bool:
        """判断是否需要向用户澄清"""
        # 条件1：Query 非常短（<5字）
        if len(query.strip()) < 5:
            return True

        # 条件2：所有 Skill 得分都极低
        if scores and max(s.similarity for s in scores) < 0.25:
            return True

        # 条件3：Query 包含模糊词
        vague_words = ["那个", "这个", "之前那个", "帮我弄一下", "处理下"]
        if any(w in query for w in vague_words):
            return True

        return False

    async def _generate_clarification(self, query: str) -> str:
        """生成澄清问题"""
        prompt = f"""用户的提问比较模糊，请生成一个礼貌的澄清问题来帮助理解用户意图。

用户提问: "{query}"

要求: 用中文，友好自然，给出2-3个具体选项帮助用户明确需求。"""
        return await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
        )

    # ── 边界消歧 ─────────────────────────────────────────

    async def _disambiguate(
        self, query: str, candidates: list[IntentScore]
    ) -> list[IntentScore]:
        """
        多个 Skill 得分接近时，利用 LLM 通过 description 界定文字区分
        """
        descriptions = "\n".join(
            f"- {c.skill_name}: {c.skill_description}"
            for c in candidates
        )
        prompt = f"""用户提问: "{query}"

以下是对应的 Skills 及其功能描述:
{descriptions}

请判断用户的意图最匹配哪一个 Skill。只返回 Skill 名称，不要其他内容。"""

        try:
            chosen = await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            chosen = chosen.strip()
            # 将选中的排到第一
            for i, c in enumerate(candidates):
                if c.skill_name in chosen:
                    candidates.insert(0, candidates.pop(i))
                    break
        except Exception as e:
            logger.warning("Disambiguation failed: %s", e)

        return candidates

    # ── 上下文回溯检测 ──────────────────────────────────

    def _detect_context_reset(self, query: str) -> bool:
        return any(kw in query for kw in self._reset_triggers)

    def _detect_context_restore(self, query: str) -> bool:
        return any(kw in query for kw in self._restore_triggers)

    # ── 多意图检测 ──────────────────────────────────────

    def _detect_multi_intent(self, query: str) -> bool:
        """检测 Query 是否包含多意图"""
        connectors = ["然后", "同时", "另外", "还有", "并且", "之后", "接着", "以及"]
        count = sum(1 for c in connectors if c in query)
        return count >= 1

    # ── 写操作检测 (v2 增强) ────────────────────────────
    # ============================================================
    # @REAL_CODE: 写操作意图检测应升级为 LLM 语义判断
    # 当前状态: 基于关键词简单匹配（update/delete/insert/modify/change/set）
    # 目标实现: LLM 分析 Query 语义，判断是否为写操作（更准确，减少误判）
    # 对接服务: LLM (deepseek-v4-pro)
    # 参考文档: 设计手册.docx → QueryService Text2SQL 章节
    # 优先级: MEDIUM
    # ============================================================

    def detect_write_intent(self, query: str) -> bool:
        """识别 query 是否可能是写操作（关键词匹配）"""
        write_keywords = [
            "update", "delete", "insert", "modify", "change", "set",
            "更新", "删除", "插入", "修改", "改为", "改成",
            "变更", "调整", "替换", "移除", "新增", "添加",
        ]
        lowered = query.lower()
        return any(kw in lowered for kw in write_keywords)

    # ============================================================
    # @REAL_CODE: 澄清判断升级为 LLM 语义判断
    # 当前状态: 仅检查 query 长度 < 5 字或包含模糊词
    # 目标实现: LLM 分析 query 信息完整度，判断是否需要追问
    # 对接服务: LLM (deepseek-v4-pro)
    # 优先级: MEDIUM
    # ============================================================

    def evaluate_query(self, query: str) -> dict:
        """
        判断 query 是否需要澄清
        返回: {"needs_clarification": bool, "reason": str}
        """
        # 过短 query 触发澄清
        if len(query.strip()) < 5:
            return {"needs_clarification": True, "reason": "query 过短，信息不足"}
        # 模糊词检测
        fuzzy_words = ["那个", "这个", "上次", "之前的", "某个"]
        if any(w in query for w in fuzzy_words):
            return {"needs_clarification": True, "reason": "query 包含模糊指代"}
        return {"needs_clarification": False, "reason": ""}

    # ============================================================
    # @REAL_CODE: 确认卡片 payload 构造
    # 当前状态: 基本实现完成
    # 目标实现: 多表关联写操作时，展示所有受影响的表
    # 对接服务: N/A（纯数据结构构造）
    # 优先级: LOW
    # ============================================================

    def build_confirmation_payload(
        self,
        operation: str,
        summary: str,
        sql: str,
        preview_rows: list[dict],
    ) -> dict:
        """构造写操作确认数据"""
        from utils.helpers import generate_confirm_id
        return {
            "confirmation_id": generate_confirm_id(),
            "operation": operation,
            "summary": summary,
            "sql": sql,
            "preview_rows": preview_rows,
        }


# 全局单例
_guardrails: Optional[Guardrails] = None


def get_guardrails() -> Guardrails:
    global _guardrails
    if _guardrails is None:
        _guardrails = Guardrails()
    return _guardrails
