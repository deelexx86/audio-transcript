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
    assert "decode failed" in failures[0][1]
    assert completions == ["good"]
    assert finished == [False]
