from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

from audio_transcript.acceleration import ExecutionMode, prepare_cuda
from audio_transcript.profiles import ModelProfile, require_local_model


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    language: str | None
    duration: float | None


class TranscriptionCancelled(RuntimeError):
    pass


class LocalTranscriber:
    def __init__(
        self, profile: ModelProfile, *, mode: ExecutionMode = ExecutionMode.CPU,
        models_dir: Path | None = None,
    ) -> None:
        if mode not in (ExecutionMode.CPU, ExecutionMode.LOCAL_CUDA):
            raise ValueError(f"Unsupported local execution mode: {mode}")
        cuda = mode == ExecutionMode.LOCAL_CUDA
        if cuda:
            prepare_cuda()
        model_path = require_local_model(profile) if models_dir is None else require_local_model(
            profile, models_dir=models_dir
        )
        self.profile = profile
        self.model = WhisperModel(
            str(model_path),
            device="cuda" if cuda else "cpu",
            device_index=0,
            compute_type="float16" if cuda else "int8",
            local_files_only=True,
        )

    def transcribe(
        self,
        source: str | Path | BinaryIO,
        *,
        duration: float | None,
        on_progress: Callable[[int], None],
        should_stop: Callable[[], bool],
        on_timing: Callable[[str, float | None, float | None], None] | None = None,
    ) -> TranscriptionResult:
        # Match faster-whisper's normal decoding, but expose its boundary so
        # media preparation is not counted as inference throughput.
        if should_stop():
            raise TranscriptionCancelled("Transcription was stopped.")
        sampling_rate = self.model.feature_extractor.sampling_rate
        media = str(source) if isinstance(source, (str, Path)) else source
        audio = decode_audio(media, sampling_rate=sampling_rate)
        actual_duration = audio.shape[0] / sampling_rate
        if should_stop():
            raise TranscriptionCancelled("Transcription was stopped.")
        if on_timing:
            on_timing("Transcribing", None, actual_duration)
        segments, info = self.model.transcribe(audio)
        pieces: list[str] = []
        for segment in segments:
            if should_stop():
                raise TranscriptionCancelled("Transcription was stopped.")
            pieces.append(segment.text)
            if on_timing:
                on_timing("Transcribing", float(segment.end), actual_duration)
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
