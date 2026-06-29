from __future__ import annotations


def execute_db_query(sql: str) -> dict:
    return {"sql": sql, "status": "mocked"}
