from __future__ import annotations

from core.agent_base import AgentBase, AgentContext
from core.models import AgentResult


class FallbackAgent(AgentBase):
    agent_name = "fallback_agent"
    subsystem = "fallback"

    def run(self, context: AgentContext) -> AgentResult:
        chunks = self.deps.knowledge_manager.retrieve("business", top_k=3)
        summary = "兜底知识问答已完成。"
        return AgentResult(
            status="success",
            agent_name=self.agent_name,
            summary=summary,
            data={"knowledge": [chunk.content for chunk in chunks]},
            events=[self.event("fallback knowledge retrieved")],
            trace=["fallback"],
        )
