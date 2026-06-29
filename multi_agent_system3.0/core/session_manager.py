"""
会话管理与隔离
- Session 生命周期管理
- 存储后端：memory / sqlite / postgres
- 每个 session 独立隔离
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from config import get_settings
from utils.logger import get_logger
from utils.helpers import generate_uuid, timestamp_now

logger = get_logger(__name__)


@dataclass
class Session:
    """会话数据结构"""
    session_id: str
    user_id: str
    created_at: str = field(default_factory=timestamp_now)
    last_active_at: str = field(default_factory=timestamp_now)

    # 对话历史: [{"role": "user/assistant", "content": "..."}, ...]
    history: list[dict] = field(default_factory=list)

    # 用户权限（SSO 登录时注入）
    permissions: dict[str, bool] = field(default_factory=dict)

    # 上下文回溯：保存被清空前的历史
    archived_history: Optional[list[dict]] = None

    # 状态标记
    is_clarifying: bool = False         # 是否处于澄清状态
    is_waiting_confirmation: bool = False  # 是否在等待用户确认

    @property
    def history_text(self) -> str:
        """将历史对话转为文本，用于拼入 Prompt"""
        lines = []
        for msg in self.history[-30:]:  # 最多取 30 条
            role = msg.get("role", "user")
            content = msg.get("content", "")
            label = "用户" if role == "user" else "助手"
            lines.append(f"{label}: {content[:500]}")
        return "\n".join(lines)

    def add_message(self, role: str, content: str) -> None:
        """添加一条消息到历史"""
        self.history.append({"role": role, "content": content})
        self.last_active_at = timestamp_now()

        # 保持短期记忆窗口（10-15轮 = 20-30条消息）
        max_history = get_settings().session.max_history_rounds * 2
        if len(self.history) > max_history:
            self.history = self.history[-max_history:]

    def reset_context(self) -> None:
        """上下文回溯：清空对话历史（但存档以便恢复）"""
        self.archived_history = self.history.copy()
        self.history = []
        logger.info("Session %s: context reset (archived %d msgs)",
                     self.session_id, len(self.archived_history))

    def restore_context(self) -> bool:
        """恢复上下文：把存档的历史恢复到当前"""
        if not self.archived_history:
            return False
        self.history = self.archived_history
        self.archived_history = None
        logger.info("Session %s: context restored (%d msgs)",
                     self.session_id, len(self.history))
        return True

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "history_count": len(self.history),
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
        }


class SessionManager:
    """会话管理器"""

    def __init__(self):
        settings = get_settings()
        self._backend = settings.session.backend
        self._ttl = settings.session.ttl_seconds
        self._sessions: dict[str, Session] = {}
        logger.info("Session manager initialized: backend=%s, ttl=%ds",
                     self._backend, self._ttl)

    # ── CRUD ─────────────────────────────────────────

    def create_session(self, user_id: str, permissions: Optional[dict] = None) -> Session:
        """创建新会话"""
        session = Session(
            session_id=generate_uuid(),
            user_id=user_id,
            permissions=permissions or {},
        )
        self._sessions[session.session_id] = session
        logger.info("Session created: %s (user=%s)", session.session_id, user_id)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        session = self._sessions.get(session_id)
        if session is None:
            return None

        # 检查 TTL
        if self._is_expired(session):
            self._sessions.pop(session_id, None)
            return None

        session.last_active_at = timestamp_now()
        return session

    def get_or_create(self, session_id: Optional[str], user_id: str = "anonymous") -> Session:
        """获取会话，不存在则创建"""
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session
        return self.create_session(user_id)

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info("Session deleted: %s", session_id)
            return True
        return False

    def update_permissions(self, session_id: str, permissions: dict) -> bool:
        """更新用户权限"""
        session = self._sessions.get(session_id)
        if session:
            session.permissions = permissions
            return True
        return False

    def has_permission(self, session_id: str, subsystem: str) -> bool:
        """检查用户是否有某子系统的权限"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        return session.permissions.get(subsystem, False)

    # ── 工具 ─────────────────────────────────────────

    def _is_expired(self, session: Session) -> bool:
        """检查会话是否过期"""
        try:
            from datetime import datetime, timezone, timedelta
            last = datetime.fromisoformat(session.last_active_at)
            now = datetime.now(timezone.utc)
            return (now - last) > timedelta(seconds=self._ttl)
        except Exception:
            return False

    def cleanup_expired(self) -> int:
        """清理过期会话，返回清理数量"""
        expired_ids = [
            sid for sid, s in self._sessions.items()
            if self._is_expired(s)
        ]
        for sid in expired_ids:
            del self._sessions[sid]
        if expired_ids:
            logger.info("Cleaned up %d expired sessions", len(expired_ids))
        return len(expired_ids)


# 全局单例
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
