from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from audio_transcript.audio import is_supported_audio


class QueueStatus(StrEnum):
    QUEUED = "Queued"
    PREPARING = "Preparing"
    DOWNLOADING = "Downloading"
    RETRYING = "Waiting to retry"
    TRANSCRIBING = "Transcribing"
    SAVING = "Saving"
    DONE = "Done"
    ERROR = "Error"
    CANCELLED = "Cancelled"


ACTIVE_STATUSES = {QueueStatus.PREPARING, QueueStatus.DOWNLOADING, QueueStatus.RETRYING, QueueStatus.TRANSCRIBING, QueueStatus.SAVING}
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
    added_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    source_url: str | None = None
    title: str = ""

    @property
    def display_name(self) -> str:
        if self.source_url:
            return f"YouTube · {self.title or self.source.stem.removeprefix('youtube-')}"
        return self.source.name


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

    def add_youtube(self, url: str, speaker: str = "") -> QueueItem | None:
        from audio_transcript.youtube import normalize_youtube_url

        normalized = normalize_youtube_url(url)
        if normalized in self._source_keys:
            return None
        video_id = normalized.rsplit("=", 1)[1]
        # Remote items use a stable output basename, never a local input path.
        item = QueueItem(
            source=Path(f"youtube-{video_id}"), speaker=speaker.strip(), source_url=normalized
        )
        self.items.append(item)
        self._source_keys.add(normalized)
        return item

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
                self._source_keys.discard(item.source_url or canonical_source(item.source))
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

    def move_ids(self, item_ids: Iterable[str], offset: int) -> None:
        """Move selected rows one step, preserving their relative order."""
        if offset not in (-1, 1):
            raise ValueError("offset must be -1 or 1")
        selected = set(item_ids)
        indices = range(len(self.items)) if offset == -1 else range(len(self.items) - 1, -1, -1)
        for index in indices:
            target = index + offset
            if (
                self.items[index].id in selected
                and 0 <= target < len(self.items)
                and self.items[target].id not in selected
            ):
                self.items[index], self.items[target] = self.items[target], self.items[index]

    def sort_by(self, field_name: str, *, descending: bool = False) -> None:
        keys = {
            "file": lambda item: item.display_name.casefold(),
            "duration": lambda item: item.duration if item.duration is not None else -1,
            "speaker": lambda item: item.speaker.casefold(),
            "status": lambda item: item.status.value,
            "added": lambda item: item.added_at,
        }
        self.items.sort(key=keys[field_name], reverse=descending)
