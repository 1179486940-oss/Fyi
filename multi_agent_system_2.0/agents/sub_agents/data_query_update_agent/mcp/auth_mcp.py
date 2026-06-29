from __future__ import annotations


def authorize_data_access(user_id: str) -> dict:
    return {"user_id": user_id, "allowed": True}
