from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.guardrails import Guardrails


@dataclass(slots=True)
class QueryPlan:
    sql: str
    operation: str
    preview_rows: list[dict[str, Any]]
    result_rows: list[dict[str, Any]]


class QueryService:
    def __init__(self, guardrails: Guardrails) -> None:
        self.guardrails = guardrails

    def build_plan(self, query: str) -> QueryPlan:
        lowered = query.lower()
        if self.guardrails.detect_write_intent(query):
            sql = "UPDATE status_table SET status = '终止' WHERE status = '运行中';"
            preview = [
                {"id": 1, "status_before": "运行中", "status_after": "终止"},
                {"id": 2, "status_before": "运行中", "status_after": "终止"},
            ]
            return QueryPlan(sql=sql, operation="UPDATE", preview_rows=preview, result_rows=preview)

        if "sales" in lowered or "销售" in query:
            rows = [
                {"month": "2026-05", "region": "East", "amount": 125000, "report_version": "202605-EAST-A12"},
                {"month": "2026-05", "region": "West", "amount": 118000, "report_version": "202605-WEST-A12"},
            ]
            return QueryPlan(
                sql="SELECT month, region, amount, report_version FROM sales_table WHERE month = '2026-05';",
                operation="SELECT",
                preview_rows=rows,
                result_rows=rows,
            )

        rows = [
            {"id": 1, "status": "运行中", "owner": "Alice", "updated_at": "2026-06-29"},
            {"id": 2, "status": "已完成", "owner": "Bob", "updated_at": "2026-06-28"},
        ]
        return QueryPlan(
            sql="SELECT id, status, owner, updated_at FROM status_table LIMIT 5;",
            operation="SELECT",
            preview_rows=rows,
            result_rows=rows,
        )
