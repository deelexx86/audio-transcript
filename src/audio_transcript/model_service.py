"""Short-lived JSON Lines endpoint for model status and lifecycle operations."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from queue import Empty, Queue
from tempfile import TemporaryFile
from threading import Event, Thread
from time import monotonic, sleep

import ctranslate2

from audio_transcript.acceleration import ExecutionMode, prepare_cuda
from audio_transcript.gguf_asr import available_families, cuda_device
from audio_transcript.model_catalog import CATALOG, CATALOG_BY_KEY
from audio_transcript.model_storage import (
    RUNTIME_DIRECTORY, download, has_managed_files, installed_bytes, remove,
)
from audio_transcript.paths import MODELS_DIR
from audio_transcript.remote_gpu import HEARTBEAT, LEASE_TIMEOUT, REMOTE_COMMAND, ssh_command
from audio_transcript.transcription import TranscriptionCancelled


class ModelWorkerError(RuntimeError):
    """The worker was reached and rejected the requested operation."""


def runtime_status(mode: ExecutionMode, runtime_home: Path, family: str) -> str:
    if mode == ExecutionMode.CPU:
        return "ready"
    if family and not (runtime_home / RUNTIME_DIRECTORY / "audiocpp_cli.exe").is_file():
        return "runtime"
    try:
        if family:
            return "ready" if cuda_device(runtime_home) else "hardware"
        if not ctranslate2.get_cuda_device_count():
            return "hardware"
        prepare_cuda()
        return "ready"
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        return "runtime"


def catalog_status(root: Path, runtime_home: Path, mode: ExecutionMode) -> dict:
    runtime = runtime_status(mode, runtime_home, "")
    gguf = runtime_status(mode, runtime_home, "gguf") if mode == ExecutionMode.REMOTE_CUDA else "unsupported"
    families = set()
    if gguf == "ready":
        try:
            families = available_families(runtime_home)
        except (KeyError, RuntimeError, OSError, ValueError, subprocess.SubprocessError):
            gguf = "runtime"
    return {
        model.key: {
            "bytes": installed_bytes(root, model),
            "managed": has_managed_files(root, model),
            "runtime": (
                "runtime" if gguf == "ready" and model.family not in families else gguf
            ) if model.family else runtime,
        }
        for model in CATALOG
    }


def serve_management(root: Path, runtime_home: Path, mode: ExecutionMode) -> int:
    stream = sys.stdin.buffer
    heard = monotonic()

    def monitor() -> None:
        nonlocal heard
        while stream.read(1) == b"\0":
            heard = monotonic()
        os._exit(1)

    def lease() -> None:
        while monotonic() - heard < LEASE_TIMEOUT:
            sleep(1)
        os._exit(1)

    def emit(event, **fields):
        print(json.dumps({"event": event, **fields}), flush=True)

    try:
        request = json.loads(stream.readline(1024))
        if request["version"] != 1:
            raise ValueError("Model management protocol mismatch.")
        action = request["action"]
        Thread(target=monitor, daemon=True).start()
        Thread(target=lease, daemon=True).start()
        if action != "status":
            model = CATALOG_BY_KEY[request["model"]]
            if mode not in model.modes:
                raise ValueError("The checkpoint is unavailable in this execution mode.")
            if action == "download":
                download(root, model, lambda current, total: emit("progress", current=current, total=total))
            elif action == "remove":
                remove(root, model)
            else:
                raise ValueError("Unknown model operation.")
        emit("status", models=catalog_status(root, runtime_home, mode), root=str(root))
        return 0
    except Exception as exc:
        emit("error", details=str(exc))
        return 1


def transact(mode, alias, action, model, progress, stopped):
    if mode == ExecutionMode.REMOTE_CUDA:
        command = [*ssh_command(alias), f"{REMOTE_COMMAND} --models"]
    else:
        executable = Path(sys.executable)
        if executable.name.lower() == "pythonw.exe":
            executable = executable.with_name("python.exe")
        command = [str(executable), "-u", "-m", "audio_transcript.model_service", mode.value]
    pending = Queue()
    done = Event()

    with TemporaryFile() as diagnostics, subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=diagnostics,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as process:
        def send():
            try:
                request = {"version": 1, "action": action, "model": model}
                process.stdin.write(json.dumps(request).encode("ascii") + b"\n")
                process.stdin.flush()
                while not done.wait(HEARTBEAT):
                    process.stdin.write(b"\0")
                    process.stdin.flush()
            except OSError:
                pass

        def receive():
            try:
                for line in process.stdout:
                    pending.put(line)
            finally:
                pending.put(None)

        sender = Thread(target=send)
        receiver = Thread(target=receive)
        sender.start()
        receiver.start()
        deadline = monotonic() + (90 if action == "download" else 35)
        try:
            while not stopped():
                try:
                    line = pending.get(timeout=0.15)
                except Empty:
                    if monotonic() > deadline:
                        raise RuntimeError("The model operation stopped responding.")
                    continue
                if line is None:
                    diagnostics.seek(0)
                    details = diagnostics.read(2048).decode("utf-8", errors="replace").strip()
                    raise RuntimeError(details or "The model worker exited without a response. Check worker setup and connectivity.")
                message = json.loads(line)
                match message["event"]:
                    case "progress":
                        deadline = monotonic() + 120
                        progress(message["current"], message["total"])
                    case "status":
                        return message
                    case "error":
                        raise ModelWorkerError(message["details"])
                    case _:
                        raise RuntimeError("Invalid model worker response.")
            raise TranscriptionCancelled("Model operation cancelled.")
        finally:
            done.set()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            sender.join()
            receiver.join()


if __name__ == "__main__":
    os._exit(serve_management(MODELS_DIR, MODELS_DIR.parent, ExecutionMode(sys.argv[1])))
