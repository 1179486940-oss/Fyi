from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


EventType = Literal[
    "answer",
    "clarification",
    "confirmation",
    "artifact_ready",
    "error",
    "trace",
]


@dataclass(slots=True)
class Attachment:
    name: str
    content_type: str
    path: str


@dataclass(slots=True)
class MemoryRecord:
    key: str
    content: str
    source: Literal["short_term", "long_term", "feedback", "kb"]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalChunk:
    kb_type: Literal["database", "business", "long_term", "feedback"]
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConfirmationPayload:
    confirmation_id: str
    operation: str
    summary: str
    sql: str
    preview_rows: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentEvent:
    type: EventType
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Artifact:
    name: str
    artifact_type: Literal["image", "html", "excel", "ppt"]
    path: str
    url: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentResult:
    status: Literal["success", "clarification_required", "confirmation_required", "error"]
    agent_name: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    table_preview: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    confirmation_required: bool = False
    clarification_required: bool = False
    events: list[AgentEvent] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    confirmation_payload: ConfirmationPayload | None = None


@dataclass(slots=True)
class RouterTask:
    agent_name: str
    user_query: str
    dependency_on: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RouterState:
    session_id: str
    user_id: str
    query: str
    attachments: list[Attachment] = field(default_factory=list)
    normalized_query: str = ""
    multimodal_context: str = ""
    memory_context: list[MemoryRecord] = field(default_factory=list)
    retrieval_context: list[RetrievalChunk] = field(default_factory=list)
    planned_tasks: list[RouterTask] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)
