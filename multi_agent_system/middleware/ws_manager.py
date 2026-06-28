"""
WebSocket 管理器
- 连接池管理 ({session_id: websocket})
- 推送消息/确认卡片到前端
- asyncio.Future 挂起等待用户响应
- 唤醒机制（前端回调 → resolve）
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from utils.logger import get_logger
from utils.helpers import generate_confirm_id, timestamp_now

logger = get_logger(__name__)

# 确认超时时间（秒）
CONFIRMATION_TIMEOUT = 30


class PendingConfirmation:
    """一个待确认的请求"""
    def __init__(self, confirm_id: str, payload: dict):
        self.confirm_id = confirm_id
        self.payload = payload
        self.created_at = timestamp_now()
        self.future: asyncio.Future = asyncio.get_event_loop().create_future()

    def resolve(self, response: dict) -> None:
        """前端回调，唤醒挂起的 Future"""
        if not self.future.done():
            self.future.set_result(response)

    def cancel(self) -> None:
        """取消（超时或前端拒绝）"""
        if not self.future.done():
            self.future.set_result({"status": "timeout"})


class WebSocketManager:
    """WebSocket 连接与确认管理"""

    def __init__(self):
        # session_id → websocket
        self._connections: dict[str, Any] = {}

        # confirm_id → PendingConfirmation
        self._pending_confirmations: dict[str, PendingConfirmation] = {}

        # 心跳任务
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ── 连接管理 ────────────────────────────────────────

    async def connect(self, session_id: str, websocket: Any) -> None:
        """注册 WebSocket 连接"""
        # 关闭旧连接
        old = self._connections.get(session_id)
        if old:
            try:
                await old.close()
            except Exception:
                pass

        self._connections[session_id] = websocket
        logger.info("WebSocket connected: session=%s (total=%d)",
                     session_id, len(self._connections))

    async def disconnect(self, session_id: str) -> None:
        """注销 WebSocket 连接"""
        ws = self._connections.pop(session_id, None)
        if ws:
            try:
                await ws.close()
            except Exception:
                pass

        # 清理该 session 的所有待确认
        to_remove = [
            cid for cid, pc in self._pending_confirmations.items()
            if pc.payload.get("session_id") == session_id
        ]
        for cid in to_remove:
            self._pending_confirmations[cid].cancel()
            del self._pending_confirmations[cid]

        logger.info("WebSocket disconnected: session=%s", session_id)

    def is_connected(self, session_id: str) -> bool:
        return session_id in self._connections

    # ── 推送 ────────────────────────────────────────────

    async def push_to_user(self, session_id: str, payload: dict) -> bool:
        """
        推送消息到前端
        Returns:
            True 推送成功；False 连接不存在
        """
        ws = self._connections.get(session_id)
        if not ws:
            logger.warning("push_to_user failed: session=%s not connected", session_id)
            return False

        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
            logger.debug("Pushed to session=%s, type=%s", session_id, payload.get("type"))
            return True
        except Exception as e:
            logger.error("Push to session=%s failed: %s", session_id, e)
            await self.disconnect(session_id)
            return False

    # ── 确认断点 ────────────────────────────────────────

    async def request_confirmation(
        self,
        session_id: str,
        operation_type: str,
        table: str,
        affected_data: list[dict],
        changes: dict,
        timeout: int = CONFIRMATION_TIMEOUT,
    ) -> dict:
        """
        发送确认弹窗并挂起等待用户响应

        Args:
            session_id: 会话ID
            operation_type: 操作类型 (INSERT / UPDATE / DELETE)
            table: 表名
            affected_data: 受影响的数据（用于展示）
            changes: 变更内容
            timeout: 超时秒数

        Returns:
            {"status": "confirmed" | "cancelled" | "timeout"}
        """
        confirm_id = generate_confirm_id()

        # 构造前端弹窗 payload
        payload = {
            "type": "confirmation_request",
            "confirm_id": confirm_id,
            "session_id": session_id,
            "operation": operation_type,
            "table": table,
            "affected_data": self._format_affected_data(affected_data),
            "changes": changes,
            "timestamp": timestamp_now(),
        }

        # 创建待确认对象
        pending = PendingConfirmation(confirm_id, payload)
        self._pending_confirmations[confirm_id] = pending

        # 推送到前端
        pushed = await self.push_to_user(session_id, payload)
        if not pushed:
            del self._pending_confirmations[confirm_id]
            return {"status": "cancelled", "reason": "push_failed"}

        # 挂起等待
        try:
            result = await asyncio.wait_for(pending.future, timeout=timeout)
            logger.info("Confirmation %s resolved: %s", confirm_id, result.get("status"))
            return result
        except asyncio.TimeoutError:
            pending.cancel()
            logger.warning("Confirmation %s timeout", confirm_id)
            return {"status": "timeout"}
        finally:
            self._pending_confirmations.pop(confirm_id, None)

    def resolve_confirmation(self, confirm_id: str, response: dict) -> bool:
        """
        前端确认回调入口
        response: {"status": "confirmed" | "cancelled", ...}
        Returns: True 成功唤醒；False 找不到对应 Future
        """
        pending = self._pending_confirmations.get(confirm_id)
        if not pending:
            logger.warning("resolve_confirmation: unknown confirm_id=%s", confirm_id)
            return False

        pending.resolve(response)
        logger.info("Confirmation %s resolved by user: %s", confirm_id, response.get("status"))
        return True

    # ── 流式消息推送 ────────────────────────────────────

    async def push_stream_chunk(
        self,
        session_id: str,
        content: str,
        is_clarification: bool = False,
        is_final: bool = False,
    ) -> bool:
        """推送流式内容块"""
        payload = {
            "type": "stream_chunk",
            "session_id": session_id,
            "content": content,
            "is_final": is_final,
            "__needs_clarification__": is_clarification,
            "timestamp": timestamp_now(),
        }
        return await self.push_to_user(session_id, payload)

    async def push_error(self, session_id: str, error_message: str) -> bool:
        """推送错误消息"""
        payload = {
            "type": "error",
            "session_id": session_id,
            "content": error_message,
            "timestamp": timestamp_now(),
        }
        return await self.push_to_user(session_id, payload)

    # ── 工具方法 ────────────────────────────────────────

    def _format_affected_data(self, data: list[dict], max_rows: int = 5) -> list[dict]:
        """
        格式化受影响数据用于前端展示
        - 批量修改只展示要变更的字段 + 索引字段
        - 超过 max_rows 条只显示示例
        """
        if not data:
            return []

        # 只展示前几条作为示例
        preview = data[:max_rows]
        return preview

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def pending_count(self) -> int:
        return len(self._pending_confirmations)


# 全局单例
_ws_manager: Optional[WebSocketManager] = None


def get_ws_manager() -> WebSocketManager:
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager
