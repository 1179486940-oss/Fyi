"""
鉴权管理模块
- SSO 鉴权抽象（已集成 DECO 平台）
- 数据鉴权 MCP 调用封装
- 敏感字段过滤
"""

from __future__ import annotations

from typing import Optional

from config import get_settings
from core.session_manager import Session, get_session_manager
from utils.logger import get_logger

logger = get_logger(__name__)


class AuthManager:
    """鉴权管理器"""

    def __init__(self):
        settings = get_settings()
        self._sensitive_fields = settings.sensitive_fields
        self._session_manager = get_session_manager()

    # ── 子系统权限检查 ──────────────────────────────────

    async def check_subsystem_permission(
        self,
        user_id: str,
        subsystem: str,
    ) -> bool:
        """
        检查用户对某个子系统的访问权限
        通过 SSO 登录时注入的 permissions 判断
        """
        # 开发环境默认全权限
        if get_settings().server.is_development:
            logger.debug("Dev mode: granting access to %s for %s", subsystem, user_id)
            return True

        # 正式环境：通过数据鉴权 MCP Server 调用
        try:
            return await self._call_auth_mcp(user_id, subsystem)
        except Exception as e:
            logger.error("Auth check failed for %s/%s: %s", user_id, subsystem, e)
            return False

    async def check_session_permission(
        self,
        session_id: str,
        subsystem: str,
    ) -> bool:
        """检查会话对某个子系统的权限"""
        return self._session_manager.has_permission(session_id, subsystem)

    # ── 数据字段级鉴权 ──────────────────────────────────

    def filter_sensitive_fields(
        self,
        records: list[dict],
        user_id: str,
        table: str,
    ) -> list[dict]:
        """
        根据用户权限过滤敏感字段
        无权限时移除 key1, key2, key3
        """
        if not records:
            return records

        # 开发环境不过滤
        if get_settings().server.is_development:
            return records

        # TODO: 接入真实鉴权 MCP 后替换此处逻辑
        has_full_access = True  # 默认有权限（开发阶段）
        if has_full_access:
            return records

        # 过滤敏感字段
        filtered = []
        for record in records:
            cleaned = {
                k: v for k, v in record.items()
                if k not in self._sensitive_fields
            }
            filtered.append(cleaned)

        logger.info("Filtered %d sensitive fields from %d records in %s",
                     len(self._sensitive_fields), len(records), table)
        return filtered

    def get_allowed_fields(self, user_id: str, table: str) -> Optional[list[str]]:
        """
        获取用户对某张表可访问的字段列表
        Returns:
            None 表示全字段可访问；list 表示限制的字段列表
        """
        # 开发环境全字段
        if get_settings().server.is_development:
            return None

        # TODO: 接入真实鉴权 MCP
        return None

    # ── 内部方法 ─────────────────────────────────────────

    async def _call_auth_mcp(self, user_id: str, subsystem: str) -> bool:
        """
        调用数据鉴权 MCP Server
        TODO: 对接真实 DECO 平台的 SSO 鉴权接口
        当前是 mock 实现
        """
        # Mock: 默认返回 True
        logger.debug("Auth MCP mock: user=%s, subsystem=%s → GRANTED", user_id, subsystem)
        return True


# 全局单例
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager
