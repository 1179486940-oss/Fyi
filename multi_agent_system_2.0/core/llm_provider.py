from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import SETTINGS
from core.models import Artifact
from utils.helpers import resolve_artifact_path
from utils.logger import ensure_directory


@dataclass(slots=True)
class MockResponse:
    content: str
    metadata: dict[str, Any]


class LLMProvider:
    def complete(self, prompt: str) -> MockResponse:
        return MockResponse(content=f"[mock-llm] {prompt}", metadata={"model": SETTINGS.default_text_model})

    def structured_intent(self, query: str) -> dict[str, Any]:
        lowered = query.lower()
        if "ppt" in lowered:
            return {"intent": "ppt_generate", "confidence": 0.93}
        if any(token in lowered for token in ["图", "chart", "plot", "折线", "柱状"]):
            return {"intent": "data_graph", "confidence": 0.91}
        if any(token in lowered for token in ["报表", "excel", "report"]):
            return {"intent": "data_report", "confidence": 0.9}
        if any(token in lowered for token in ["查", "sql", "update", "delete", "insert", "状态"]):
            return {"intent": "data_query_update", "confidence": 0.89}
        return {"intent": "fallback", "confidence": 0.6}

    def multimodal_extract(self, attachment_paths: list[str]) -> str:
        if not attachment_paths:
            return ""
        return "\n".join(f"[mock multimodal extracted] {path}" for path in attachment_paths)

    def create_artifact(self, artifact_type: str, name: str, content: str) -> Artifact:
        root = ensure_directory(SETTINGS.artifact_root)
        suffix = {"image": ".png", "html": ".html", "excel": ".xlsx", "ppt": ".pptx"}[artifact_type]
        path = resolve_artifact_path(root, name).with_suffix(suffix)
        path.write_text(content, encoding="utf-8")
        return Artifact(
            name=name,
            artifact_type=artifact_type,
            path=str(path),
            url=f"{SETTINGS.mock_storage_base_url}/{path.name}",
            metadata={"provider": "mock"},
        )
