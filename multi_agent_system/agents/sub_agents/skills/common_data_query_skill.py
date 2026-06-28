"""
Skill: Common_Data_Query
通用数据查询逻辑 —— 可被 Data_Graph_Agent 和 Data_Report_Agent 复用
检索数据KB → 鉴权 → Text2SQL → 返回数据（不含确认断点，查询专用）
"""

from __future__ import annotations

from typing import Any, Optional

from core.agent_base import BaseAgent
from utils.logger import get_logger

logger = get_logger(__name__)


class CommonDataQuery:
    """通用数据查询 Skill（可复用）"""

    def __init__(self, agent: BaseAgent):
        self.agent = agent
        self._km = agent._km
        self._llm = agent._llm
        self._auth = agent._auth

    async def query(
        self,
        natural_language_query: str,
        context: str = "",
        table_scope: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        执行自然语言数据查询
        Args:
            natural_language_query: 用户的自然语言查询
            context: 对话上下文
            table_scope: 限定数据表范围（可选）
        Returns:
            {"status": "success/error", "rows": [...], "columns": [...], "sql": "..."}
        """
        # Step 1: 检索数据KB（必检 top_k=1）
        db_chunks = await self._km.search("database", natural_language_query, top_k=1)
        db_context = "\n".join(c.content for c in db_chunks) if db_chunks else ""
        logger.debug("CommonDataQuery: retrieved %d DB chunks", len(db_chunks))

        # Step 2: 鉴权
        from agents.sub_agents.mcp.auth_mcp import AuthMCP
        auth_mcp = AuthMCP()
        has_access = await auth_mcp.check_data_permission(
            self.agent.user_id, "data_subsystem"
        )
        if not has_access:
            return {"status": "error", "content": "⚠️ 无数据访问权限"}

        # Step 3: 生成 SQL
        full_context = f"【数据库结构】\n{db_context}\n\n{context}"
        if table_scope:
            full_context += f"\n限定查询表范围：{table_scope}"

        sql = await self._generate_sql(natural_language_query, full_context)
        if not sql:
            return {"status": "error", "content": "无法生成有效的 SQL 查询"}

        # Step 4: 执行查询
        from agents.sub_agents.mcp.db_mcp import DatabaseMCP
        db_mcp = DatabaseMCP()

        result = await db_mcp.execute_query(sql)
        logger.info("CommonDataQuery: SQL executed, %d rows", result.get("row_count", 0))

        return {
            "status": "success",
            "rows": result.get("rows", []),
            "columns": result.get("columns", []),
            "row_count": result.get("row_count", 0),
            "sql": sql,
        }

    async def _generate_sql(self, query: str, context: str) -> str:
        """LLM 生成 SQL"""
        prompt = f"""根据数据库信息和用户提问，生成正确的 SELECT SQL 语句。

{context}

用户提问：{query}

要求：只返回一条 SELECT SQL 语句，不要任何解释。无法生成返回 CANNOT_GENERATE。"""
        try:
            sql = await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            return sql.strip().strip("`").strip("```sql").strip("```").strip()
        except Exception as e:
            logger.error("SQL generation error: %s", e)
            return ""
