"""
Skill: Comment_Data_Process
处理 Comment 数据表的增删改查流程
结构同 NSG_Borrow_Data_Process，但针对 Comment 数据表
"""

from __future__ import annotations

from typing import Any

from core.agent_base import BaseAgent
from core.knowledge_manager import KBChunk
from utils.logger import get_logger
from utils.helpers import is_write_operation

logger = get_logger(__name__)


class CommentDataProcess:
    """Comment 数据流程 Skill"""

    def __init__(self, agent: BaseAgent):
        self.agent = agent
        self._km = agent._km
        self._memory = agent._memory
        self._auth = agent._auth
        self._confirm = agent._confirm

    async def execute(self, query: str, context: str) -> dict[str, Any]:
        """
        执行 Comment 数据流程
        同 NSG_Borrow_Data_Process 的模块一~三、五，针对 Comment 数据表
        """

        # 模块一：检索数据KB（必检）
        db_chunks = await self._km.search("database", query, top_k=1)
        db_context = "\n".join(c.content for c in db_chunks) if db_chunks else ""

        # 模块二：触发关键词检测
        extra_chunks: list[KBChunk] = []
        if self._memory.detect_longterm_memory_trigger(query):
            lt_chunks = await self._km.search("longterm_memory", query, top_k=3)
            fb_chunks = await self._km.search("feedback", query, top_k=3)
            extra_chunks.extend(lt_chunks)
            extra_chunks.extend(fb_chunks)

        # 模块三：上下文拼接
        all_chunks = list(db_chunks) + extra_chunks
        full_context = self._km.assemble_context(all_chunks, context)
        if db_context:
            full_context = f"【评论数据表信息】\n{db_context}\n\n{full_context}"

        # 鉴权检查
        has_permission = await self._auth.check_subsystem_permission(
            self.agent.user_id, "data_query"
        )
        if not has_permission:
            return {
                "status": "error",
                "content": "⚠️ 没有数据子系统访问权限。",
            }

        # 模块五：Text2SQL + 确认断点
        sql = await self._generate_sql(query, full_context)
        if not sql:
            return {
                "status": "error",
                "content": "无法生成有效的 SQL，请补充具体查询条件。",
            }

        from agents.sub_agents.mcp.db_mcp import DatabaseMCP
        db_mcp = DatabaseMCP()

        if is_write_operation(sql):
            select_sql = self._build_select_for_confirm(sql)
            affected = []
            if select_sql:
                preview = await db_mcp.execute_query(select_sql)
                affected = preview.get("rows", [])

            confirmed = await self.agent._breakpoint_confirm(
                operation=self._detect_op(sql),
                table=self._extract_table(sql),
                found_data=affected,
                changes={"sql": sql},
            )
            if not confirmed:
                return {"status": "cancelled", "content": "❌ 操作已取消"}

            result = await db_mcp.execute_write(sql)
            response = f"✅ 操作成功\n{result.get('message', '')}"
        else:
            result = await db_mcp.execute_query(sql, max_preview_fields=5)
            preview = result.get("preview", "")
            total_cols = len(result.get("columns", []))
            hidden_note = ""
            if total_cols > 5:
                hidden_note = f"\n\n💡 共 {total_cols} 个字段，当前展示前 5 个。如需查看其他字段，请追问。"
            response = f"查询结果：\n\n{preview}{hidden_note}"

        thought = f"评论数据处理 → SQL: {sql[:200]}"
        return {
            "status": "success",
            "content": f"{self.agent.display_thought(thought)}\n\n{response}",
            "sql": sql,
            "data": result,
        }

    async def _generate_sql(self, query: str, context: str) -> str:
        prompt = f"""根据数据库信息和用户提问，生成正确的 SQL 语句。

数据库信息：
{context}

用户提问：{query}

要求：只返回 SQL，不要解释。无法生成时返回 CANNOT_GENERATE。"""
        try:
            sql = await self.agent._llm.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            return sql.strip().strip("`").strip("```sql").strip("```").strip()
        except Exception:
            return ""

    def _build_select_for_confirm(self, sql: str) -> str:
        import re
        sql_upper = sql.upper()
        if sql_upper.startswith("UPDATE"):
            match = re.search(r"UPDATE\s+(\w+)\s+SET\s+", sql_upper)
            where_match = re.search(r"WHERE\s+(.+)$", sql, re.IGNORECASE)
            if match:
                table = match.group(1)
                where = where_match.group(1) if where_match else "1=1"
                return f"SELECT * FROM {table} WHERE {where}"
        elif sql_upper.startswith("DELETE"):
            match = re.search(r"DELETE\s+FROM\s+(\w+)", sql_upper)
            where_match = re.search(r"WHERE\s+(.+)$", sql, re.IGNORECASE)
            if match:
                table = match.group(1)
                where = where_match.group(1) if where_match else "1=1"
                return f"SELECT * FROM {table} WHERE {where}"
        return ""

    def _detect_op(self, sql: str) -> str:
        sql_upper = sql.strip().upper()
        for op in ("INSERT", "UPDATE", "DELETE"):
            if sql_upper.startswith(op):
                return op
        return "UNKNOWN"

    def _extract_table(self, sql: str) -> str:
        import re
        match = re.search(r"(?:FROM|INTO|UPDATE)\s+(\w+)", sql, re.IGNORECASE)
        return match.group(1) if match else "unknown"
