from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from audio_transcript.settings import SettingsStore
from audio_transcript.queueing import QueueStatus
from audio_transcript.ui import MainWindow


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
