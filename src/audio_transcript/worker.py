from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from audio_transcript.artifacts import write_artifacts
from audio_transcript.audio import probe_duration
from audio_transcript.profiles import ModelProfile
from audio_transcript.queueing import QueueStatus
from audio_transcript.transcription import LocalTranscriber, TranscriptionCancelled


@dataclass(frozen=True, slots=True)
class WorkItem:
    id: str
    source: Path
    speaker: str
    duration: float | None


class BatchWorker(QObject):
    state_changed = Signal(str, str, int)
    item_completed = Signal(str, object)
    item_failed = Signal(str, str)
    finished = Signal(bool)

    def __init__(
        self,
        items: list[WorkItem],
        profile: ModelProfile,
        output_mode: str,
    ) -> None:
        super().__init__()
        self.items = items
        self.profile = profile
        self.output_mode = output_mode
        self._stop_requested = threading.Event()

    def request_stop(self) -> None:
        self._stop_requested.set()

    @Slot()
    def run(self) -> None:
        stopped = False
        transcriber: LocalTranscriber | None = None
        for work in self.items:
            if self._stop_requested.is_set():
                stopped = True
                break
            self.state_changed.emit(work.id, QueueStatus.PREPARING.value, 0)
            try:
                duration = probe_duration(work.source, decode_first_frame=True) or work.duration
                if self._stop_requested.is_set():
                    raise TranscriptionCancelled("Transcription was stopped.")
                if transcriber is None:
                    transcriber = LocalTranscriber(self.profile)
                self.state_changed.emit(work.id, QueueStatus.TRANSCRIBING.value, 0)
                result = transcriber.transcribe(
                    work.source,
                    duration=duration,
                    on_progress=lambda progress, item_id=work.id: self.state_changed.emit(
                        item_id, QueueStatus.TRANSCRIBING.value, progress
                    ),
                    should_stop=self._stop_requested.is_set,
                )
                if self._stop_requested.is_set():
                    raise TranscriptionCancelled("Transcription was stopped.")
                self.state_changed.emit(work.id, QueueStatus.SAVING.value, 100)
                processed_at = datetime.now().astimezone()
                artifacts = write_artifacts(
                    source=work.source,
                    transcript=result.text,
                    processed_at=processed_at,
                    duration=result.duration,
                    language=result.language,
                    speaker=work.speaker,
                    model_name=self.profile.artifact_name,
                    output_mode=self.output_mode,
                )
                self.item_completed.emit(
                    work.id,
                    {
                        "transcript": result.text,
                        "language": result.language,
                        "duration": result.duration,
                        "model_name": self.profile.artifact_name,
                        "output_directory": artifacts.directory,
                    },
                )
            except TranscriptionCancelled:
                self.state_changed.emit(work.id, QueueStatus.CANCELLED.value, 0)
                stopped = True
                break
            except Exception as exc:
                message = (
                    "Transcription failed\n\n"
                    f"Source:\n{work.source}\n\n"
                    f"Details:\n{exc}"
                )
                self.item_failed.emit(work.id, message)
                if self._stop_requested.is_set():
                    stopped = True
                    break
        self.finished.emit(stopped)
