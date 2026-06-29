"""
独立查询服务（从 v2 迁移增强）
将数据查询和 SQL 规划逻辑从 Agent 内部抽离，形成独立服务层。

职责:
  - 根据用户 query 生成 QueryPlan（SQL + 操作类型 + 预览数据）
  - 与 Guardrails 协作判断写操作意图
  - 为 Agent 提供统一的查询入口

来源: multi_agent_system_2.0/core/query_service.py
适配: v1 生产环境（对接真实 PostgreSQL + RAGFlow 数据KB）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.guardrails import get_guardrails
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class QueryPlan:
    """查询执行计划"""
    sql: str                                    # 生成的 SQL
    operation: str                              # SELECT / INSERT / UPDATE / DELETE
    preview_rows: list[dict[str, Any]]          # 预览数据（前 N 条）
    result_rows: list[dict[str, Any]]           # 完整结果（查询时）或受影响行预览（写操作时）
    table_name: str = ""                        # 目标表名
    total_count: int = 0                        # 总行数（查询时）

    # ============================================================
    # @REAL_CODE: 对接真实 Text2SQL 引擎
    # 当前状态: Mock SQL 生成（基于关键词匹配）
    # 目标实现: LLM 根据 RAGFlow 数据KB 返回的表结构 DDL 生成精确 SQL
    # 对接服务: LLM (deepseek-v4-pro) + RAGFlow 数据库KB
    # 参考文档: 设计手册.docx → Data_Query_Agent 章节 Text2SQL 部分
    # 优先级: HIGH
    # ============================================================


class QueryService:
    """
    查询服务
    负责 QueryPlan 的生成。v2 版为 mock 实现，v1 生产版需对接真实 LLM + DB。
    """

    def __init__(self):
        self._guardrails = get_guardrails()

    # ============================================================
    # @REAL_CODE: 构建基于 LLM 的 Text2SQL 查询计划
    # 当前状态: 基于关键词的简单 mock 分支
    # 目标实现:
    #   1. 从 RAGFlow 数据库KB 检索目标表 DDL (top_k=1)
    #   2. 将 表DDL + 用户Query → LLM 生成 SQL
    #   3. 判断 SQL 类型 (SELECT/UPDATE/INSERT/DELETE)
    #   4. 对写操作：先执行 SELECT 获取受影响数据预览
    #   5. 返回完整的 QueryPlan
    # 对接服务: LLM (deepseek-v4-pro) + RAGFlow (KB_DATABASE) + PostgreSQL
    # 参考文档: agent设计手册.docx → Data_Query_Agent 完整执行流程
    # 优先级: HIGH — 这是系统核心功能
    # ============================================================
    def build_plan(self, query: str) -> QueryPlan:
        """
        根据用户 query 生成查询计划

        ⚠️ 当前为 MOCK 实现，上线前必须替换为真实 Text2SQL + DB 查询。
        真实实现参考下方 @REAL_CODE 注释。
        """
        lowered = query.lower()

        # ── Mock: 写操作分支 ──
        if self._guardrails.detect_write_intent(query):  # type: ignore[attr-defined]
            # ============================================================
            # @REAL_CODE: 真实写操作处理流程
            # 当前: mock SQL + mock 预览数据
            # 目标:
            #   1. LLM 生成 UPDATE/INSERT/DELETE SQL
            #   2. 先执行 SELECT 获取受影响数据（用于确认弹窗预览）
            #   3. 将 SELECT 结果填入 preview_rows
            #   4. 实际写操作在用户确认后由 ConfirmationService 触发
            # 对接: PostgreSQL (asyncpg) + LLM Text2SQL
            # ============================================================
            sql = "UPDATE status_table SET status = '终止' WHERE status = '运行中';"
            preview = [
                {"id": 1, "status_before": "运行中", "status_after": "终止"},
                {"id": 2, "status_before": "运行中", "status_after": "终止"},
            ]
            return QueryPlan(
                sql=sql,
                operation="UPDATE",
                preview_rows=preview,
                result_rows=preview,
                table_name="status_table",
            )

        # ── Mock: 销售数据查询分支 ──
        if "sales" in lowered or "销售" in query:
            # ============================================================
            # @REAL_CODE: 真实销售数据查询
            # 当前: mock 返回固定数据
            # 目标:
            #   1. 从 RAGFlow 数据库KB 检索 sales 表 DDL
            #   2. LLM 根据 DDL + Query 生成精确 SELECT
            #   3. 执行 SQL → 获取真实数据
            #   4. 首次展示前5个字段 + 引导追问
            # 对接: PostgreSQL + RAGFlow 数据库KB + LLM
            # ============================================================
            rows = [
                {"month": "2026-05", "region": "East", "amount": 125000, "report_version": "202605-EAST-A12"},
                {"month": "2026-05", "region": "West", "amount": 118000, "report_version": "202605-WEST-A12"},
            ]
            return QueryPlan(
                sql="SELECT month, region, amount, report_version FROM sales_table WHERE month = '2026-05';",
                operation="SELECT",
                preview_rows=rows,
                result_rows=rows,
                table_name="sales_table",
                total_count=len(rows),
            )

        # ── Mock: 默认状态表查询分支 ──
        # ============================================================
        # @REAL_CODE: 真实通用查询
        # 当前: mock 返回固定状态表数据
        # 目标: 同销售数据查询流程
        # 对接: PostgreSQL + RAGFlow 数据库KB + LLM
        # ============================================================
        rows = [
            {"id": 1, "status": "运行中", "owner": "Alice", "updated_at": "2026-06-29"},
            {"id": 2, "status": "已完成", "owner": "Bob", "updated_at": "2026-06-28"},
        ]
        return QueryPlan(
            sql="SELECT id, status, owner, updated_at FROM status_table LIMIT 5;",
            operation="SELECT",
            preview_rows=rows,
            result_rows=rows,
            table_name="status_table",
            total_count=len(rows),
        )

    # ============================================================
    # @REAL_CODE: 执行真实的数据库查询
    # 当前状态: 未实现，QueryPlan 中的 result_rows 为 mock 数据
    # 目标实现: 使用 asyncpg 连接池执行 SQL，返回真实结果
    # 对接服务: PostgreSQL (DB_HOST/DB_PORT/DB_NAME)
    # 参考文档: mcp/db_mcp.py → execute_query()
    # 优先级: HIGH
    # ============================================================
    async def execute_query(self, sql: str) -> list[dict[str, Any]]:
        """
        执行真实数据库查询（当前为占位方法）
        ⚠️ 需要替换为 asyncpg 实现
        """
        # TODO: @REAL_CODE — 替换为真实 asyncpg 查询
        # from agents.sub_agents.mcp.db_mcp import DatabaseMCP
        # db = DatabaseMCP()
        # result = await db.execute_query(sql)
        # return result["rows"]
        logger.warning("QueryService.execute_query() called but no real DB connected (mock mode)")
        return []

    # ============================================================
    # @REAL_CODE: 执行真实的写操作（确认后调用）
    # 当前状态: 未实现
    # 目标实现: 使用 asyncpg 执行 INSERT/UPDATE/DELETE，返回影响行数
    # 对接服务: PostgreSQL
    # 参考文档: mcp/db_mcp.py → execute_write()
    # 优先级: HIGH
    # ============================================================
    async def execute_write(self, sql: str) -> dict[str, Any]:
        """
        执行真实写操作（当前为占位方法）
        ⚠️ 需要替换为 asyncpg 实现，且必须在用户确认后调用
        """
        # TODO: @REAL_CODE — 替换为真实 asyncpg 写操作
        # from agents.sub_agents.mcp.db_mcp import DatabaseMCP
        # db = DatabaseMCP()
        # result = await db.execute_write(sql)
        # return result
        logger.warning("QueryService.execute_write() called but no real DB connected (mock mode)")
        return {"status": "mock_success", "rows_affected": 0}
