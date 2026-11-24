from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from threading import Event

import pytest
from PySide6.QtWidgets import QApplication

from audio_transcript.acceleration import ExecutionMode
from audio_transcript.artifacts import write_artifacts
from audio_transcript.gguf_asr import segments_from_rows
from audio_transcript.model_catalog import CATALOG, CATALOG_BY_KEY, CheckpointFile
from audio_transcript.model_manager import ModelManager
from audio_transcript.model_storage import download, has_managed_files, installed_bytes, model_lock, remove
from audio_transcript.settings import AppSettings, SettingsStore
from audio_transcript.transcription import SpeakerSegment


def test_catalog_selection_round_trips_without_changing_explicit_mode(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    for entry in CATALOG:
        assert entry.files and all(file.size > 0 for file in entry.files)
        assert ExecutionMode.REMOTE_CUDA in entry.modes
        assert (ExecutionMode.CPU in entry.modes) == (not entry.family)
        store.save(AppSettings(model_profile=entry.key, execution_mode=ExecutionMode.REMOTE_CUDA))
        assert store.load().model_profile == entry.key
        assert store.load().execution_mode == ExecutionMode.REMOTE_CUDA


def test_checkpoint_lifecycle_preserves_unknown_files_and_locks_in_use_weights(tmp_path, monkeypatch):
    package = replace(CATALOG[2], files=(CheckpointFile("checkpoint.gguf", 4, sha256(b"GGUF").hexdigest()),))
    model_dir = tmp_path / package.directory_name
    model_dir.mkdir()
    (model_dir / "checkpoint.gguf.partial").write_bytes(b"GG")
    (model_dir / "unrelated").write_text("untouched")
    assert installed_bytes(tmp_path, package) is None
    assert has_managed_files(tmp_path, package)

    class Response:
        status = 206
        headers = {"Content-Range": "bytes 2-3/4"}

        def __enter__(self):
            self.remaining = b"UF"
            return self

        def __exit__(self, *_):
            pass

        def read(self, _):
            data, self.remaining = self.remaining, b""
            return data

    requests = []
    monkeypatch.setattr("audio_transcript.model_storage.urlopen", lambda request, **_: requests.append(request) or Response())
    updates = []
    download(tmp_path, package, lambda current, total: updates.append((current, total)))
    assert requests[0].get_header("Range") == "bytes=2-"
    assert updates[-1] == (4, 4)
    assert installed_bytes(tmp_path, package) == 4
    with model_lock(tmp_path, package):
        with pytest.raises(RuntimeError, match="in use"):
            remove(tmp_path, package)
    remove(tmp_path, package)
    assert not has_managed_files(tmp_path, package)
    assert (model_dir / "unrelated").read_text() == "untouched"


def test_speaker_output_keeps_plain_utf8_and_does_not_generate_missing_timestamps(tmp_path):
    segments = segments_from_rows([
        {"speaker_id": "S01", "start_seconds": 1.1, "end_seconds": 2, "text": "Здравствуйте."},
        {"speaker": "S02", "text": "Hello."},
        {"speaker": "S02", "start": 5, "end": 2, "text": "Yes."},
    ], duration=10)
    assert segments[-1] == SpeakerSegment("S02", "Yes.")
    report = write_artifacts(
        source="Разговор.wav", transcript="Здравствуйте. Hello. Yes.", processed_at=datetime.now(),
        duration=10, language=None, speaker="", model_name="moss-transcribe-diarize", output_mode="workspace",
        workspace=tmp_path, execution_mode=ExecutionMode.REMOTE_CUDA, precision="CUDA BF16",
        speaker_segments=segments,
    )
    assert report.text_path.read_text(encoding="utf-8") == "Здравствуйте. Hello. Yes.\n"
    assert report.speakers_path.read_text(encoding="utf-8").splitlines() == [
        "[00:00:01.100–00:00:02.000] S01: Здравствуйте.", "S02: Hello.", "S02: Yes.",
    ]
    assert "SSH, CUDA BF16" in report.markdown_path.read_text(encoding="utf-8")


def test_model_dialog_enables_use_only_for_installed_ready_weights(monkeypatch):
    app = QApplication.instance() or QApplication([])
    returned = Event()
    state = {"bytes": 123, "runtime": "ready", "managed": True}

    def status(*_):
        returned.set()
        return {"models": {CATALOG[2].key: state}, "root": r"D:\models\audio-transcript"}

    monkeypatch.setattr("audio_transcript.model_manager.transact", status)
    manager = ModelManager(None, ExecutionMode.REMOTE_CUDA, "gpu-tts", CATALOG[2].key)
    assert returned.wait(3)
    manager.operation.wait(3000)
    app.processEvents()
    assert manager.catalog.count() == len(CATALOG_BY_KEY)
    assert manager.use_button.isEnabled() and manager.remove_button.isEnabled()
    assert not manager.download_button.isEnabled()
    manager.catalog.setCurrentRow(3)
    assert not manager.use_button.isEnabled()
    assert manager.download_button.isEnabled()
    manager.close()

def test_remote_preflight_distinguishes_absent_loader_from_installed_weights(tmp_path, monkeypatch):
    from audio_transcript import model_service

    model = CATALOG_BY_KEY["moss-transcribe-diarize"]
    monkeypatch.setattr(model_service, "runtime_status", lambda *_: "ready")
    monkeypatch.setattr(model_service, "available_families", lambda _: {"qwen3_asr"})
    monkeypatch.setattr(
        model_service, "installed_bytes", lambda _, entry: 123 if entry.key == model.key else None,
    )

    status = model_service.catalog_status(tmp_path, tmp_path, ExecutionMode.REMOTE_CUDA)
    assert status[model.key]["bytes"] == 123
    assert status[model.key]["runtime"] == "runtime"
    assert status["qwen3-asr-0.6b"]["runtime"] == "ready"
    assert status["qwen3-asr-0.6b"]["bytes"] is None

def test_gguf_refuses_over_limit_recording_before_launch(monkeypatch, tmp_path):
    import numpy as np

    from audio_transcript import gguf_asr

    model = replace(CATALOG_BY_KEY["moss-transcribe-diarize"], limit=1)
    monkeypatch.setattr(gguf_asr, "decode_audio", lambda *_args, **_kwargs: np.zeros(16001))
    engine = gguf_asr.GgufTranscriber(model, tmp_path, tmp_path)
    with pytest.raises(ValueError, match="accepts at most 1 seconds"):
        engine.transcribe(
            "long.wav", duration=None, on_progress=lambda _: None, should_stop=lambda: False,
        )
    assert not list(tmp_path.iterdir())

def test_nemotron_preserves_decoder_speaker_tags_when_alignment_is_unavailable():
    from audio_transcript.gguf_asr import NEMOTRON_SPEAKER, nemotron_speaker_text

    raw = "<spk:0> первый ответ <|spk:3|> second answer."
    assert nemotron_speaker_text(raw) == (
        SpeakerSegment("spk:0", "первый ответ"),
        SpeakerSegment("spk:3", "second answer."),
    )
    assert " ".join(NEMOTRON_SPEAKER.sub(" ", raw).split()) == "первый ответ second answer."
