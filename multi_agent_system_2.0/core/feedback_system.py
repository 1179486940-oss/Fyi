from __future__ import annotations

from core.models import RetrievalChunk


class FeedbackSystem:
    def create_feedback_chunk(self, question: str, answer: str, feedback: str) -> RetrievalChunk:
        content = f"Question: {question}\nAnswer: {answer}\nFeedback: {feedback}"
        return RetrievalChunk("feedback", content, 1.0, {"question": question, "feedback": feedback})
