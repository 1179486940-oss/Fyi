from __future__ import annotations

from dataclasses import dataclass

from core.models import ConfirmationPayload


@dataclass(slots=True)
class ConfirmationState:
    approved: bool | None = None
    payload: ConfirmationPayload | None = None


class ConfirmationService:
    def __init__(self) -> None:
        self._states: dict[str, ConfirmationState] = {}

    def request(self, payload: ConfirmationPayload) -> ConfirmationState:
        state = ConfirmationState(approved=None, payload=payload)
        self._states[payload.confirmation_id] = state
        return state

    def resolve(self, confirmation_id: str, approved: bool) -> ConfirmationState | None:
        state = self._states.get(confirmation_id)
        if state is None:
            return None
        state.approved = approved
        return state

    def get(self, confirmation_id: str) -> ConfirmationState | None:
        return self._states.get(confirmation_id)
