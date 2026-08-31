from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from audio_transcript.audio import is_supported_audio


class QueueStatus(StrEnum):
    QUEUED = "Queued"
    PREPARING = "Preparing"
    TRANSCRIBING = "Transcribing"
    SAVING = "Saving"
    DONE = "Done"
    ERROR = "Error"
    CANCELLED = "Cancelled"


ACTIVE_STATUSES = {QueueStatus.PREPARING, QueueStatus.TRANSCRIBING, QueueStatus.SAVING}
RETRYABLE_STATUSES = {QueueStatus.QUEUED, QueueStatus.ERROR, QueueStatus.CANCELLED}


@dataclass(slots=True)
class QueueItem:
    source: Path
    speaker: str = ""
    duration: float | None = None
    status: QueueStatus = QueueStatus.QUEUED
    progress: int = 0
    transcript: str = ""
    error: str = ""
    output_directory: Path | None = None
    language: str | None = None
    model_name: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass(frozen=True, slots=True)
class AddResult:
    added: tuple[QueueItem, ...]
    duplicates: int
    unsupported: int
    missing: int


def canonical_source(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))


class QueueManager:
    def __init__(self) -> None:
        self.items: list[QueueItem] = []
        self._source_keys: set[str] = set()

    def add_paths(self, paths: Iterable[str | Path], speaker: str = "") -> AddResult:
        added: list[QueueItem] = []
        duplicates = unsupported = missing = 0
        for raw_path in paths:
            path = Path(raw_path).expanduser().resolve(strict=False)
            if not path.is_file():
                missing += 1
                continue
            if not is_supported_audio(path):
                unsupported += 1
                continue
            key = canonical_source(path)
            if key in self._source_keys:
                duplicates += 1
                continue
            item = QueueItem(source=path, speaker=speaker.strip())
            self.items.append(item)
            self._source_keys.add(key)
            added.append(item)
        return AddResult(tuple(added), duplicates, unsupported, missing)

    def remove_ids(self, item_ids: Iterable[str]) -> None:
        remove = set(item_ids)
        retained: list[QueueItem] = []
        for item in self.items:
            if item.id in remove:
                self._source_keys.discard(canonical_source(item.source))
            else:
                retained.append(item)
        self.items = retained

    def clear(self) -> None:
        self.items.clear()
        self._source_keys.clear()

    def get(self, item_id: str) -> QueueItem | None:
        return next((item for item in self.items if item.id == item_id), None)

    def retryable_items(self) -> list[QueueItem]:
        return [item for item in self.items if item.status in RETRYABLE_STATUSES]
