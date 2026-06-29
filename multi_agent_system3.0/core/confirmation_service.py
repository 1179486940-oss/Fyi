"""
独立确认服务（从 v2 迁移 + v1 中间件抽取）
将确认断点逻辑从 middleware/confirmation_middleware.py 中独立出来，
形成单一职责的确认服务层。

职责:
  - 登记待确认的写操作 (request)
  - 处理用户确认/取消 (resolve)
  - 查询确认状态 (get)
  - 超时自动取消

来源: multi_agent_system_2.0/core/confirmation_service.py
融合: v1 middleware/confirmation_middleware.py 的 ConfirmationMiddleware
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models import ConfirmationPayload
from utils.logger import get_logger
from utils.helpers import timestamp_now

logger = get_logger(__name__)


# ── 确认状态 ─────────────────────────────────────────

@dataclass(slots=True)
class ConfirmationState:
    """单条确认的状态"""
    approved: bool | None = None                # None=待确认, True=已确认, False=已取消
    payload: ConfirmationPayload | None = None
    created_at: str = field(default_factory=timestamp_now)
    resolved_at: str = ""

    # ============================================================
    # @REAL_CODE: 确认超时后的自动清理
    # 当前状态: 状态保存在内存 dict，无自动过期
    # 目标实现: 添加 TTL 机制，超时后自动 resolve 为 timeout
    # 对接服务: asyncio 定时器 / Redis TTL（分布式场景）
    # 参考文档: 中断式确认机制调研.docx
    # 优先级: MEDIUM
    # ============================================================


class ConfirmationService:
    """
    确认服务 — 写操作确认断点的核心逻辑

    与 ConfirmationMiddleware 的关系:
      ConfirmationMiddleware 负责 WebSocket 推送 + Future 挂起（I/O 层）
      ConfirmationService 负责状态管理 + 业务逻辑（业务层）
    """

    def __init__(self, timeout: int = 30):
        self._timeout = timeout
        self._states: dict[str, ConfirmationState] = {}
        # ============================================================
        # @REAL_CODE: 分布式场景下的状态存储
        # 当前状态: 确认状态存储在进程内存 dict（单实例可用）
        # 目标实现: 多实例部署时使用 Redis 存储确认状态
        # 对接服务: Redis
        # 参考文档: 中断式确认机制调研.docx → 分布式确认
        # 优先级: LOW (单实例部署时不需改造)
        # ============================================================

    # ── 核心方法 ──────────────────────────────────────

    def request(self, payload: ConfirmationPayload) -> ConfirmationState:
        """
        登记一条待确认操作

        Args:
            payload: 确认卡片数据（operation/sql/preview_rows 等）

        Returns:
            ConfirmationState (approved=None 表示等待中)
        """
        state = ConfirmationState(approved=None, payload=payload)
        self._states[payload.confirmation_id] = state
        logger.info(
            "ConfirmationService: registered %s for %s on table=%s",
            payload.confirmation_id,
            payload.operation,
            payload.metadata.get("table_name", "unknown"),
        )
        return state

    def resolve(self, confirmation_id: str, approved: bool) -> ConfirmationState | None:
        """
        处理用户确认/取消

        Args:
            confirmation_id: 确认ID
            approved: True=确认执行, False=取消操作

        Returns:
            更新后的 ConfirmationState，不存在则返回 None
        """
        state = self._states.get(confirmation_id)
        if state is None:
            logger.warning("ConfirmationService: resolve called on unknown id=%s", confirmation_id)
            return None

        state.approved = approved
        state.resolved_at = timestamp_now()
        logger.info(
            "ConfirmationService: resolved %s → %s",
            confirmation_id,
            "APPROVED" if approved else "CANCELLED",
        )
        return state

    def get(self, confirmation_id: str) -> ConfirmationState | None:
        """
        查询确认状态

        Args:
            confirmation_id: 确认ID

        Returns:
            ConfirmationState 或 None（不存在/已过期）
        """
        return self._states.get(confirmation_id)

    # ── 便捷方法 ──────────────────────────────────────

    def is_confirmed(self, confirmation_id: str) -> bool:
        """判断是否已确认"""
        state = self.get(confirmation_id)
        return state is not None and state.approved is True

    def is_cancelled(self, confirmation_id: str) -> bool:
        """判断是否已取消"""
        state = self.get(confirmation_id)
        return state is not None and state.approved is False

    # ============================================================
    # @REAL_CODE: 超时自动取消机制
    # 当前状态: 无超时自动处理（依赖 ConfirmationMiddleware 的 Future timeout）
    # 目标实现: 定时扫描 _states，将超过 timeout 的待确认项自动 resolve 为 cancelled
    # 对接服务: asyncio.create_task 后台定时器
    # 参考文档: 中断式确认机制调研.docx → 超时策略
    # 优先级: MEDIUM
    # ============================================================
    async def cleanup_expired(self) -> int:
        """
        清理过期的待确认请求（当前为占位方法）
        ⚠️ 需要实现真实的超时扫描逻辑
        """
        # TODO: @REAL_CODE — 扫描 _states，将超时项自动 resolve 为 False
        # from datetime import datetime, timezone, timedelta
        # now = datetime.now(timezone.utc)
        # expired = []
        # for cid, state in self._states.items():
        #     if state.approved is not None:
        #         continue
        #     created = datetime.fromisoformat(state.created_at)
        #     if (now - created).total_seconds() > self._timeout:
        #         expired.append(cid)
        # for cid in expired:
        #     self.resolve(cid, False)
        # return len(expired)
        return 0

    # ── 统计 ──────────────────────────────────────────

    @property
    def pending_count(self) -> int:
        """待确认数量"""
        return sum(1 for s in self._states.values() if s.approved is None)

    @property
    def total_count(self) -> int:
        """总确认数"""
        return len(self._states)
