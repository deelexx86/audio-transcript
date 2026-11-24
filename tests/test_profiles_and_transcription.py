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
            self.feature_extractor = SimpleNamespace(sampling_rate=16000)
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
    import numpy as np
    monkeypatch.setattr(transcription_module, "decode_audio", lambda *args, **kwargs: np.zeros(32000, dtype=np.float32))
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
            self.feature_extractor = SimpleNamespace(sampling_rate=16000)

        def transcribe(self, source):
            return iter([SimpleNamespace(text="partial", end=1.0)]), SimpleNamespace(
                language="en", duration=1.0
            )

    monkeypatch.setattr(transcription_module, "WhisperModel", FakeModel)
    import numpy as np
    monkeypatch.setattr(transcription_module, "decode_audio", lambda *args, **kwargs: np.zeros(16000, dtype=np.float32))
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


def test_precise_observations_start_after_decode_and_preserve_text(monkeypatch, tmp_path):
    import numpy as np
    from test_timing import Clock
    from audio_transcript.timing import AttemptTiming

    clock = Clock()
    timing = AttemptTiming(clock=clock)
    monkeypatch.setattr(transcription_module, "require_local_model", lambda _: tmp_path)
    def decode(*args, **kwargs):
        clock.advance(40)
        return np.zeros(16000 * 120, dtype=np.float32)
    monkeypatch.setattr(transcription_module, "decode_audio", decode)
    class Model:
        def __init__(self, *args, **kwargs):
            self.feature_extractor = SimpleNamespace(sampling_rate=16000)
            clock.advance(60)
        def transcribe(self, audio):
            assert isinstance(audio, np.ndarray)
            def segments():
                for end in (10.25, 20.5, 30.75):
                    clock.advance(5)
                    yield SimpleNamespace(text=" faithful", end=end)
            return segments(), SimpleNamespace(duration=120, language="en")
    monkeypatch.setattr(transcription_module, "WhisperModel", Model)
    observations = []
    def on_timing(phase, position, duration):
        timing.set_phase(phase, duration=duration)
        if position is not None:
            timing.observe(position, duration)
        observations.append(timing.snapshot())
    result = LocalTranscriber(ACCURACY).transcribe(
        tmp_path / "synthetic.wav", duration=None, on_progress=lambda _: None,
        should_stop=lambda: False, on_timing=on_timing,
    )
    assert result.text == "faithful faithful faithful"
    assert observations[0].inference_started_at == 200
    assert observations[-1].processed == 30.75
    assert observations[-1].view(clock()).speed == 2.05
    assert observations[-1].view(clock()).elapsed == 115
