from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from core.models import ConfirmationPayload


WRITE_VERBS = ("update", "delete", "insert", "modify", "change", "set ")


@dataclass(slots=True)
class GuardrailDecision:
    requires_clarification: bool = False
    clarification_message: str = ""
    is_write_intent: bool = False


class Guardrails:
    def detect_write_intent(self, query: str) -> bool:
        lowered = query.lower()
        return any(token in lowered for token in WRITE_VERBS)

    def evaluate_query(self, query: str) -> GuardrailDecision:
        stripped = query.strip()
        if len(stripped) < 4:
            return GuardrailDecision(True, "你的问题有点短，我需要更多上下文才能判断该调用哪个子 Agent。")
        return GuardrailDecision(False, "", self.detect_write_intent(query))

    def build_confirmation_payload(self, operation: str, summary: str, sql: str, preview_rows: list[dict]) -> ConfirmationPayload:
        return ConfirmationPayload(
            confirmation_id=str(uuid4()),
            operation=operation,
            summary=summary,
            sql=sql,
            preview_rows=preview_rows,
        )
