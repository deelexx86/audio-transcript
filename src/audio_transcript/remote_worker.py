"""Single-use worker for the Windows SSH host. Standard output is JSON Lines."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryFile
from threading import Event, Thread
from time import monotonic, sleep

from av.error import FFmpegError

from audio_transcript.acceleration import ExecutionMode, prepare_cuda
from audio_transcript.gguf_asr import GgufTranscriber, available_families, cuda_device
from audio_transcript.model_catalog import CATALOG_BY_KEY
from audio_transcript.model_storage import REMOTE_MODELS, installed_bytes, model_lock
from audio_transcript.profiles import ModelMissingError, PROFILES_BY_KEY
from audio_transcript.remote_gpu import BLOCK_SIZE, LEASE_TIMEOUT, PROTOCOL
from audio_transcript.transcription import LocalTranscriber


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}), flush=True)


def serve(models_dir: Path, runtime_home: Path) -> int:
    stream = sys.stdin.buffer
    last_input = monotonic()
    stopped = Event()
    graceful_stop = False

    def enforce_lease() -> None:
        # Kill even during native inference or a stalled upload. The OS closes
        # the delete-on-close media handle and releases CUDA resources.
        while monotonic() - last_input < LEASE_TIMEOUT:
            sleep(1)
        disconnect()

    def receive_heartbeats() -> None:
        nonlocal last_input
        while stream.read(1) == b"\0":
            last_input = monotonic()
        disconnect()

    def disconnect() -> None:
        if graceful_stop:
            stopped.set()
        else:
            os._exit(1)

    Thread(target=enforce_lease, daemon=True).start()
    kind = "remote_connection"
    try:
        request = json.loads(stream.readline(1024))
        if request["version"] != PROTOCOL:
            raise ValueError("Protocol version mismatch. Rerun the remote GPU setup.")
        model = CATALOG_BY_KEY[request["profile"]]
        size = request["size"]
        if type(size) is not int or size <= 0:
            raise ValueError("Expected a nonempty source file.")
        with model_lock(models_dir, model) as model_dir:
            kind = "remote_model_missing"
            if installed_bytes(models_dir, model) is None:
                raise ModelMissingError()
            kind = "remote_cuda"
            if model.family:
                if not cuda_device(runtime_home):
                    raise RuntimeError("audio.cpp found no CUDA device.")
                if model.family not in available_families(runtime_home):
                    raise RuntimeError("The installed audio.cpp build lacks this ASR model family.")
            else:
                prepare_cuda()
            # The client starts sending media only after the model and CUDA
            # prerequisites have passed. No source filename or command arguments.
            with TemporaryFile(dir=runtime_home) as media:
                emit("ready", version=PROTOCOL)
                last_input = monotonic()
                kind = "remote_connection"
                remaining = size
                while remaining:
                    block = stream.read1(min(BLOCK_SIZE, remaining))
                    if not block:
                        return 1
                    media.write(block)
                    remaining -= len(block)
                    last_input = monotonic()
                graceful_stop = bool(model.family)
                Thread(target=receive_heartbeats, daemon=True).start()
                emit("received")
                media.seek(0)
                kind = "remote_cuda"
                if model.family:
                    transcriber = GgufTranscriber(model, model_dir, runtime_home)
                else:
                    transcriber = LocalTranscriber(
                        PROFILES_BY_KEY[model.key], mode=ExecutionMode.LOCAL_CUDA, models_dir=models_dir,
                    )

                def timing(_phase: str, position: float | None, duration: float | None) -> None:
                    if position is None:
                        emit("inference", duration=duration)
                    else:
                        emit("position", seconds=position)

                result = transcriber.transcribe(
                    media, duration=None, on_progress=lambda _: None,
                    should_stop=stopped.is_set, on_timing=timing,
                )
        emit("result", **asdict(result))
        return 0
    except ModelMissingError:
        emit("error", details="The selected model is missing or incomplete on the SSH host.", kind="remote_model_missing")
        return 1
    except FFmpegError as exc:
        emit("error", details=exc.strerror, kind="remote_media")
        return 1
    except Exception as exc:
        emit("error", details=str(exc), kind=kind)
        return 1


def main() -> None:
    runtime_home = Path(sys.argv[0]).resolve().parent
    if sys.argv[1:] == ["--models"]:
        from audio_transcript.model_service import serve_management

        os._exit(serve_management(REMOTE_MODELS, runtime_home, ExecutionMode.REMOTE_CUDA))
    code = 1
    try:
        code = serve(REMOTE_MODELS, runtime_home)
    finally:
        # A daemon may still be blocked in a stdin read after the result.
        os._exit(code)
