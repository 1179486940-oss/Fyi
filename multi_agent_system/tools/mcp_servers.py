"""
MCP Server 注册中心
统一管理所有 MCP Server 的生命周期和调用
"""

from __future__ import annotations

from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class MCPServerRegistry:
    """MCP Server 注册中心"""

    def __init__(self):
        self._servers: dict[str, Any] = {}

    def register(self, name: str, server: Any) -> None:
        """注册一个 MCP Server"""
        self._servers[name] = server
        logger.info("MCP Server registered: %s", name)

    def get(self, name: str) -> Optional[Any]:
        """获取已注册的 MCP Server"""
        return self._servers.get(name)

    def unregister(self, name: str) -> None:
        """注销 MCP Server"""
        if name in self._servers:
            del self._servers[name]
            logger.info("MCP Server unregistered: %s", name)

    @property
    def registered_names(self) -> list[str]:
        return list(self._servers.keys())


# 全局单例
_registry: Optional[MCPServerRegistry] = None


def get_mcp_registry() -> MCPServerRegistry:
    global _registry
    if _registry is None:
        _registry = MCPServerRegistry()
    return _registry


def register_mcp_server(name: str) -> callable:
    """装饰器：自动注册 MCP Server"""
    def decorator(cls):
        registry = get_mcp_registry()
        instance = cls()
        registry.register(name, instance)
        return cls
    return decorator
