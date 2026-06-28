"""
确认断点中间件（方案 A + C 组合）
- 子 Agent 内部调用：_breakpoint_confirm()
- 中间件层拦截：ConfirmationMiddleware.intercept()
- 对所有写操作（INSERT/UPDATE/DELETE）自动拦截
"""

from __future__ import annotations

from typing import Any, Optional

from middleware.ws_manager import get_ws_manager
from utils.logger import get_logger
from utils.helpers import timestamp_now

logger = get_logger(__name__)


class ConfirmationResult:
    """确认断点返回结果"""
    def __init__(self, status: str, reason: str = ""):
        self.status = status          # "confirmed" | "cancelled" | "timeout"
        self.reason = reason
        self.timestamp = timestamp_now()

    @property
    def is_confirmed(self) -> bool:
        return self.status == "confirmed"

    @property
    def is_cancelled(self) -> bool:
        return self.status in ("cancelled", "timeout")

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class ConfirmationMiddleware:
    """
    确认断点中间件
    - 统一拦截所有写操作的确认逻辑
    - 子 Agent 通过此中间件触发确认断点
    """

    def __init__(self, timeout: int = 30):
        self._timeout = timeout
        self._ws = get_ws_manager()

    async def intercept(
        self,
        operation_type: str,
        table: str,
        affected_data: list[dict],
        changes: dict,
        session_id: str,
        timeout: Optional[int] = None,
    ) -> ConfirmationResult:
        """
        拦截写操作，等待用户确认

        Args:
            operation_type: "INSERT" / "UPDATE" / "DELETE"
            table: 目标表名
            affected_data: SELECT 查到的受影响的原始数据
            changes: 将要变更的字段及新值
            session_id: 会话ID
            timeout: 超时秒数（默认30）

        Returns:
            ConfirmationResult
        """
        timeout = timeout or self._timeout

        logger.info(
            "Confirmation intercept: %s on %s (session=%s, timeout=%ds)",
            operation_type, table, session_id, timeout,
        )

        result = await self._ws.request_confirmation(
            session_id=session_id,
            operation_type=operation_type,
            table=table,
            affected_data=affected_data,
            changes=changes,
            timeout=timeout,
        )

        status = result.get("status", "timeout")
        reason = result.get("reason", "")

        if status == "confirmed":
            logger.info("Confirmation APPROVED: %s on %s", operation_type, table)
        else:
            logger.info("Confirmation REJECTED: %s on %s (status=%s, reason=%s)",
                         operation_type, table, status, reason)

        return ConfirmationResult(status=status, reason=reason)

    # ── 便捷方法（供子 Agent 内部调用）────────────────────

    async def confirm_update(
        self,
        table: str,
        affected_data: list[dict],
        changes: dict,
        session_id: str,
    ) -> ConfirmationResult:
        """确认 UPDATE 操作"""
        return await self.intercept("UPDATE", table, affected_data, changes, session_id)

    async def confirm_insert(
        self,
        table: str,
        new_data: list[dict],
        session_id: str,
    ) -> ConfirmationResult:
        """确认 INSERT 操作"""
        return await self.intercept("INSERT", table, [], {"new_data": new_data}, session_id)

    async def confirm_delete(
        self,
        table: str,
        affected_data: list[dict],
        session_id: str,
    ) -> ConfirmationResult:
        """确认 DELETE 操作"""
        return await self.intercept("DELETE", table, affected_data, {}, session_id)


# 全局单例
_confirmation_middleware: Optional[ConfirmationMiddleware] = None


def get_confirmation_middleware() -> ConfirmationMiddleware:
    global _confirmation_middleware
    if _confirmation_middleware is None:
        from config import get_settings
        timeout = get_settings().confirmation_timeout
        _confirmation_middleware = ConfirmationMiddleware(timeout=timeout)
    return _confirmation_middleware
