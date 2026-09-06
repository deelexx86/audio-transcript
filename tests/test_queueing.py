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


def test_moves_preserve_selection_order_boundaries_and_sources(tmp_path):
    queue = QueueManager()
    paths = [tmp_path / f"{index}.amr" for index in range(5)]
    for path in paths:
        path.write_bytes(b"unchanged")
    a, b, c, d, e = queue.add_paths(paths).added
    queue.move_ids([b.id, c.id, e.id], -1)
    assert queue.items == [b, c, a, e, d]
    queue.move_ids([b.id, c.id], -1)
    assert queue.items == [b, c, a, e, d]
    queue.move_ids([b.id, c.id, e.id], 1)
    assert queue.items == [a, b, c, d, e]
    queue.move_ids([e.id], 1)
    assert queue.items == [a, b, c, d, e]
    assert all(path.read_bytes() == b"unchanged" for path in paths)
    assert queue.add_paths(paths).duplicates == 5


def test_sort_added_uses_full_timestamp_and_keeps_retry_order(tmp_path):
    from datetime import datetime, timedelta, timezone

    queue = QueueManager()
    paths = [tmp_path / name for name in ("z.amr", "a.wav", "b.ogg")]
    for path in paths:
        path.touch()
    before = datetime.now().astimezone()
    a, b, c = queue.add_paths(paths).added
    assert before <= a.added_at <= datetime.now().astimezone()
    a.added_at = datetime(2026, 9, 6, tzinfo=timezone.utc)
    b.added_at = a.added_at + timedelta(microseconds=1)
    c.added_at = a.added_at
    queue.sort_by("added", descending=True)
    assert queue.items == [b, a, c]
    queue.sort_by("added")
    assert queue.items == [a, c, b]  # Equal keys keep their previous order.
    a.status = QueueStatus.DONE
    c.status = QueueStatus.CANCELLED
    assert queue.retryable_items() == [c, b]
    queue.sort_by("file")
    assert queue.items == [b, c, a]
    a.duration, b.duration, c.duration = 120, 9, None
    queue.sort_by("duration")
    assert queue.items == [c, b, a]
    original_time = b.added_at
    assert queue.add_paths([b.source]).duplicates == 1
    assert b.added_at == original_time
