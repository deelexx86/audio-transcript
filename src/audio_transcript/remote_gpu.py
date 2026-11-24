"""Client for one on-demand CUDA job over a verified OpenSSH connection."""
from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from contextlib import suppress
from math import isfinite
from pathlib import Path
from queue import Empty, Queue
from tempfile import TemporaryFile
from threading import Event, Thread
from time import monotonic
from typing import BinaryIO

from audio_transcript.acceleration import valid_ssh_alias
from audio_transcript.profiles import ModelProfile
from audio_transcript.transcription import TranscriptionCancelled, TranscriptionResult


PROTOCOL = 1
BLOCK_SIZE = 256 * 1024
HEARTBEAT = 2
UPLOAD_TIMEOUT = 60
LEASE_TIMEOUT = 45
REMOTE_COMMAND = (
    r'"%LOCALAPPDATA%\AudioTranscriptGpu\.venv\Scripts\python.exe" -u '
    r'"%LOCALAPPDATA%\AudioTranscriptGpu\worker.pyz"'
)


def ssh_command(alias: str) -> list[str]:
    if not valid_ssh_alias(alias):
        raise ValueError("Expected an SSH alias containing only letters, numbers, dots, dashes or underscores.")
    return [
        "ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3",
        "-o", "ForwardAgent=no", "-o", "ClearAllForwardings=yes", alias,
    ]


class RemoteGPUError(RuntimeError):
    def __init__(self, message: str, kind: str = "remote_connection") -> None:
        super().__init__(message)
        self.kind = kind


class RemoteTranscriber:
    def __init__(self, profile: ModelProfile, alias: str) -> None:
        self.profile = profile
        self.command = [*ssh_command(alias), REMOTE_COMMAND]

    def transcribe(
        self,
        source: str | Path,
        *,
        duration: float | None,
        on_progress: Callable[[int], None],
        should_stop: Callable[[], bool],
        on_timing: Callable[[str, float | None, float | None], None] | None = None,
    ) -> TranscriptionResult:
        if should_stop():
            raise TranscriptionCancelled("Transcription was stopped.")
        with Path(source).open("rb") as media, TemporaryFile() as stderr:
            size = os.fstat(media.fileno()).st_size
            try:
                process = subprocess.Popen(
                    self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as exc:
                raise RemoteGPUError(f"Could not start Windows OpenSSH: {exc}") from exc
            with process:
                try:
                    result = self._exchange(process, media, size, on_progress, should_stop, on_timing)
                except RemoteGPUError as exc:
                    if process.poll() is not None:
                        stderr.seek(0)
                        diagnostic = stderr.read(2048).decode("utf-8", errors="replace").strip()
                        if diagnostic:
                            raise RemoteGPUError(f"{exc}\n{diagnostic}", exc.kind) from exc
                    raise
        on_progress(100)
        return result

    def _exchange(self, process, media, size, on_progress, should_stop, on_timing):
        events: Queue[bytes | None] = Queue()
        upload = Event()
        done = Event()
        last_write = monotonic()
        send_error: OSError | None = None

        def send() -> None:
            nonlocal last_write, send_error
            try:
                header = {"version": PROTOCOL, "profile": self.profile.key, "size": size}
                process.stdin.write(json.dumps(header).encode("ascii") + b"\n")
                process.stdin.flush()
                upload.wait()
                remaining = size
                while remaining and not done.is_set():
                    block = media.read(min(BLOCK_SIZE, remaining))
                    if not block:
                        raise OSError("The source became shorter during transfer.")
                    process.stdin.write(block)
                    process.stdin.flush()
                    remaining -= len(block)
                    last_write = monotonic()
                while not done.wait(HEARTBEAT):
                    process.stdin.write(b"\0")
                    process.stdin.flush()
            except OSError as exc:
                send_error = exc

        def receive() -> None:
            try:
                while line := process.stdout.readline():
                    events.put(line)
            finally:
                events.put(None)

        sender = Thread(target=send, name="ssh-upload")
        receiver = Thread(target=receive, name="ssh-events")
        sender.start()
        receiver.start()
        result = None
        phase = "connecting"
        try:
            while True:
                if should_stop():
                    raise TranscriptionCancelled("Transcription was stopped.")
                try:
                    line = events.get(timeout=0.1)
                except Empty:
                    if send_error and process.poll() is None and phase == "upload":
                        raise RemoteGPUError(f"Could not send the source: {send_error}")
                    if phase in ("connecting", "upload", "finished") and monotonic() - last_write > UPLOAD_TIMEOUT:
                        raise RemoteGPUError("The remote connection or upload stopped responding.")
                    continue
                if line is None:
                    exit_code = process.wait(timeout=5)
                    if exit_code != 0 or result is None:
                        raise RemoteGPUError(
                            f"The SSH worker exited without a successful result ({phase}, exit {exit_code})."
                        )
                    return result
                try:
                    message = json.loads(line)
                    event = message["event"]
                    if event == "ready" and phase == "connecting" and message["version"] == PROTOCOL:
                        phase = "upload"
                        last_write = monotonic()
                        if on_timing:
                            on_timing("Uploading", None, None)
                        upload.set()
                    elif event == "received" and phase == "upload":
                        phase = "preparing"
                        if on_timing:
                            on_timing("Preparing", None, None)
                    elif event == "inference" and phase == "preparing":
                        phase = "inference"
                        actual_duration = float(message["duration"])
                        if not isfinite(actual_duration) or actual_duration < 0:
                            raise ValueError("Invalid media duration.")
                        if on_timing:
                            on_timing("Transcribing", None, actual_duration)
                    elif event == "position" and phase == "inference":
                        position = float(message["seconds"])
                        if not isfinite(position) or position < 0:
                            raise ValueError("Invalid media position.")
                        if on_timing:
                            on_timing("Transcribing", position, actual_duration)
                        if actual_duration > 0:
                            on_progress(min(99, max(0, round(position / actual_duration * 100))))
                    elif event == "result" and phase == "inference":
                        text, language = message["text"], message["language"]
                        if not isinstance(text, str) or (language is not None and not isinstance(language, str)):
                            raise ValueError("Invalid transcript.")
                        result = TranscriptionResult(text, language, actual_duration)
                        phase = "finished"
                        last_write = monotonic()
                    elif event == "error":
                        raise RemoteGPUError(str(message["details"]), message["kind"])
                    else:
                        raise ValueError("Unexpected message or protocol version.")
                except (KeyError, TypeError, ValueError, OverflowError) as exc:
                    raise RemoteGPUError("Invalid SSH worker response. Rerun the remote GPU setup.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RemoteGPUError("The SSH worker did not exit after closing its output.") from exc
        finally:
            done.set()
            upload.set()
            if process.poll() is None:
                process.kill()
            process.wait()
            sender.join()
            receiver.join()
            with suppress(OSError):
                process.stdin.close()
