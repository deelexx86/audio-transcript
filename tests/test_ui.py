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
    assert window.size().height() == 600
    window.close()
