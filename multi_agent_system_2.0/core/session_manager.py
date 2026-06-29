from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

from core.models import RouterState
from utils.helpers import take


class SessionManager:
    def __init__(self, memory_limit: int = 15) -> None:
        self.memory_limit = memory_limit
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        self._checkpoints: dict[str, list[RouterState]] = {}

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        turns = self._sessions.setdefault(session_id, [])
        turns.append({"role": role, "content": content})
        self._sessions[session_id] = take(turns, self.memory_limit)

    def get_recent_turns(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._sessions.get(session_id, []))

    def create_checkpoint(self, state: RouterState) -> str:
        checkpoint_id = str(uuid4())
        snapshots = self._checkpoints.setdefault(state.session_id, [])
        snapshots.append(replace(state, checkpoints=list(state.checkpoints) + [checkpoint_id]))
        return checkpoint_id

    def restore_checkpoint(self, session_id: str, checkpoint_id: str) -> RouterState | None:
        for snapshot in reversed(self._checkpoints.get(session_id, [])):
            if checkpoint_id in snapshot.checkpoints:
                return snapshot
        return None
