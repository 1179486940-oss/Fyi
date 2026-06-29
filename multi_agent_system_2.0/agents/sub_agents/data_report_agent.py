from __future__ import annotations

from core.agent_base import AgentBase, AgentContext
from core.models import AgentResult


class DataReportAgent(AgentBase):
    agent_name = "data_report_agent"
    subsystem = "report"

    def run(self, context: AgentContext) -> AgentResult:
        auth = self.deps.auth_manager.authorize(context.user_id, self.subsystem)
        if not auth.allowed:
            return AgentResult(status="error", agent_name=self.agent_name, summary=auth.reason)

        artifact = self.deps.llm_provider.create_artifact(
            artifact_type="excel",
            name="sales_report",
            content="Mock Excel report content",
        )
        return AgentResult(
            status="success",
            agent_name=self.agent_name,
            summary="报表已生成。",
            artifacts=[artifact],
            events=[self.event("report artifact created", "artifact_ready")],
            trace=["report"],
        )
