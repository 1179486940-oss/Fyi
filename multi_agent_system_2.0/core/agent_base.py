from __future__ import annotations

from dataclasses import dataclass, field

from core.auth_manager import AuthManager
from core.knowledge_manager import KnowledgeManager
from core.llm_provider import LLMProvider
from core.memory_manager import MemoryManager
from core.models import AgentEvent, AgentResult
from core.session_manager import SessionManager


@dataclass(slots=True)
class AgentDependencies:
    llm_provider: LLMProvider
    session_manager: SessionManager
    memory_manager: MemoryManager
    knowledge_manager: KnowledgeManager
    auth_manager: AuthManager


@dataclass(slots=True)
class AgentContext:
    session_id: str
    user_id: str
    query: str
    multimodal_context: str = ""
    metadata: dict = field(default_factory=dict)


class AgentBase:
    agent_name = "base_agent"
    subsystem = "fallback"

    def __init__(self, deps: AgentDependencies) -> None:
        self.deps = deps

    def event(self, message: str, event_type: str = "trace") -> AgentEvent:
        return AgentEvent(type=event_type, message=message)

    def summarize_execution(self, steps: list[str]) -> str:
        return " -> ".join(steps)

    def run(self, context: AgentContext) -> AgentResult:
        raise NotImplementedError
