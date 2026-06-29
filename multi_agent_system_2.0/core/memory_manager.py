from __future__ import annotations

from dataclasses import dataclass

from core.models import MemoryRecord
from utils.helpers import utc_now_iso


TRIGGER_KEYWORDS = ["记住", "长久记住", "别忘了", "以后要用", "存起来", "这个很重要", "以后会用到"]
FORGET_KEYWORDS = ["不用记住", "忘了吧"]


@dataclass(slots=True)
class MemoryDecision:
    action: str
    matched_keyword: str | None = None


class MemoryManager:
    def __init__(self) -> None:
        self._long_term_memory: dict[str, list[MemoryRecord]] = {}

    def detect_memory_action(self, query: str) -> MemoryDecision:
        for keyword in FORGET_KEYWORDS:
            if keyword in query:
                return MemoryDecision(action="delete", matched_keyword=keyword)
        for keyword in TRIGGER_KEYWORDS:
            if keyword in query:
                return MemoryDecision(action="write", matched_keyword=keyword)
        return MemoryDecision(action="none")

    def write_long_term_memory(self, session_id: str, content: str, keyword: str | None = None) -> MemoryRecord:
        record = MemoryRecord(
            key=f"ltm-{session_id}-{len(self._long_term_memory.get(session_id, [])) + 1}",
            content=content,
            source="long_term",
            metadata={"keyword": keyword, "created_at": utc_now_iso()},
        )
        self._long_term_memory.setdefault(session_id, []).append(record)
        return record

    def delete_last_long_term_memory(self, session_id: str) -> MemoryRecord | None:
        bucket = self._long_term_memory.get(session_id, [])
        if not bucket:
            return None
        return bucket.pop()

    def get_long_term_memory(self, session_id: str) -> list[MemoryRecord]:
        return list(self._long_term_memory.get(session_id, []))
