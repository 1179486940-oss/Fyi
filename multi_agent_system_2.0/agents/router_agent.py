from __future__ import annotations

from dataclasses import asdict

from agents.sub_agents.data_graph_agent import DataGraphAgent
from agents.sub_agents.data_query_update_agent import DataQueryUpdateAgent
from agents.sub_agents.data_report_agent import DataReportAgent
from agents.sub_agents.fallback_agent import FallbackAgent
from agents.sub_agents.ppt_generate_agent import PPTGenerateAgent
from core.agent_base import AgentContext, AgentDependencies
from core.confirmation_service import ConfirmationService
from core.guardrails import Guardrails
from core.llm_provider import LLMProvider
from core.memory_manager import MemoryManager
from core.query_service import QueryService
from core.session_manager import SessionManager
from core.auth_manager import AuthManager
from core.knowledge_manager import KnowledgeManager
from core.models import AgentEvent, AgentResult, RouterState, RouterTask


class RouterAgent:
    def __init__(self) -> None:
        self.llm_provider = LLMProvider()
        self.session_manager = SessionManager()
        self.memory_manager = MemoryManager()
        self.knowledge_manager = KnowledgeManager()
        self.auth_manager = AuthManager()
        self.guardrails = Guardrails()
        self.confirmation_service = ConfirmationService()
        self.query_service = QueryService(self.guardrails)
        self.deps = AgentDependencies(
            llm_provider=self.llm_provider,
            session_manager=self.session_manager,
            memory_manager=self.memory_manager,
            knowledge_manager=self.knowledge_manager,
            auth_manager=self.auth_manager,
        )
        self.agent_map = {
            "data_query_update": DataQueryUpdateAgent(self.deps, self.confirmation_service, self.query_service, self.guardrails),
            "data_graph": DataGraphAgent(self.deps),
            "data_report": DataReportAgent(self.deps),
            "ppt_generate": PPTGenerateAgent(self.deps),
            "fallback": FallbackAgent(self.deps),
        }

    def _normalize_query(self, query: str, multimodal_context: str) -> str:
        if not multimodal_context:
            return query
        return f"{query}\n\n[Multimodal Context]\n{multimodal_context}"

    def _plan_tasks(self, query: str) -> list[RouterTask]:
        lowered = query.lower()
        tasks: list[RouterTask] = []
        if any(token in lowered for token in ["查", "query", "update", "delete", "insert", "状态", "销售"]):
            tasks.append(RouterTask(agent_name="data_query_update", user_query=query))
        if any(token in lowered for token in ["图", "chart", "plot", "折线", "柱状"]):
            tasks.append(RouterTask(agent_name="data_graph", user_query=query, dependency_on="data_query_update" if tasks else None))
        if any(token in lowered for token in ["报表", "excel", "report"]):
            tasks.append(RouterTask(agent_name="data_report", user_query=query, dependency_on="data_query_update" if tasks else None))
        if "ppt" in lowered:
            dependency = tasks[-1].agent_name if tasks else None
            tasks.append(RouterTask(agent_name="ppt_generate", user_query=query, dependency_on=dependency))
        if not tasks:
            tasks.append(RouterTask(agent_name="fallback", user_query=query))
        return tasks

    def handle(self, session_id: str, user_id: str, query: str, attachments: list[str] | None = None) -> dict:
        attachments = attachments or []
        multimodal_context = self.llm_provider.multimodal_extract(attachments)
        normalized_query = self._normalize_query(query, multimodal_context)
        state = RouterState(session_id=session_id, user_id=user_id, query=query, normalized_query=normalized_query, multimodal_context=multimodal_context)
        memory_decision = self.memory_manager.detect_memory_action(query)
        if memory_decision.action == "write":
            record = self.memory_manager.write_long_term_memory(session_id, query, memory_decision.matched_keyword)
            state.events.append(AgentEvent(type="trace", message=f"memory stored: {record.key}"))
        elif memory_decision.action == "delete":
            removed = self.memory_manager.delete_last_long_term_memory(session_id)
            state.events.append(AgentEvent(type="trace", message=f"memory removed: {removed.key if removed else 'none'}"))

        checkpoint_id = self.session_manager.create_checkpoint(state)
        state.checkpoints.append(checkpoint_id)

        guardrail = self.guardrails.evaluate_query(query)
        if guardrail.requires_clarification:
            result = AgentResult(
                status="clarification_required",
                agent_name="router_agent",
                summary=guardrail.clarification_message,
                clarification_required=True,
                events=[AgentEvent(type="clarification", message=guardrail.clarification_message)],
                trace=["clarification"],
            )
            return asdict(result)

        state.planned_tasks = self._plan_tasks(query)
        outputs = []
        for task in state.planned_tasks:
            agent = self.agent_map[task.agent_name]
            context = AgentContext(session_id=session_id, user_id=user_id, query=task.user_query, multimodal_context=multimodal_context)
            outputs.append(agent.run(context))

        summary = " | ".join(output.summary for output in outputs)
        return {
            "status": "success",
            "checkpoint_id": checkpoint_id,
            "planned_tasks": [asdict(task) for task in state.planned_tasks],
            "results": [asdict(output) for output in outputs],
            "summary": summary,
        }
