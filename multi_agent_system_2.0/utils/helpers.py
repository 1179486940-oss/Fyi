from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence, TypeVar

T = TypeVar("T")


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def take(items: Sequence[T], limit: int) -> list[T]:
    return list(items[: max(limit, 0)])


def flatten(parts: Iterable[Iterable[T]]) -> list[T]:
    return [item for group in parts for item in group]


def safe_filename(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in name)
    return cleaned.strip("_") or "artifact"


def resolve_artifact_path(root: str | Path, *parts: str) -> Path:
    path = Path(root)
    for part in parts:
        path = path / safe_filename(part)
    return path
