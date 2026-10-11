from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from audio_transcript.settings import SettingsStore
from audio_transcript.queueing import QueueStatus
from audio_transcript.ui import MainWindow


@pytest.fixture(autouse=True)
def english_system_language(monkeypatch):
    # Tests of English labels must be independent of the Windows display language.
    monkeypatch.setattr("audio_transcript.i18n.system_language", lambda: "en")


def test_video_file_picker_folder_inbox_and_drop(monkeypatch, tmp_path):
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDropEvent

    app = QApplication.instance() or QApplication([])
    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    sources = [tmp_path / name for name in ("picked.MP4", "folder.mkv", "inbox.mov", "dropped.avi")]
    for source in sources:
        source.touch()
    monkeypatch.setattr("audio_transcript.ui.probe_duration", lambda _: 1.0)
    def choose_files(parent, title, initial, filters):
        assert "video" in title
        assert all(f"*.{ext}" in filters for ext in ("mp4", "mkv", "mov", "avi", "wmv"))
        return [str(sources[0])], ""
    monkeypatch.setattr("audio_transcript.ui.QFileDialog.getOpenFileNames", choose_files)
    window._choose_files()
    monkeypatch.setattr("audio_transcript.ui.QFileDialog.getExistingDirectory", lambda *args: str(tmp_path))
    monkeypatch.setattr("audio_transcript.ui.scan_folder", lambda folder: [sources[1]] if folder == str(tmp_path) else [sources[2]])
    window._choose_folder()
    window._add_inbox()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(sources[3]))])
    event = QDropEvent(QPointF(0, 0), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(event)
    app.processEvents()
    assert event.isAccepted()
    assert [item.source for item in window.queue.items] == sources
    assert window.table.rowCount() == 4 and window.transcribe_button.isEnabled()
    window.close()


def test_main_window_workflow_controls_and_resize(monkeypatch, tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    window.show()
    app.processEvents()

    assert window.windowTitle() == "Audio Transcript"
    assert window.model_combo.count() == 2
    assert window.output_combo.count() == 2
    assert not window.transcribe_button.isEnabled()
    assert not window.stop_button.isEnabled()
    assert window.width() >= 760
    assert window.height() >= 560

    source = tmp_path / "пример.wav"
    source.touch()
    window._add_paths([source])
    app.processEvents()
    assert window.table.rowCount() == 1
    assert window.transcribe_button.isEnabled()
    assert window.table.item(0, 2).flags()

    item = window.queue.items[0]
    item.status = QueueStatus.DONE
    item.transcript = "Чистый текст"
    item.output_directory = tmp_path
    window._refresh_row(item)
    window._show_selected()
    assert window.copy_button.isEnabled()
    assert window.open_folder_button.isEnabled()
    window._copy_transcript()
    assert QApplication.clipboard().text() == "Чистый текст"

    opened: list[str] = []
    monkeypatch.setattr(
        "audio_transcript.ui.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )
    window._open_output_folder()
    assert [Path(path) for path in opened] == [tmp_path]

    window._on_state_changed(item.id, QueueStatus.CANCELLED.value, 0)
    assert "stopped" in window.preview.toPlainText().lower()

    window.resize(820, 600)
    app.processEvents()
    assert window.size().width() == 820
    assert window.size().height() >= 600
    assert window.table.height() >= window.table.minimumHeight()
    assert window.preview.height() >= window.preview.minimumHeight()
    assert window.splitter.height() >= sum(
        window.splitter.widget(index).minimumHeight() for index in range(2)
    ) + window.splitter.handleWidth()
    window.close()


def test_ordering_preserves_selection_preview_and_row_identity(tmp_path):
    from PySide6.QtCore import QItemSelectionModel, Qt
    from PySide6.QtTest import QTest

    app = QApplication.instance() or QApplication([])
    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    window.show()
    paths = [tmp_path / name for name in ("z.amr", "a.wav", "b.ogg")]
    for path in paths:
        path.touch()
    window._add_paths(paths)
    a, b, c = window.queue.items
    from datetime import timedelta
    b.added_at = a.added_at + timedelta(seconds=1)
    c.added_at = a.added_at + timedelta(seconds=2)
    a.status = QueueStatus.DONE
    a.transcript = "Selected transcript"
    window._refresh_row(a)
    window._show_selected()
    window.move_down_button.click()
    assert window.queue.items == [b, a, c]
    assert window._selected_item() is a
    assert window._selected_ids() == [a.id]
    assert window.preview.toPlainText() == a.transcript
    header = window.table.horizontalHeader()
    app.processEvents()
    # Exercise the actual header click, not Qt's independent visual-only sorting.
    from PySide6.QtCore import QPoint
    position = QPoint(header.sectionViewportPosition(0) + 10, header.height() // 2)
    QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=position)
    assert window.queue.items == [b, c, a]
    assert window._selected_item() is a
    window.table.item(0, 2).setText("Speaker B")
    assert b.speaker == "Speaker B"
    window._on_state_changed(c.id, QueueStatus.TRANSCRIBING.value, 37)
    assert window.table.item(1, 3).text() == "Transcribing 37%"
    window._sort_queue(4)
    assert window.queue.items == [a, b, c]
    window._sort_queue(4)
    assert window.queue.items == [c, b, a]
    assert not window.table.item(0, 4).flags() & Qt.ItemFlag.ItemIsEditable
    # Multiple selection survives re-rendering with the current preview intact.
    window.table.selectionModel().select(window.table.model().index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    window._move_selected(-1)
    assert set(window._selected_ids()) == {a.id, b.id}
    assert window._selected_item() is a
    order = list(window.queue.items)
    window._processing = True
    window._update_actions()
    assert not window.move_up_button.isEnabled()
    assert not header.isEnabled()
    window._sort_queue(0)
    window._move_selected(1)
    window._add_paths([tmp_path / "extra.amr"])
    assert window.queue.items == order
    window._processing = False
    window.close()


def test_worker_receives_displayed_order(tmp_path, monkeypatch):
    from PySide6.QtCore import QObject, Signal
    import time

    captured = []
    class RecordingWorker(QObject):
        state_changed = Signal(str, str, int)
        item_completed = Signal(str, object)
        item_failed = Signal(str, str)
        finished = Signal(bool)
        timing_changed = Signal(str, object)

        def __init__(self, items, profile, output_mode):
            super().__init__()
            captured.extend(item.source.name for item in items)

        def run(self):
            self.finished.emit(False)

    monkeypatch.setattr("audio_transcript.ui.BatchWorker", RecordingWorker)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    paths = [tmp_path / name for name in ("z.amr", "a.wav", "b.ogg")]
    for path in paths:
        path.touch()
    window._add_paths(paths)
    window._sort_queue(0)
    window.queue.items[1].status = QueueStatus.DONE
    window._start_batch()
    deadline = time.monotonic() + 5
    while window._processing and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not window._processing
    assert captured == ["a.wav", "z.amr"]
    window.close()


def test_ui_timer_without_callbacks_stop_terminal_and_batch_reset(tmp_path, monkeypatch):
    from PySide6.QtTest import QTest
    from test_timing import Clock
    from audio_transcript.timing import AttemptTiming
    app = QApplication.instance() or QApplication([])
    clock = Clock()
    window = MainWindow(SettingsStore(tmp_path / "settings.json"), timing_clock=clock)
    monkeypatch.setattr("audio_transcript.ui.probe_duration", lambda _: 120)
    sources = [tmp_path / name for name in ("first.wav", "second.wav")]
    for source in sources:
        source.touch()
    window._add_paths(sources)
    first, second = window.queue.items
    timing = AttemptTiming(clock=clock)
    window._on_timing_changed(first.id, timing.snapshot())
    window._on_state_changed(first.id, "Preparing", 0)
    clock.advance(8)
    QTest.qWait(600)
    assert window.elapsed_value.text() == "00:08"
    assert window.remaining_value.text() == "Unavailable"
    assert window._timing_timer.isActive()
    # Stop request must keep the actual phase and live clock until safe termination.
    class StopWorker:
        def request_stop(self):
            pass
    window._worker = StopWorker()
    window._processing = True
    window._stop_batch()
    assert first.status == QueueStatus.PREPARING
    assert window._timing_timer.isActive()
    timing.finish("Cancelled")
    window._on_timing_changed(first.id, timing.snapshot())
    window._on_state_changed(first.id, "Cancelled", 0)
    assert first.processing_seconds == 8
    assert not window._timing_timer.isActive()
    clock.advance(100)
    window._refresh_timing()
    assert window.elapsed_value.text() == "00:08"
    fresh = AttemptTiming(clock=clock)
    window._on_timing_changed(second.id, fresh.snapshot())
    window._on_state_changed(second.id, "Downloading", -1)
    assert window.elapsed_value.text() == "00:00"
    assert "second.wav" in window.timing_file_label.toolTip()
    fresh.finish("Error")
    window._on_timing_changed(second.id, fresh.snapshot())
    window._on_item_failed(second.id, "synthetic failure")
    assert second.processing_seconds == 0
    assert first.processing_seconds == 8
    window._processing = False
    window._worker = None
    window.close()


@pytest.mark.parametrize("code,elapsed,remaining,estimating,unavailable", [
    ("en", "Elapsed", "Remaining", "Estimating…", "Unavailable"),
    ("ru", "Прошло", "Осталось", "Оценивается…", "Недоступно"),
    ("es", "Transcurrido", "Restante", "Estimando…", "No disponible"),
    ("de", "Vergangen", "Verbleibend", "Wird geschätzt…", "Nicht verfügbar"),
])
def test_timing_localization_and_minimum_layout(code, elapsed, remaining, estimating, unavailable, tmp_path):
    from test_timing import Clock, warmed
    from audio_transcript.timing import AttemptTiming
    app = QApplication.instance() or QApplication([])
    clock, timing = warmed()
    window = MainWindow(SettingsStore(tmp_path / "settings.json"), timing_clock=clock)
    source = tmp_path / ("synthetic-recording-with-a-long-name-" * 4 + ".wav")
    source.touch()
    window._add_paths([source])
    item = window.queue.items[0]
    window._on_timing_changed(item.id, timing.snapshot())
    window.language_combo.setCurrentIndex(window.language_combo.findData(code))
    window.show()
    window.resize(760, window.minimumHeight())
    app.processEvents()
    assert window.elapsed_label.text() == elapsed
    assert window.remaining_label.text() == remaining
    assert window.remaining_value.text().startswith("≈")
    assert window._status_text(QueueStatus.TRANSCRIBING) in window.timing_file_label.text()
    assert "2.0" in window.speed_value.text() or "2,0" in window.speed_value.text()
    for widget in (window.elapsed_value, window.remaining_value, window.speed_value):
        assert widget.width() >= widget.fontMetrics().horizontalAdvance(widget.text())
        assert widget.mapTo(window.centralWidget(), widget.rect().bottomRight()).x() <= window.centralWidget().width()
    fresh = AttemptTiming(clock=clock)
    fresh.set_phase("Transcribing", duration=120)
    window._on_timing_changed(item.id, fresh.snapshot())
    assert window.remaining_value.text() == estimating
    clock.advance(31)
    window._refresh_timing()
    assert window.remaining_value.text() == unavailable
    fresh.finish("Done")
    window._on_timing_changed(item.id, fresh.snapshot())
    window.close()


def test_retry_selected_resets_attempt_duration_and_keeps_other_results(tmp_path, monkeypatch):
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtTest import QTest
    from audio_transcript.timing import AttemptTiming
    from test_timing import Clock
    clock = Clock()
    class RetryingWorker(QObject):
        state_changed = Signal(str, str, int)
        timing_changed = Signal(str, object)
        item_completed = Signal(str, object)
        item_failed = Signal(str, object)
        finished = Signal(bool)
        def __init__(self, items, profile, output_mode):
            super().__init__()
            self.items = items
        def run(self):
            item = self.items[0]
            timing = AttemptTiming(clock=clock)
            self.timing_changed.emit(item.id, timing.snapshot())
            self.state_changed.emit(item.id, "Preparing", 0)
            clock.advance(3)
            timing.finish("Error")
            self.timing_changed.emit(item.id, timing.snapshot())
            self.item_failed.emit(item.id, "synthetic error")
            self.finished.emit(False)
    monkeypatch.setattr("audio_transcript.ui.BatchWorker", RetryingWorker)
    monkeypatch.setattr("audio_transcript.ui.probe_duration", lambda _: 120)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(SettingsStore(tmp_path / "settings.json"), timing_clock=clock)
    for name in ("retry.wav", "done.wav"):
        path = tmp_path / name
        path.touch()
        window._add_paths([path])
    retry, done = window.queue.items
    retry.status, retry.processing_seconds = QueueStatus.ERROR, 200
    done.status, done.processing_seconds = QueueStatus.DONE, 400
    window.table.selectRow(0)
    window._retry_selected()
    assert retry.processing_seconds is None
    for _ in range(100):
        QTest.qWait(10)
        if not window._processing:
            break
    assert not window._processing
    assert retry.processing_seconds == 3
    assert done.processing_seconds == 400
    assert window.elapsed_value.text() == "00:03"
    assert not window._timing_timer.isActive()
    window.close()



def test_collapsible_settings_and_youtube_queue(monkeypatch, tmp_path):
    from PySide6.QtCore import Qt
    app = QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(store)
    window.show()
    app.processEvents()
    expanded_height = window.minimumHeight()
    window.settings_toggle.click()
    app.processEvents()
    assert not window.settings_panel.isVisible()
    assert window.minimumHeight() < expanded_height
    window.resize(800, 600)
    app.processEvents()
    assert window.splitter.height() >= sum(window.splitter.widget(i).minimumHeight() for i in range(2))
    window.youtube_edit.setText("https://youtu.be/jNQXAC9IVRw")
    window.add_youtube_button.click()
    assert window.table.rowCount() == 1
    assert window.queue.items[0].source_url == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    assert "YouTube" in window.table.item(0, 0).text()
    assert "https://" in window.preview.toPlainText()
    window.youtube_edit.setText("https://youtube.com/watch?v=jNQXAC9IVRw&t=5")
    window.add_youtube_button.click()
    assert window.table.rowCount() == 1
    window.youtube_edit.setText("https://example.com")
    window.add_youtube_button.click()
    assert "video link" in window.statusBar().currentMessage()
    window.close()
    assert store.load().settings_expanded is False
    reopened = MainWindow(store)
    reopened.show()
    app.processEvents()
    assert not reopened.settings_panel.isVisible()
    reopened.close()


def test_retry_selected_and_remove_completed_preserve_other_items(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    paths = [tmp_path / f"{i}.wav" for i in range(4)]
    for path in paths:
        path.write_bytes(b"source untouched")
    window._add_paths(paths)
    done, error, cancelled, queued = window.queue.items
    done.status, error.status, cancelled.status = QueueStatus.DONE, QueueStatus.ERROR, QueueStatus.CANCELLED
    output = tmp_path / "transcript.txt"
    output.write_text("completed transcript", encoding="utf-8")
    done.output_directory = tmp_path
    window.table.selectRow(1)
    window._update_actions()
    assert window.retry_selected_button.isEnabled()
    batches = []
    monkeypatch.setattr(window, "_run_items", lambda items: batches.append(list(items)))
    window.retry_selected_button.click()
    assert batches == [[error]]
    assert cancelled.status == QueueStatus.CANCELLED and queued.status == QueueStatus.QUEUED
    window._processing = True
    window._update_actions()
    assert not window.remove_completed_button.isEnabled()
    window._remove_completed()
    assert done in window.queue.items
    window._processing = False
    window._update_actions()
    window.remove_completed_button.click()
    assert window.queue.items == [error, cancelled, queued]
    assert window._selected_item() is error
    assert window.table.rowCount() == 3
    assert output.read_text(encoding="utf-8") == "completed transcript"
    assert all(path.read_bytes() == b"source untouched" for path in paths)
    assert window.queue.add_paths([paths[0]]).added
    window.close()
