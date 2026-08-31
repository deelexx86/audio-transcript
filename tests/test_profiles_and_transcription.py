from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import audio_transcript.profiles as profiles_module
import audio_transcript.transcription as transcription_module
from audio_transcript.profiles import ACCURACY, ModelMissingError, model_is_ready, require_local_model
from audio_transcript.transcription import LocalTranscriber, TranscriptionCancelled


def create_model_files(root: Path, directory_name: str) -> Path:
    model = root / directory_name
    model.mkdir()
    for name in ("config.json", "model.bin", "tokenizer.json"):
        (model / name).touch()
    return model


def test_repository_local_model_discovery(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(profiles_module, "MODELS_DIR", tmp_path)
    expected = create_model_files(tmp_path, ACCURACY.directory_name)
    assert model_is_ready(ACCURACY)
    assert require_local_model(ACCURACY) == expected


def test_missing_model_error_is_actionable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(profiles_module, "MODELS_DIR", tmp_path)
    try:
        require_local_model(ACCURACY)
    except ModelMissingError as exc:
        assert "bootstrap_models.bat" in str(exc)
        assert str(tmp_path) in str(exc)
    else:
        raise AssertionError("missing model unexpectedly accepted")


def test_transcription_preserves_model_text_and_reports_progress(monkeypatch, tmp_path: Path) -> None:
    model_path = create_model_files(tmp_path, "model")
    monkeypatch.setattr(transcription_module, "require_local_model", lambda profile: model_path)

    class FakeModel:
        def __init__(self, path, **kwargs):
            assert Path(path) == model_path
            assert kwargs["local_files_only"] is True

        def transcribe(self, source):
            return iter(
                [
                    SimpleNamespace(text=" Добрый", end=1.0),
                    SimpleNamespace(text=" день.", end=2.0),
                ]
            ), SimpleNamespace(language="ru", duration=2.0)

    monkeypatch.setattr(transcription_module, "WhisperModel", FakeModel)
    progress: list[int] = []
    result = LocalTranscriber(ACCURACY).transcribe(
        tmp_path / "голос.ogg",
        duration=None,
        on_progress=progress.append,
        should_stop=lambda: False,
    )

    assert result.text == "Добрый день."
    assert result.language == "ru"
    assert progress == [50, 99, 100]


def test_transcription_cancellation_discards_partial_text(monkeypatch, tmp_path: Path) -> None:
    model_path = create_model_files(tmp_path, "model")
    monkeypatch.setattr(transcription_module, "require_local_model", lambda profile: model_path)

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, source):
            return iter([SimpleNamespace(text="partial", end=1.0)]), SimpleNamespace(
                language="en", duration=1.0
            )

    monkeypatch.setattr(transcription_module, "WhisperModel", FakeModel)
    transcriber = LocalTranscriber(ACCURACY)
    try:
        transcriber.transcribe(
            tmp_path / "voice.ogg",
            duration=1.0,
            on_progress=lambda value: None,
            should_stop=lambda: True,
        )
    except TranscriptionCancelled:
        pass
    else:
        raise AssertionError("cancellation was ignored")
