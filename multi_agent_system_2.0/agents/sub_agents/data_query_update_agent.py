from __future__ import annotations

from core.agent_base import AgentBase, AgentContext
from core.confirmation_service import ConfirmationService
from core.guardrails import Guardrails
from core.models import AgentResult
from core.query_service import QueryService


class DataQueryUpdateAgent(AgentBase):
    agent_name = "data_query_update_agent"
    subsystem = "data"

    def __init__(self, deps, confirmation_service: ConfirmationService, query_service: QueryService, guardrails: Guardrails) -> None:
        super().__init__(deps)
        self.confirmation_service = confirmation_service
        self.query_service = query_service
        self.guardrails = guardrails

    def run(self, context: AgentContext) -> AgentResult:
        auth = self.deps.auth_manager.authorize(context.user_id, self.subsystem)
        if not auth.allowed:
            return AgentResult(status="error", agent_name=self.agent_name, summary=auth.reason)

        plan = self.query_service.build_plan(context.query)
        trace = ["authorized", f"sql:{plan.operation}"]
        hidden_fields = set(auth.hidden_fields)
        preview_rows = [
            {key: value for key, value in row.items() if key not in hidden_fields}
            for row in plan.preview_rows
        ]

        if plan.operation != "SELECT":
            payload = self.guardrails.build_confirmation_payload(
                operation=plan.operation,
                summary="检测到写操作，等待用户确认后执行。",
                sql=plan.sql,
                preview_rows=preview_rows,
            )
            self.confirmation_service.request(payload)
            return AgentResult(
                status="confirmation_required",
                agent_name=self.agent_name,
                summary="已生成改数预览，等待确认。",
                table_preview=preview_rows,
                confirmation_required=True,
                events=[self.event("write confirmation requested", "confirmation")],
                trace=trace,
                confirmation_payload=payload,
            )

        return AgentResult(
            status="success",
            agent_name=self.agent_name,
            summary="数据查询完成。",
            data={"sql": plan.sql},
            table_preview=preview_rows,
            events=[self.event("query executed")],
            trace=trace,
        )
