"""
MCP: 数据鉴权
封装鉴权接口，判断用户数据访问权限
"""

from __future__ import annotations

from typing import Optional

from config import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


class AuthMCP:
    """数据鉴权 MCP Server"""

    def __init__(self):
        self._settings = get_settings()
        self._sensitive_fields = self._settings.sensitive_fields

    async def check_data_permission(
        self,
        user_id: str,
        data_subsystem: str,
    ) -> bool:
        """
        检查用户对某个数据子系统的访问权限
        TODO: 对接 BA 提供的数据鉴权接口
        """
        # 开发阶段 Mock：默认有权限
        if self._settings.server.is_development:
            return True

        # 正式环境调用真实鉴权接口
        return await self._call_auth_interface(user_id, data_subsystem)

    async def get_accessible_tables(
        self,
        user_id: str,
    ) -> list[str]:
        """
        获取用户可访问的数据表列表
        """
        # Mock: 返回全部表
        return ["*"]

    async def get_accessible_fields(
        self,
        user_id: str,
        table_name: str,
    ) -> Optional[list[str]]:
        """
        获取用户对某表的可访问字段
        Returns:
            None → 全字段可访问
            list[str] → 受限字段列表
        """
        # Mock: 返回 None 表示全字段可访问
        return None

    def filter_fields(
        self,
        records: list[dict],
        allowed_fields: Optional[list[str]],
    ) -> list[dict]:
        """
        根据权限过滤字段
        - allowed_fields 为 None → 全字段返回
        - 否则只返回 allowed_fields 中的字段
        """
        if allowed_fields is None:
            return records

        return [
            {k: v for k, v in r.items() if k in allowed_fields}
            for r in records
        ]

    def remove_sensitive_fields(self, records: list[dict]) -> list[dict]:
        """移除敏感字段（key1, key2, key3）"""
        return [
            {k: v for k, v in r.items() if k not in self._sensitive_fields}
            for r in records
        ]

    # ── 内部 ─────────────────────────────────────────────

    async def _call_auth_interface(self, user_id: str, subsystem: str) -> bool:
        """调用真实鉴权接口"""
        import httpx

        # TODO: 替换为真实接口地址
        url = f"{self._settings.llm.base_url}/auth/check"
        headers = {"Authorization": f"Bearer {self._settings.llm.api_key}"}
        payload = {"user_id": user_id, "subsystem": subsystem}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload, headers=headers)
                data = resp.json()
                return data.get("has_access", False)
        except Exception as e:
            logger.error("Auth interface call failed: %s", e)
            return False
