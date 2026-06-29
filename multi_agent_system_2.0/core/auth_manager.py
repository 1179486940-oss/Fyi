from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AuthDecision:
    allowed: bool
    reason: str
    hidden_fields: list[str]


class AuthManager:
    def __init__(self) -> None:
        self._permissions = {
            "demo-user": {"data": True, "graph": True, "report": True, "ppt": True, "fallback": True},
            "restricted-user": {"data": True, "graph": False, "report": False, "ppt": False, "fallback": True},
        }

    def authorize(self, user_id: str, subsystem: str) -> AuthDecision:
        allowed = self._permissions.get(user_id, self._permissions["demo-user"]).get(subsystem, False)
        if not allowed:
            return AuthDecision(False, f"User {user_id} has no access to {subsystem} subsystem.", [])
        hidden_fields = ["key1", "key2", "key3"] if user_id == "restricted-user" and subsystem == "data" else []
        return AuthDecision(True, "authorized", hidden_fields)
