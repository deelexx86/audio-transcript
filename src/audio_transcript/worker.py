from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from PySide6.QtCore import QObject, Signal, Slot

from audio_transcript.artifacts import write_artifacts
from audio_transcript.audio import probe_duration
from audio_transcript.errors import ProcessingFailure
from audio_transcript.paths import CONFIG_DIR
from audio_transcript.profiles import ModelMissingError, ModelProfile, require_local_model
from audio_transcript.queueing import QueueStatus
from audio_transcript.transcription import LocalTranscriber, TranscriptionCancelled
from audio_transcript.timing import AttemptTiming
from audio_transcript.youtube import YouTubeDownloadError, download_audio


@dataclass(frozen=True, slots=True)
class WorkItem:
    id: str
    source: Path
    speaker: str
    duration: float | None
    source_url: str | None = None


class BatchWorker(QObject):
    state_changed = Signal(str, str, int)
    item_completed = Signal(str, object)
    item_failed = Signal(str, object)
    finished = Signal(bool)
    timing_changed = Signal(str, object)

    def __init__(
        self,
        items: list[WorkItem],
        profile: ModelProfile,
        output_mode: str,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        super().__init__()
        self.items = items
        self.profile = profile
        self.output_mode = output_mode
        self._stop_requested = threading.Event()
        self._clock = clock

    def _state(self, item_id: str, timing: AttemptTiming, state: QueueStatus, progress: int) -> None:
        timing.set_phase(state.value)
        self.timing_changed.emit(item_id, timing.snapshot())
        self.state_changed.emit(item_id, state.value, progress)

    def _observation(self, item_id: str, timing: AttemptTiming, phase: str,
                     position: float | None, duration: float | None) -> None:
        timing.set_phase(phase, duration=duration)
        if position is not None:
            timing.observe(position, duration)
        self.timing_changed.emit(item_id, timing.snapshot())
        if position is None:
            self.state_changed.emit(item_id, phase, 0)

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
            timing = AttemptTiming(clock=self._clock)
            self._state(work.id, timing, QueueStatus.PREPARING, 0)
            try:
                with ExitStack() as cleanup:
                    source = work.source
                    title = ""
                    if work.source_url:
                        require_local_model(self.profile)
                        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                        directory = Path(cleanup.enter_context(
                            TemporaryDirectory(prefix="youtube-", dir=CONFIG_DIR)
                        ))
                        self._state(work.id, timing, QueueStatus.DOWNLOADING, -1)
                        audio = download_audio(
                            work.source_url, directory,
                            on_progress=lambda progress, item_id=work.id: self._state(
                                item_id, timing, QueueStatus.DOWNLOADING, progress
                            ),
                            should_stop=self._stop_requested.is_set,
                            on_retry=lambda item_id=work.id: self._state(
                                item_id, timing, QueueStatus.RETRYING, -1
                            ),
                        )
                        source, title = audio.path, audio.title
                        self._state(work.id, timing, QueueStatus.PREPARING, 0)
                    duration = probe_duration(source, decode_first_frame=True) or work.duration
                    if self._stop_requested.is_set():
                        raise TranscriptionCancelled("Transcription was stopped.")
                    if transcriber is None:
                        transcriber = LocalTranscriber(self.profile)
                    result = transcriber.transcribe(
                        source,
                        duration=duration,
                        on_progress=lambda progress, item_id=work.id: self.state_changed.emit(
                            item_id, QueueStatus.TRANSCRIBING.value, progress),
                        on_timing=lambda phase, position, duration, item_id=work.id: self._observation(
                            item_id, timing, phase, position, duration),
                        should_stop=self._stop_requested.is_set,
                    )
                    if self._stop_requested.is_set():
                        raise TranscriptionCancelled("Transcription was stopped.")
                    self._state(work.id, timing, QueueStatus.SAVING, 100)
                    processed_at = datetime.now().astimezone()
                    artifacts = write_artifacts(
                        source=work.source,
                        transcript=result.text,
                        processed_at=processed_at,
                        duration=result.duration,
                        language=result.language,
                        speaker=work.speaker,
                        model_name=self.profile.artifact_name,
                        output_mode="workspace" if work.source_url else self.output_mode,
                        source_url=work.source_url,
                        source_title=title,
                    )
                    payload = {
                        "transcript": result.text,
                        "title": title,
                        "language": result.language,
                        "duration": result.duration,
                        "model_name": self.profile.artifact_name,
                        "output_directory": artifacts.directory,
                    }
                # Include artifact saving and temporary-media cleanup in elapsed.
                timing.finish(QueueStatus.DONE.value)
                self.timing_changed.emit(work.id, timing.snapshot())
                payload["processing_seconds"] = timing.snapshot().view(self._clock()).elapsed
                self.item_completed.emit(work.id, payload)
            except TranscriptionCancelled:
                timing.finish(QueueStatus.CANCELLED.value)
                self.timing_changed.emit(work.id, timing.snapshot())
                self.state_changed.emit(work.id, QueueStatus.CANCELLED.value, 0)
                stopped = True
                break
            except Exception as exc:
                timing.finish(QueueStatus.ERROR.value)
                self.timing_changed.emit(work.id, timing.snapshot())
                message = ProcessingFailure(
                    source=str(work.source_url or work.source),
                    details=str(exc),
                    kind=exc.kind if isinstance(exc, YouTubeDownloadError)
                    else "model_missing" if isinstance(exc, ModelMissingError)
                    else "transcription",
                )
                self.item_failed.emit(work.id, message)
                if self._stop_requested.is_set():
                    stopped = True
                    break
        self.finished.emit(stopped)
