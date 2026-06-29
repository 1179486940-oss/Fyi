from __future__ import annotations

from core.agent_base import AgentContext, AgentDependencies
from core.auth_manager import AuthManager
from core.confirmation_service import ConfirmationService
from core.guardrails import Guardrails
from core.knowledge_manager import KnowledgeManager
from core.llm_provider import LLMProvider
from core.memory_manager import MemoryManager
from core.query_service import QueryService
from core.session_manager import SessionManager
from agents.sub_agents.data_query_update_agent import DataQueryUpdateAgent


def build_agent() -> DataQueryUpdateAgent:
    deps = AgentDependencies(
        llm_provider=LLMProvider(),
        session_manager=SessionManager(),
        memory_manager=MemoryManager(),
        knowledge_manager=KnowledgeManager(),
        auth_manager=AuthManager(),
    )
    guardrails = Guardrails()
    return DataQueryUpdateAgent(deps, ConfirmationService(), QueryService(guardrails), guardrails)


def test_query_agent_returns_select_preview() -> None:
    agent = build_agent()
    result = agent.run(AgentContext(session_id="s", user_id="demo-user", query="查询状态表"))
    assert result.status == "success"
    assert len(result.table_preview) > 0


def test_query_agent_requires_confirmation_for_write() -> None:
    agent = build_agent()
    result = agent.run(AgentContext(session_id="s", user_id="demo-user", query="update status_table set status='终止'"))
    assert result.status == "confirmation_required"
    assert result.confirmation_payload is not None
