from __future__ import annotations

from core.agent_base import AgentBase, AgentContext
from core.models import AgentResult


class PPTGenerateAgent(AgentBase):
    agent_name = "ppt_generate_agent"
    subsystem = "ppt"

    def run(self, context: AgentContext) -> AgentResult:
        auth = self.deps.auth_manager.authorize(context.user_id, self.subsystem)
        if not auth.allowed:
            return AgentResult(status="error", agent_name=self.agent_name, summary=auth.reason)

        artifact = self.deps.llm_provider.create_artifact(
            artifact_type="ppt",
            name="business_presentation",
            content="Mock PPT binary placeholder",
        )
        return AgentResult(
            status="success",
            agent_name=self.agent_name,
            summary="PPT 已生成。",
            artifacts=[artifact],
            events=[self.event("ppt artifact created", "artifact_ready")],
            trace=["ppt"],
        )
