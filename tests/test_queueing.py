from __future__ import annotations

from pathlib import Path

from audio_transcript.queueing import QueueManager, QueueStatus


def test_queue_deduplicates_absolute_source_and_preserves_unicode(tmp_path: Path) -> None:
    source = tmp_path / "Переговоры.ogg"
    source.touch()
    queue = QueueManager()

    first = queue.add_paths([source], speaker="Евгений")
    second = queue.add_paths([source, source.parent / "." / source.name])

    assert len(first.added) == 1
    assert first.added[0].speaker == "Евгений"
    assert second.duplicates == 2
    assert len(queue.items) == 1


def test_queue_removal_does_not_touch_source(tmp_path: Path) -> None:
    source = tmp_path / "voice.wav"
    source.write_bytes(b"audio remains owned by user")
    queue = QueueManager()
    item = queue.add_paths([source]).added[0]

    queue.remove_ids([item.id])

    assert source.exists()
    assert queue.items == []


def test_retryable_state_selection(tmp_path: Path) -> None:
    paths = [tmp_path / f"{name}.wav" for name in ("queued", "done", "error", "cancelled")]
    for path in paths:
        path.touch()
    queue = QueueManager()
    items = list(queue.add_paths(paths).added)
    items[1].status = QueueStatus.DONE
    items[2].status = QueueStatus.ERROR
    items[3].status = QueueStatus.CANCELLED

    assert [item.source.stem for item in queue.retryable_items()] == ["queued", "error", "cancelled"]
