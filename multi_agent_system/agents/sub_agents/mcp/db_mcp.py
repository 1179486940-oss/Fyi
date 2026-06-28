"""
MCP: 数据库操作
封装 PostgreSQL 的查询与写操作
"""

from __future__ import annotations

from typing import Any, Optional

from config import get_settings
from utils.logger import get_logger
from utils.helpers import is_write_operation, dict_to_table_preview, dict_to_full_table

logger = get_logger(__name__)


class DatabaseMCP:
    """数据库操作 MCP Server"""

    def __init__(self):
        self._pool = None
        self._settings = get_settings().database

    async def _get_pool(self):
        """获取数据库连接池（懒加载）"""
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                host=self._settings.host,
                port=self._settings.port,
                database=self._settings.name,
                user=self._settings.user,
                password=self._settings.password,
                min_size=self._settings.pool_min,
                max_size=self._settings.pool_max,
            )
            logger.info("DB pool created: %s:%d/%s",
                         self._settings.host, self._settings.port, self._settings.name)
        return self._pool

    # ── 查询 ─────────────────────────────────────────────

    async def execute_query(
        self,
        sql: str,
        max_preview_fields: int = 5,
    ) -> dict[str, Any]:
        """
        执行 SELECT 查询
        Returns:
            {"columns": [...], "rows": [...], "row_count": N,
             "preview": "表格文本预览", "preview_fields": N}
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            try:
                records = await conn.fetch(sql)
            except Exception as e:
                logger.error("Query failed: %s — %s", sql[:100], e)
                return {"error": str(e), "rows": [], "row_count": 0}

        columns = list(records[0].keys()) if records else []
        rows = [dict(r) for r in records]

        logger.info("Query executed: %d rows, %s", len(rows), sql[:80])
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "preview": dict_to_table_preview(rows, max_fields=max_preview_fields),
            "full_table": dict_to_full_table(rows),
            "preview_fields": max_preview_fields,
        }

    # ── 写操作 ──────────────────────────────────────────

    async def execute_write(self, sql: str) -> dict[str, Any]:
        """
        执行 INSERT / UPDATE / DELETE
        注意：调用方负责在调用前进行确认断点检查
        """
        if not is_write_operation(sql):
            return {"error": "Not a write operation", "status": "rejected"}

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            try:
                result = await conn.execute(sql)
                # 获取影响行数（从 SQL 执行结果字符串解析）
                row_count = int(result.split()[-1]) if result else 0
                logger.info("Write executed: %d rows affected", row_count)
                return {
                    "status": "success",
                    "rows_affected": row_count,
                    "message": result,
                }
            except Exception as e:
                logger.error("Write failed: %s — %s", sql[:100], e)
                return {"error": str(e), "status": "failed"}

    # ── 表结构 ──────────────────────────────────────────

    async def get_table_schema(self, table_name: str) -> list[dict]:
        """获取指定表的字段结构"""
        sql = f"""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
            ORDER BY ordinal_position
        """
        result = await self.execute_query(sql, max_preview_fields=100)
        return result.get("rows", [])

    async def list_tables(self) -> list[str]:
        """列出所有表"""
        sql = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
        result = await self.execute_query(sql, max_preview_fields=1)
        return [r["table_name"] for r in result.get("rows", [])]

    # ── 模拟 / Mock ──────────────────────────────────────

    async def mock_execute(self, sql: str) -> dict[str, Any]:
        """
        Mock 模式：不连接真实数据库，返回模拟数据
        用于开发阶段
        """
        if is_write_operation(sql):
            return {"status": "success", "rows_affected": 1, "message": "Mock write executed"}

        return {
            "columns": ["id", "name", "status", "created_at", "updated_at"],
            "rows": [
                {"id": 1, "name": "示例数据A", "status": "运行中", "created_at": "2026-06-01", "updated_at": "2026-06-28"},
                {"id": 2, "name": "示例数据B", "status": "已完成", "created_at": "2026-06-15", "updated_at": "2026-06-27"},
                {"id": 3, "name": "示例数据C", "status": "待处理", "created_at": "2026-06-20", "updated_at": "2026-06-25"},
            ],
            "row_count": 3,
            "preview": dict_to_table_preview([
                {"id": 1, "name": "示例数据A", "status": "运行中", "created_at": "2026-06-01", "updated_at": "2026-06-28"},
            ], max_fields=5),
            "full_table": dict_to_full_table([
                {"id": 1, "name": "示例数据A", "status": "运行中", "created_at": "2026-06-01", "updated_at": "2026-06-28"},
                {"id": 2, "name": "示例数据B", "status": "已完成", "created_at": "2026-06-15", "updated_at": "2026-06-27"},
            ]),
            "preview_fields": 5,
        }
