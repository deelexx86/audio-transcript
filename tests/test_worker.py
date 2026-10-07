from __future__ import annotations

from pathlib import Path

import audio_transcript.worker as worker_module
from audio_transcript.artifacts import ArtifactResult
from audio_transcript.profiles import ACCURACY
from audio_transcript.transcription import TranscriptionResult
from audio_transcript.worker import BatchWorker, WorkItem


def test_batch_worker_isolates_file_error_and_continues(monkeypatch, tmp_path: Path) -> None:
    bad = tmp_path / "bad.ogg"
    good = tmp_path / "good.ogg"

    def fake_probe(path: Path, **kwargs) -> float:
        if path == bad:
            raise RuntimeError("decode failed")
        return 2.0

    class FakeTranscriber:
        def __init__(self, profile):
            self.profile = profile

        def transcribe(self, source, **kwargs):
            kwargs["on_progress"](100)
            return TranscriptionResult("Success", "en", 2.0)

    output = tmp_path / "output"
    output.mkdir()
    text_path = output / "transcript.txt"
    markdown_path = output / "transcript.md"
    monkeypatch.setattr(worker_module, "probe_duration", fake_probe)
    monkeypatch.setattr(worker_module, "LocalTranscriber", FakeTranscriber)
    monkeypatch.setattr(
        worker_module,
        "write_artifacts",
        lambda **kwargs: ArtifactResult(output, text_path, markdown_path),
    )

    worker = BatchWorker(
        [WorkItem("bad", bad, "", None), WorkItem("good", good, "", None)],
        ACCURACY,
        "workspace",
    )
    failures: list[tuple[str, str]] = []
    completions: list[str] = []
    finished: list[bool] = []
    worker.item_failed.connect(lambda item_id, message: failures.append((item_id, message)))
    worker.item_completed.connect(lambda item_id, payload: completions.append(item_id))
    worker.finished.connect(finished.append)

    worker.run()

    assert failures[0][0] == "bad"
    assert "decode failed" in failures[0][1].details
    assert completions == ["good"]
    assert finished == [False]



def test_youtube_success_saves_metadata_in_workspace_and_cleans_temp(monkeypatch, tmp_path):
    from audio_transcript.youtube import DownloadedAudio
    from audio_transcript.artifacts import write_artifacts

    config = tmp_path / "config"
    outputs = tmp_path / "transcripts"
    monkeypatch.setattr(worker_module, "CONFIG_DIR", config)
    monkeypatch.setattr(worker_module, "require_local_model", lambda _: None)
    downloaded = []
    def fake_download(url, directory, **kwargs):
        path = directory / "audio.webm"
        path.write_bytes(b"temporary audio")
        downloaded.append(path)
        kwargs["on_progress"](50)
        return DownloadedAudio(path, "Video title")

    class FakeTranscriber:
        def __init__(self, profile):
            pass

        def transcribe(self, source, **kwargs):
            assert source == downloaded[0] and source.exists()
            return TranscriptionResult("Faithful words", "en", 19.0)

    monkeypatch.setattr(worker_module, "download_audio", fake_download)
    monkeypatch.setattr(worker_module, "probe_duration", lambda *args, **kwargs: 19.0)
    monkeypatch.setattr(worker_module, "LocalTranscriber", FakeTranscriber)
    monkeypatch.setattr(worker_module, "write_artifacts", lambda **kwargs: write_artifacts(workspace=outputs, **kwargs))
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    worker = BatchWorker([WorkItem("video", Path("youtube-jNQXAC9IVRw.webm"), "", None, url)], ACCURACY, "source")
    completed, failed = [], []
    worker.item_completed.connect(lambda _, payload: completed.append(payload))
    worker.item_failed.connect(lambda _, error: failed.append(error))
    worker.run()
    assert not failed
    assert len(completed) == 1
    directory = completed[0]["output_directory"]
    assert directory.is_relative_to(outputs)
    assert (directory / "transcript.txt").read_text(encoding="utf-8") == "Faithful words\n"
    markdown = (directory / "transcript.md").read_text(encoding="utf-8")
    assert f"URL: {url}" in markdown and "Title: Video title" in markdown
    assert str(config) not in markdown
    assert not downloaded[0].exists()
    assert list(config.iterdir()) == []


def test_youtube_download_failure_cleans_partial_and_continues(monkeypatch, tmp_path):
    from audio_transcript.transcription import TranscriptionCancelled
    config = tmp_path / "config"
    monkeypatch.setattr(worker_module, "CONFIG_DIR", config)
    monkeypatch.setattr(worker_module, "require_local_model", lambda _: None)
    seen = []
    def fake_download(url, directory, **kwargs):
        (directory / "audio.part").write_bytes(b"partial")
        seen.append(directory)
        raise RuntimeError("network failed")

    monkeypatch.setattr(worker_module, "download_audio", fake_download)
    monkeypatch.setattr(worker_module, "probe_duration", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("local decoded boundary")))
    worker = BatchWorker([
        WorkItem("video", Path("video.webm"), "", None, "https://youtu.be/jNQXAC9IVRw"),
        WorkItem("local", tmp_path / "local.wav", "", None),
    ], ACCURACY, "workspace")
    failed = []
    worker.item_failed.connect(lambda item_id, _: failed.append(item_id))
    worker.run()
    assert failed == ["video", "local"]
    assert not seen[0].exists()

    def cancel_download(url, directory, **kwargs):
        (directory / "audio.part").touch()
        kwargs["on_retry"]()
        worker.request_stop()
        raise TranscriptionCancelled("stopped")

    worker = BatchWorker(worker.items, ACCURACY, "workspace")
    monkeypatch.setattr(worker_module, "download_audio", cancel_download)
    states, finished = [], []
    worker.state_changed.connect(lambda item_id, state, _: states.append((item_id, state)))
    worker.finished.connect(finished.append)
    worker.run()
    assert ("video", "Cancelled") in states
    assert ("video", "Waiting to retry") in states
    assert not any(item_id == "local" for item_id, _ in states)
    assert finished == [True]
    assert list(config.iterdir()) == []



def test_missing_model_prevents_youtube_download(monkeypatch, tmp_path):
    from audio_transcript.profiles import ModelMissingError

    def missing(profile):
        raise ModelMissingError("Model is not installed")

    def unexpected_download(*args, **kwargs):
        raise AssertionError("Must not download before checking the model")

    monkeypatch.setattr(worker_module, "require_local_model", missing)
    monkeypatch.setattr(worker_module, "download_audio", unexpected_download)
    worker = BatchWorker([WorkItem("video", Path("youtube-jNQXAC9IVRw"), "", None,
                                  "https://youtu.be/jNQXAC9IVRw")], ACCURACY, "workspace")
    errors = []
    worker.item_failed.connect(lambda _, message: errors.append(message))
    worker.run()
    assert len(errors) == 1 and "Model is not installed" in errors[0].details
