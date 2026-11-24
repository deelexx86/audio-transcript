"""Run standalone GGUF ASR with an explicit CUDA backend."""
from __future__ import annotations

import json
import math
import re
import subprocess
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from faster_whisper.audio import decode_audio

from audio_transcript.model_storage import RUNTIME_DIRECTORY
from audio_transcript.transcription import SpeakerSegment, TranscriptionCancelled, TranscriptionResult


NEMOTRON_SPEAKER = re.compile(r"(?:<\|?|\[|\b)spk:(\d+)(?:\|?>|\])?")


def runtime_report(runtime_home: Path, option: str) -> dict:
    executable = runtime_home / RUNTIME_DIRECTORY / "audiocpp_cli.exe"
    result = subprocess.run(
        [str(executable), option, "--json"], cwd=executable.parent,
        capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError("audio.cpp could not start. Check its CUDA runtime installation.")
    return json.loads(result.stdout)


def cuda_device(runtime_home: Path) -> bool:
    devices = runtime_report(runtime_home, "--list-devices")["devices"]
    return any(str(device.get("backend", "")).lower() == "cuda" for device in devices)


def available_families(runtime_home: Path) -> set[str]:
    loaders = runtime_report(runtime_home, "--list-loaders")["loaders"]
    return {family for family, loader in loaders.items() if "offline" in loader["tasks"].get("asr", ())}


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError("Invalid structured transcript from audio.cpp.")
    return data


def segments_from_rows(
    rows: list[dict], duration: float, *, sample_rate: int = 16000, allow_times: bool = True,
) -> tuple[SpeakerSegment, ...]:
    segments = []
    for row in rows:
        speaker = row.get("speaker_id", row.get("speaker"))
        text = row.get("text", row.get("display", row.get("word")))
        if speaker is None or not isinstance(text, str) or not text.strip():
            continue
        start = row.get("start_seconds", row.get("start"))
        end = row.get("end_seconds", row.get("end"))
        if isinstance(row.get("start_sample"), int) and isinstance(row.get("end_sample"), int):
            start, end = row["start_sample"] / sample_rate, row["end_sample"] / sample_rate
        if not (allow_times and isinstance(start, (float, int)) and isinstance(end, (float, int))
                and math.isfinite(start) and math.isfinite(end) and 0 <= start <= end <= duration + 1):
            start = end = None
        segments.append(SpeakerSegment(str(speaker), text.strip(), start, end))
    return tuple(segments)


def nemotron_speaker_text(text: str) -> tuple[SpeakerSegment, ...]:
    # CTC alignment can be unavailable while the decoder still supplies tags.
    tags = list(NEMOTRON_SPEAKER.finditer(text))
    turns = []
    for index, tag in enumerate(tags):
        end = tags[index + 1].start() if index + 1 < len(tags) else len(text)
        words = text[tag.end():end].strip()
        if words:
            turns.append(SpeakerSegment(f"spk:{tag[1]}", words))
    return tuple(turns)


class GgufTranscriber:
    def __init__(self, model, model_dir: Path, runtime_home: Path) -> None:
        self.model = model
        self.weights = model_dir / model.files[0].name
        self.exe = runtime_home / RUNTIME_DIRECTORY / "audiocpp_cli.exe"
        self.runtime_home = runtime_home

    def transcribe(self, source, *, duration, on_progress, should_stop, on_timing=None):
        # Decode once at the runtime's input rate. The CLI receives the whole
        # recording, so native speaker state survives the runtime's own windows.
        if should_stop():
            raise TranscriptionCancelled("Transcription was stopped.")
        rate = 24000 if self.model.family.startswith("vibevoice_asr") else 16000
        audio = decode_audio(source, sampling_rate=rate)
        duration = len(audio) / rate
        if should_stop():
            raise TranscriptionCancelled("Transcription was stopped.")
        if not duration:
            raise ValueError("The source contains no decodable audio.")
        if self.model.limit is not None and duration > self.model.limit:
            raise ValueError(f"{self.model.display_name} accepts at most {self.model.limit} seconds in this application.")
        with TemporaryDirectory(prefix="asr-", dir=self.runtime_home) as temp:
            temp = Path(temp)
            media = temp / "media.wav"
            with wave.open(str(media), "wb") as output:
                output.setparams((1, 2, rate, 0, "NONE", ""))
                for offset in range(0, len(audio), rate * 10):
                    if should_stop():
                        raise TranscriptionCancelled("Transcription was stopped.")
                    block = audio[offset:offset + rate * 10]
                    output.writeframesraw((block.clip(-1.0, 32767 / 32768) * 32768).astype("<i2").tobytes())
            del audio, block
            text_file = temp / "text.txt"
            turns = temp / "turns.json"
            words = temp / "words.json"
            command = [
                str(self.exe), "--task", "asr", "--family", self.model.family, "--backend", "cuda",
                "--model", str(self.weights), "--audio", str(media), "--text-out", str(text_file),
                "--metrics", *self.model.options,
            ]
            if self.model.speakers:
                command.extend(("--turns-out", str(turns)))
            if self.model.family == "nemotron_transcribe":
                command.extend(("--words-out", str(words)))
            if self.model.family == "moss_transcribe_diarize":
                command.extend(("--max-tokens", str(max(512, math.ceil(duration * 16)))))
            if should_stop():
                raise TranscriptionCancelled("Transcription was stopped.")
            if on_timing:
                on_timing("Transcribing", None, duration)
            with (temp / "cli.log").open("w+b") as log:
                with subprocess.Popen(
                    command, cwd=self.exe.parent, stdin=subprocess.DEVNULL, stdout=log,
                    stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                ) as process:
                    try:
                        while process.poll() is None:
                            if should_stop():
                                raise TranscriptionCancelled("Transcription was stopped.")
                            try:
                                process.wait(timeout=0.2)
                            except subprocess.TimeoutExpired:
                                pass
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait()
                    if process.returncode or not text_file.is_file():
                        log.seek(0, 2)
                        log.seek(max(0, log.tell() - 1600))
                        details = log.read().decode("utf-8", errors="replace").strip()
                        raise RuntimeError(f"audio.cpp CUDA exited with status {process.returncode}. {details}")
                    log.seek(0)
                    output = log.read().decode("utf-8", errors="replace")
            timing = re.search(r"(?m)^metrics\.wall_ms=([0-9eE.+-]+)\s*$", output)
            elapsed = float(timing[1]) / 1000 if timing else None
            text = text_file.read_text(encoding="utf-8-sig").strip()
            attributed = ()
            if self.model.family == "nemotron_transcribe":
                schema = next(
                    (line.partition("=")[2] for line in output.splitlines() if line.startswith("custom_schema_output=")), "",
                )
                if not schema:
                    raise RuntimeError("Nemotron did not report whether transcription completed.")
                report = json.loads(schema)["data"]
                if report.get("termination") not in {"end_of_turn", "near_silent"}:
                    raise RuntimeError(f"Nemotron stopped before completion: {report.get('termination')}")
                attributed = segments_from_rows(report.get("words", []), duration)
                if not attributed:
                    attributed = nemotron_speaker_text(text)
                text = NEMOTRON_SPEAKER.sub(" ", text).strip()
            elif self.model.speakers:
                attributed = segments_from_rows(
                    read_rows(turns), duration, sample_rate=rate, allow_times=self.model.timestamps,
                )
                if self.model.family == "moss_transcribe_diarize" and text:
                    if not attributed:
                        raise RuntimeError("MOSS did not return a complete speaker-attributed transcript.")
                    text = " ".join(part.text for part in attributed)
                if self.model.streamed:
                    text = re.sub(r"(?im)^\s*Speaker\s+\d+\s*:\s*", "", text).strip()
            if not text:
                raise ValueError("The selected model returned no recognized speech.")
            return TranscriptionResult(text, None, duration, attributed, elapsed)
