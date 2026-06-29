from __future__ import annotations

from core.agent_base import AgentBase, AgentContext
from core.models import AgentResult


class DataGraphAgent(AgentBase):
    agent_name = "data_graph_agent"
    subsystem = "graph"

    def run(self, context: AgentContext) -> AgentResult:
        auth = self.deps.auth_manager.authorize(context.user_id, self.subsystem)
        if not auth.allowed:
            return AgentResult(status="error", agent_name=self.agent_name, summary=auth.reason)

        artifact = self.deps.llm_provider.create_artifact(
            artifact_type="html",
            name="sales_chart",
            content="<html><body><h1>Mock Sales Chart</h1></body></html>",
        )
        return AgentResult(
            status="success",
            agent_name=self.agent_name,
            summary="图表已生成。",
            artifacts=[artifact],
            events=[self.event("graph artifact created", "artifact_ready")],
            trace=["graph"],
        )
