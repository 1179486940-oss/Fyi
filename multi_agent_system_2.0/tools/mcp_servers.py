from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MockMCPResponse:
    ok: bool
    payload: dict[str, Any]


class MockMCPRegistry:
    def run(self, server_name: str, action: str, payload: dict[str, Any]) -> MockMCPResponse:
        if server_name == "auth" and action == "authorize":
            return MockMCPResponse(ok=True, payload={"allowed": True, "details": payload})
        if server_name == "ppt" and action == "generate":
            return MockMCPResponse(ok=True, payload={"job_id": "mock-ppt-job", "details": payload})
        if server_name == "query" and action == "execute":
            return MockMCPResponse(ok=True, payload={"rows": payload.get("rows", []), "sql": payload.get("sql", "")})
        return MockMCPResponse(ok=True, payload={"server": server_name, "action": action, "details": payload})
