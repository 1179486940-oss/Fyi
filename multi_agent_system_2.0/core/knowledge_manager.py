from __future__ import annotations

from core.models import RetrievalChunk


class KnowledgeManager:
    def __init__(self) -> None:
        self._kb: dict[str, list[RetrievalChunk]] = {
            "database": [
                RetrievalChunk("database", "status_table(id, status, owner, updated_at)", 0.95, {"table": "status_table"}),
                RetrievalChunk("database", "sales_table(month, region, amount, report_version)", 0.92, {"table": "sales_table"}),
            ],
            "business": [
                RetrievalChunk("business", "PPT 生成支持晚点发布模板、汇总模板、趋势模板。", 0.86),
                RetrievalChunk("business", "默认报表导出为 Excel，图表支持 PNG 与 HTML。", 0.83),
            ],
            "feedback": [],
        }

    def retrieve(self, kb_type: str, top_k: int = 3) -> list[RetrievalChunk]:
        return list(self._kb.get(kb_type, []))[:top_k]

    def merge_context(self, *groups: list[RetrievalChunk]) -> list[RetrievalChunk]:
        merged = [chunk for group in groups for chunk in group]
        return sorted(merged, key=lambda item: item.score, reverse=True)

    def add_feedback_chunk(self, chunk: RetrievalChunk) -> None:
        self._kb.setdefault("feedback", []).append(chunk)
