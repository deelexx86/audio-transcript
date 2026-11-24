from __future__ import annotations

import sys
from threading import Event

import pytest

from audio_transcript import transcription
from audio_transcript.acceleration import CudaUnavailable, ExecutionMode
from audio_transcript.profiles import FAST
from audio_transcript.remote_gpu import RemoteGPUError, RemoteTranscriber, ssh_command
from audio_transcript.settings import AppSettings, SettingsStore
from audio_transcript.transcription import LocalTranscriber, TranscriptionCancelled


def test_mode_and_profile_are_independent_and_legacy_defaults_are_local(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.path.write_text('{"model_profile":"fast"}', encoding="utf-8")
    assert store.load().execution_mode == ExecutionMode.CPU
    for mode in ExecutionMode:
        store.save(AppSettings(execution_mode=mode, model_profile="fast", ssh_alias="other-gpu"))
        loaded = store.load()
        assert (loaded.execution_mode, loaded.model_profile, loaded.ssh_alias) == (mode, "fast", "other-gpu")
    store.save(AppSettings(execution_mode=ExecutionMode.REMOTE_CUDA, ssh_alias="-oProxyCommand"))
    assert store.load().execution_mode == ExecutionMode.REMOTE_CUDA
    assert store.load().ssh_alias == ""
    with pytest.raises(ValueError):
        ssh_command("-oProxyCommand")


def test_local_cuda_requires_cuda_and_never_constructs_a_cpu_model(monkeypatch, tmp_path):
    arguments = []
    monkeypatch.setattr(transcription, "WhisperModel", lambda *args, **kwargs: arguments.append(kwargs))
    monkeypatch.setattr(transcription, "require_local_model", lambda _: tmp_path)
    monkeypatch.setattr(transcription, "prepare_cuda", lambda: None)
    LocalTranscriber(FAST, mode=ExecutionMode.LOCAL_CUDA)
    assert arguments[-1] == dict(device="cuda", device_index=0, compute_type="float16", local_files_only=True)

    def unavailable():
        raise CudaUnavailable("No CUDA device")

    monkeypatch.setattr(transcription, "prepare_cuda", unavailable)
    with pytest.raises(CudaUnavailable):
        LocalTranscriber(FAST, mode=ExecutionMode.LOCAL_CUDA)
    assert len(arguments) == 1


@pytest.fixture
def protocol_peer(tmp_path):
    # A separate process exercises actual Windows pipes and cleanup without SSH.
    peer = tmp_path / "peer.py"
    peer.write_text(
        """
import hashlib
import json
import sys

def emit(event, **fields):
    print(json.dumps(dict(event=event, **fields)), flush=True)

if sys.argv[1] == "disconnect":
    sys.stderr.write("Host key verification failed.\\n")
    sys.exit(255)

stream = sys.stdin.buffer
header = json.loads(stream.readline())
assert header["profile"] == "fast"
emit("ready", version=header["version"])
media = stream.read(header["size"])
emit("received")
emit("inference", duration=80.0)
emit("position", seconds=20.0)
if sys.argv[1] == "cancel":
    while stream.read(1):
        pass
    sys.exit(1)
if sys.argv[1] == "incomplete":
    sys.exit(1)
emit("result", text=hashlib.sha256(media).hexdigest(), language="ru")
""",
        encoding="utf-8",
    )
    return peer


def test_remote_protocol_transfers_binary_and_reuses_r1_inference_events(protocol_peer, tmp_path):
    from hashlib import sha256

    source = tmp_path / "Запись & test.wav"
    data = bytes(range(256)) * 3100
    source.write_bytes(data)
    transcriber = RemoteTranscriber(FAST, "gpu-test")
    transcriber.command = [sys.executable, str(protocol_peer), "success"]
    observations, progress = [], []
    result = transcriber.transcribe(
        source, duration=None, on_progress=progress.append, should_stop=lambda: False,
        on_timing=lambda *sample: observations.append(sample),
    )
    assert (result.text, result.language, result.duration) == (sha256(data).hexdigest(), "ru", 80.0)
    assert progress == [25, 100]
    assert observations == [
        ("Uploading", None, None), ("Preparing", None, None),
        ("Transcribing", None, 80.0), ("Transcribing", 20.0, 80.0),
    ]
    assert source.read_bytes() == data


@pytest.mark.parametrize("mode, expected", [
    ("disconnect", "Host key verification failed"),
    ("incomplete", "without a successful result"),
])
def test_remote_failure_discards_partial_results(protocol_peer, tmp_path, mode, expected):
    source = tmp_path / "test.wav"
    source.write_bytes(b"media")
    transcriber = RemoteTranscriber(FAST, "gpu-test")
    transcriber.command = [sys.executable, str(protocol_peer), mode]
    progress = []
    with pytest.raises(RemoteGPUError, match=expected):
        transcriber.transcribe(
            source, duration=None, on_progress=progress.append, should_stop=lambda: False,
        )
    assert 100 not in progress


@pytest.mark.parametrize("stop_phase", ["Uploading", "Transcribing"])
def test_remote_stop_during_upload_and_inference(protocol_peer, tmp_path, stop_phase):
    source = tmp_path / "test.wav"
    source.write_bytes(b"media")
    transcriber = RemoteTranscriber(FAST, "gpu-test")
    transcriber.command = [sys.executable, str(protocol_peer), "cancel"]
    stop = Event()
    progress = []

    def observe(phase, position, duration):
        if phase == stop_phase:
            stop.set()

    with pytest.raises(TranscriptionCancelled):
        transcriber.transcribe(
            source, duration=None, on_progress=progress.append, should_stop=stop.is_set, on_timing=observe,
        )
    assert 100 not in progress
    assert source.read_bytes() == b"media"
