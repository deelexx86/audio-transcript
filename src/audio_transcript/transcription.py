from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel

from audio_transcript.profiles import ModelProfile, require_local_model


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    language: str | None
    duration: float | None


class TranscriptionCancelled(RuntimeError):
    pass


class LocalTranscriber:
    def __init__(self, profile: ModelProfile) -> None:
        model_path = require_local_model(profile)
        self.profile = profile
        self.model = WhisperModel(
            str(model_path),
            device="cpu",
            compute_type="int8",
            local_files_only=True,
        )

    def transcribe(
        self,
        source: str | Path,
        *,
        duration: float | None,
        on_progress: Callable[[int], None],
        should_stop: Callable[[], bool],
    ) -> TranscriptionResult:
        segments, info = self.model.transcribe(str(source))
        actual_duration = duration or getattr(info, "duration", None)
        pieces: list[str] = []
        for segment in segments:
            if should_stop():
                raise TranscriptionCancelled("Transcription was stopped.")
            pieces.append(segment.text)
            if actual_duration and actual_duration > 0:
                on_progress(min(99, max(0, round((segment.end / actual_duration) * 100))))
        if should_stop():
            raise TranscriptionCancelled("Transcription was stopped.")
        on_progress(100)
        return TranscriptionResult(
            text="".join(pieces).strip(),
            language=getattr(info, "language", None),
            duration=actual_duration,
        )
