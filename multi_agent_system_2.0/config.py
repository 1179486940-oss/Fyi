from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "multi_agent_system"
    app_env: str = "development"
    default_llm_provider: Literal["mock", "openai", "anthropic"] = "mock"
    default_text_model: str = "mock-text"
    default_vision_model: str = "mock-vision"
    short_term_memory_limit: int = 15
    long_term_memory_ttl_days: int = 30
    artifact_root: Path = Path("artifacts")
    mock_storage_base_url: str = "http://localhost:8000/mock-downloads"


SETTINGS = Settings()
