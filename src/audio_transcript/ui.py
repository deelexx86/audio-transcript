from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from audio_transcript.audio import SUPPORTED_EXTENSIONS, format_duration, probe_duration, scan_folder
from audio_transcript.paths import INBOX_DIR, ensure_runtime_directories
from audio_transcript.profiles import PROFILES, PROFILES_BY_KEY
from audio_transcript.queueing import ACTIVE_STATUSES, QueueItem, QueueManager, QueueStatus
from audio_transcript.settings import AppSettings, SettingsStore
from audio_transcript.worker import BatchWorker, WorkItem


class MainWindow(QMainWindow):
    def __init__(self, settings_store: SettingsStore | None = None) -> None:
        super().__init__()
        ensure_runtime_directories()
        self.settings_store = settings_store or SettingsStore()
        self.settings = self.settings_store.load()
        self.queue = QueueManager()
        self._row_by_id: dict[str, int] = {}
        self._processing = False
        self._closing_after_stop = False
        self._batch_stopped = False
        self._thread: QThread | None = None
        self._worker: BatchWorker | None = None
        self._build_ui()
        self._restore_settings()
        self._update_actions()

    def _build_ui(self) -> None:
        self.setWindowTitle("Audio Transcript")
        self.setAcceptDrops(True)
        self.setMinimumSize(760, 560)

        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Audio Transcript")
        title.setObjectName("title")
        subtitle = QLabel("Faithful transcripts from local audio")
        subtitle.setObjectName("subtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        badge = QLabel("LOCAL  •  OFFLINE")
        badge.setObjectName("badge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addLayout(title_block)
        header.addStretch()
        header.addWidget(badge)
        outer.addLayout(header)

        controls = QFrame()
        controls.setObjectName("controls")
        control_layout = QFormLayout(controls)
        control_layout.setContentsMargins(14, 12, 14, 12)
        control_layout.setHorizontalSpacing(18)
        control_layout.setVerticalSpacing(10)
        self.model_combo = QComboBox()
        for profile in PROFILES:
            self.model_combo.addItem(profile.display_name, profile.key)
        self.speaker_edit = QLineEdit()
        self.speaker_edit.setPlaceholderText("Optional default for newly added files")
        self.output_combo = QComboBox()
        self.output_combo.addItem("Workspace / transcripts", "workspace")
        self.output_combo.addItem("Same folder as source", "source")
        control_layout.addRow("Model", self.model_combo)
        control_layout.addRow("Speaker", self.speaker_edit)
        control_layout.addRow("Output", self.output_combo)
        outer.addWidget(controls)

        action_layout = QHBoxLayout()
        self.add_files_button = QPushButton("+ Files")
        self.add_folder_button = QPushButton("+ Folder")
        self.inbox_button = QPushButton("Inbox")
        self.remove_button = QPushButton("Remove")
        self.clear_button = QPushButton("Clear")
        action_layout.addWidget(self.add_files_button)
        action_layout.addWidget(self.add_folder_button)
        action_layout.addWidget(self.inbox_button)
        action_layout.addSpacing(12)
        action_layout.addWidget(self.remove_button)
        action_layout.addWidget(self.clear_button)
        action_layout.addStretch()
        outer.addLayout(action_layout)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        queue_panel = QWidget()
        queue_layout = QVBoxLayout(queue_panel)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(7)
        drop_hint = QLabel("Drop audio files here  •  OGG, MP3, M4A, WAV, WEBM")
        drop_hint.setObjectName("dropHint")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        queue_layout.addWidget(drop_hint)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("File", "Duration", "Speaker", "Status"))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(2, 190)
        self.table.setMinimumHeight(175)
        queue_layout.addWidget(self.table)
        self.splitter.addWidget(queue_panel)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_header = QHBoxLayout()
        self.preview_title = QLabel("Transcript preview")
        self.preview_title.setObjectName("sectionTitle")
        self.copy_button = QPushButton("Copy")
        self.open_folder_button = QPushButton("Open Folder")
        preview_header.addWidget(self.preview_title)
        preview_header.addStretch()
        preview_header.addWidget(self.copy_button)
        preview_header.addWidget(self.open_folder_button)
        preview_layout.addLayout(preview_header)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select a completed file to inspect its transcript.")
        self.preview.setMinimumHeight(130)
        preview_layout.addWidget(self.preview)
        self.splitter.addWidget(preview_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        outer.addWidget(self.splitter, 1)

        footer = QHBoxLayout()
        self.summary_label = QLabel("Queue is empty")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedWidth(210)
        self.stop_button = QPushButton("Stop")
        self.transcribe_button = QPushButton("Transcribe")
        self.transcribe_button.setObjectName("primaryButton")
        footer.addWidget(self.summary_label)
        footer.addStretch()
        footer.addWidget(self.progress_bar)
        footer.addWidget(self.stop_button)
        footer.addWidget(self.transcribe_button)
        outer.addLayout(footer)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.setStyleSheet(
            """
            QMainWindow { background: #f5f7fa; }
            QWidget { font-family: "Segoe UI"; font-size: 10pt; color: #1d2733; }
            QLabel#title { font-size: 20pt; font-weight: 650; color: #17202a; }
            QLabel#subtitle { color: #657282; }
            QLabel#badge { color: #176b4d; background: #e1f4eb; border: 1px solid #b8e4d1;
                           border-radius: 12px; padding: 5px 10px; font-size: 8pt; font-weight: 700; }
            QLabel#dropHint { color: #617080; background: #eef2f6; border: 1px dashed #aeb9c4;
                              border-radius: 5px; padding: 8px; }
            QLabel#sectionTitle { font-size: 11pt; font-weight: 600; }
            QFrame#controls { background: white; border: 1px solid #dbe1e7; border-radius: 6px; }
            QLineEdit, QComboBox, QPlainTextEdit, QTableWidget {
                background: white; border: 1px solid #cbd3dc; border-radius: 4px; padding: 4px;
                selection-background-color: #cfe0f4; selection-color: #17202a;
            }
            QTableWidget { padding: 0; gridline-color: #e4e8ed; }
            QHeaderView::section { background: #edf1f5; border: 0; border-bottom: 1px solid #cbd3dc;
                                   padding: 7px; font-weight: 600; }
            QPushButton { background: #ffffff; border: 1px solid #b9c3cd; border-radius: 4px;
                          padding: 6px 13px; }
            QPushButton:hover { background: #edf3fa; border-color: #8fa5bb; }
            QPushButton:disabled { color: #9da6af; background: #f2f3f5; border-color: #d8dde2; }
            QPushButton#primaryButton { background: #2563a6; color: white; border-color: #2563a6;
                                        font-weight: 600; padding-left: 18px; padding-right: 18px; }
            QPushButton#primaryButton:hover { background: #1e548e; }
            QPushButton#primaryButton:disabled { color: #9da6af; background: #f2f3f5;
                                                 border-color: #d8dde2; }
            QProgressBar { background: white; border: 1px solid #cbd3dc; border-radius: 4px;
                           text-align: center; min-height: 21px; }
            QProgressBar::chunk { background: #3d7dbb; border-radius: 3px; }
            """
        )

        self.add_files_button.clicked.connect(self._choose_files)
        self.add_folder_button.clicked.connect(self._choose_folder)
        self.inbox_button.clicked.connect(self._add_inbox)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self._clear_queue)
        self.transcribe_button.clicked.connect(self._start_batch)
        self.stop_button.clicked.connect(self._stop_batch)
        self.copy_button.clicked.connect(self._copy_transcript)
        self.open_folder_button.clicked.connect(self._open_output_folder)
        self.table.itemSelectionChanged.connect(self._show_selected)
        self.table.itemChanged.connect(self._table_item_changed)

    def _restore_settings(self) -> None:
        model_index = self.model_combo.findData(self.settings.model_profile)
        self.model_combo.setCurrentIndex(max(0, model_index))
        output_index = self.output_combo.findData(self.settings.output_mode)
        self.output_combo.setCurrentIndex(max(0, output_index))
        self.speaker_edit.setText(self.settings.default_speaker)
        self.resize(self.settings.window_width, self.settings.window_height)
        if self.settings.splitter_sizes:
            self.splitter.setSizes(self.settings.splitter_sizes)

    def _save_settings(self) -> None:
        current = AppSettings(
            model_profile=str(self.model_combo.currentData()),
            output_mode=str(self.output_combo.currentData()),
            last_source_directory=self.settings.last_source_directory,
            default_speaker=self.speaker_edit.text().strip(),
            window_width=self.width(),
            window_height=self.height(),
            splitter_sizes=self.splitter.sizes(),
        )
        try:
            self.settings_store.save(current)
        except OSError as exc:
            self.statusBar().showMessage(f"Could not save settings: {exc}", 8000)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        files: list[Path] = []
        for path in paths:
            files.extend(scan_folder(path) if path.is_dir() else [path])
        self._add_paths(files)
        event.acceptProposedAction()

    def _choose_files(self) -> None:
        initial = self.settings.last_source_directory or str(INBOX_DIR)
        pattern = " ".join(f"*{extension}" for extension in sorted(SUPPORTED_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add audio files", initial, f"Audio files ({pattern});;All files (*)"
        )
        if files:
            self.settings.last_source_directory = str(Path(files[0]).parent)
            self._add_paths(files)

    def _choose_folder(self) -> None:
        initial = self.settings.last_source_directory or str(INBOX_DIR)
        folder = QFileDialog.getExistingDirectory(self, "Add audio folder", initial)
        if folder:
            self.settings.last_source_directory = folder
            self._add_paths(scan_folder(folder))

    def _add_inbox(self) -> None:
        self._add_paths(scan_folder(INBOX_DIR))

    def _add_paths(self, paths: list[str | Path]) -> None:
        result = self.queue.add_paths(paths, self.speaker_edit.text())
        for item in result.added:
            try:
                item.duration = probe_duration(item.source)
            except Exception:
                item.duration = None
            self._append_row(item)
        messages: list[str] = []
        if result.added:
            messages.append(f"{len(result.added)} added")
        if result.duplicates:
            messages.append(f"{result.duplicates} duplicate skipped")
        if result.unsupported:
            messages.append(f"{result.unsupported} unsupported skipped")
        if result.missing:
            messages.append(f"{result.missing} missing skipped")
        if not messages:
            messages.append("No supported audio files found")
        self.statusBar().showMessage(" • ".join(messages), 6000)
        self._update_actions()
        if result.added and self.table.currentRow() < 0:
            self.table.selectRow(0)

    def _append_row(self, item: QueueItem) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        file_cell = QTableWidgetItem(item.source.name)
        file_cell.setData(Qt.ItemDataRole.UserRole, item.id)
        file_cell.setToolTip(str(item.source))
        file_cell.setFlags(file_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        duration_cell = QTableWidgetItem(format_duration(item.duration))
        duration_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        duration_cell.setFlags(duration_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        speaker_cell = QTableWidgetItem(item.speaker)
        status_cell = QTableWidgetItem(item.status.value)
        status_cell.setFlags(status_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        for column, cell in enumerate((file_cell, duration_cell, speaker_cell, status_cell)):
            self.table.setItem(row, column, cell)
        self._row_by_id[item.id] = row

    def _rebuild_row_map(self) -> None:
        self._row_by_id = {}
        for row in range(self.table.rowCount()):
            cell = self.table.item(row, 0)
            if cell:
                self._row_by_id[str(cell.data(Qt.ItemDataRole.UserRole))] = row

    def _selected_item(self) -> QueueItem | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        cell = self.table.item(row, 0)
        return self.queue.get(str(cell.data(Qt.ItemDataRole.UserRole))) if cell else None

    def _selected_ids(self) -> list[str]:
        ids: list[str] = []
        for selection in self.table.selectionModel().selectedRows():
            cell = self.table.item(selection.row(), 0)
            if cell:
                ids.append(str(cell.data(Qt.ItemDataRole.UserRole)))
        return ids

    def _remove_selected(self) -> None:
        selected = set(self._selected_ids())
        if not selected:
            return
        self.queue.remove_ids(selected)
        for row in range(self.table.rowCount() - 1, -1, -1):
            cell = self.table.item(row, 0)
            if cell and str(cell.data(Qt.ItemDataRole.UserRole)) in selected:
                self.table.removeRow(row)
        self._rebuild_row_map()
        self._show_selected()
        self._update_actions()

    def _clear_queue(self) -> None:
        self.queue.clear()
        self.table.setRowCount(0)
        self._row_by_id.clear()
        self.preview.clear()
        self.preview_title.setText("Transcript preview")
        self._update_actions()

    def _table_item_changed(self, cell: QTableWidgetItem) -> None:
        if cell.column() != 2 or self._processing:
            return
        id_cell = self.table.item(cell.row(), 0)
        if not id_cell:
            return
        item = self.queue.get(str(id_cell.data(Qt.ItemDataRole.UserRole)))
        if item:
            item.speaker = cell.text().strip()

    def _start_batch(self) -> None:
        retryable = self.queue.retryable_items()
        if self._processing or not retryable:
            return
        profile = PROFILES_BY_KEY[str(self.model_combo.currentData())]
        output_mode = str(self.output_combo.currentData())
        self._processing = True
        for item in retryable:
            item.status = QueueStatus.QUEUED
            item.progress = 0
            item.error = ""
            item.transcript = ""
            item.output_directory = None
            self._refresh_row(item)
        work = [WorkItem(item.id, item.source, item.speaker, item.duration) for item in retryable]
        self._thread = QThread(self)
        self._worker = BatchWorker(work, profile, output_mode)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.state_changed.connect(self._on_state_changed)
        self._worker.item_completed.connect(self._on_item_completed)
        self._worker.item_failed.connect(self._on_item_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._batch_stopped = False
        self._update_actions()
        self.statusBar().showMessage(f"Using local model: {profile.display_name}")
        self._thread.start()

    def _stop_batch(self) -> None:
        if self._worker and self._processing:
            self._worker.request_stop()
            self.stop_button.setEnabled(False)
            self.statusBar().showMessage(
                "Stop requested — the current safe inference boundary may take a moment.", 10000
            )

    def _on_state_changed(self, item_id: str, state: str, progress: int) -> None:
        item = self.queue.get(item_id)
        if not item:
            return
        item.status = QueueStatus(state)
        item.progress = progress
        self._refresh_row(item)
        if self._selected_item() is item:
            self._show_selected()
        self._update_actions()

    def _on_item_completed(self, item_id: str, payload: dict[str, object]) -> None:
        item = self.queue.get(item_id)
        if not item:
            return
        item.status = QueueStatus.DONE
        item.progress = 100
        item.transcript = str(payload["transcript"])
        item.language = str(payload["language"]) if payload["language"] else None
        item.duration = float(payload["duration"]) if payload["duration"] is not None else item.duration
        item.model_name = str(payload["model_name"])
        item.output_directory = Path(payload["output_directory"])
        self._refresh_row(item)
        if self._selected_item() is item:
            self._show_selected()
        self._update_actions()

    def _on_item_failed(self, item_id: str, message: str) -> None:
        item = self.queue.get(item_id)
        if not item:
            return
        item.status = QueueStatus.ERROR
        item.progress = 0
        item.error = message
        self._refresh_row(item)
        if self._selected_item() is item:
            self._show_selected()
        self._update_actions()

    def _on_worker_finished(self, stopped: bool) -> None:
        self._batch_stopped = stopped

    def _on_thread_finished(self) -> None:
        self._processing = False
        self._worker = None
        self._thread = None
        for item in self.queue.items:
            self._refresh_row(item)
        self._update_actions()
        self.statusBar().showMessage(
            "Processing stopped; queued files were preserved."
            if self._batch_stopped
            else "Batch finished.",
            8000,
        )
        if self._closing_after_stop:
            self.close()

    def _refresh_row(self, item: QueueItem) -> None:
        row = self._row_by_id.get(item.id)
        if row is None:
            return
        duration_cell = self.table.item(row, 1)
        speaker_cell = self.table.item(row, 2)
        status_cell = self.table.item(row, 3)
        if duration_cell:
            duration_cell.setText(format_duration(item.duration))
        if speaker_cell:
            flags = speaker_cell.flags()
            speaker_cell.setFlags(
                flags & ~Qt.ItemFlag.ItemIsEditable if self._processing else flags | Qt.ItemFlag.ItemIsEditable
            )
        if status_cell:
            status_cell.setText(
                f"{item.status.value} {item.progress}%"
                if item.status == QueueStatus.TRANSCRIBING
                else item.status.value
            )

    def _show_selected(self) -> None:
        item = self._selected_item()
        if not item:
            self.preview_title.setText("Transcript preview")
            self.preview.clear()
        else:
            self.preview_title.setText(f"Transcript — {item.source.name}")
            if item.status == QueueStatus.DONE:
                self.preview.setPlainText(item.transcript)
            elif item.status == QueueStatus.ERROR:
                self.preview.setPlainText(item.error)
            elif item.status == QueueStatus.CANCELLED:
                self.preview.setPlainText("Transcription was stopped. This file can be transcribed again.")
            else:
                self.preview.setPlainText(f"Source:\n{item.source}\n\nStatus: {item.status.value}")
        self._update_actions()

    def _copy_transcript(self) -> None:
        item = self._selected_item()
        if item and item.status == QueueStatus.DONE:
            QApplication.clipboard().setText(item.transcript)
            self.statusBar().showMessage("Transcript copied to the clipboard.", 4000)

    def _open_output_folder(self) -> None:
        item = self._selected_item()
        if item and item.output_directory and item.output_directory.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.output_directory)))

    def _update_actions(self) -> None:
        selected = self._selected_item()
        has_items = bool(self.queue.items)
        selected_ids = self._selected_ids()
        retryable = bool(self.queue.retryable_items())
        for widget in (
            self.add_files_button,
            self.add_folder_button,
            self.inbox_button,
            self.model_combo,
            self.speaker_edit,
            self.output_combo,
        ):
            widget.setEnabled(not self._processing)
        self.remove_button.setEnabled(not self._processing and bool(selected_ids))
        self.clear_button.setEnabled(not self._processing and has_items)
        self.transcribe_button.setEnabled(not self._processing and retryable)
        self.stop_button.setEnabled(self._processing and bool(self._worker))
        completed_selected = bool(selected and selected.status == QueueStatus.DONE)
        self.copy_button.setEnabled(completed_selected)
        self.open_folder_button.setEnabled(
            bool(completed_selected and selected and selected.output_directory)
        )

        counts = {status: 0 for status in QueueStatus}
        for item in self.queue.items:
            counts[item.status] += 1
        running = sum(counts[status] for status in ACTIVE_STATUSES)
        queued = counts[QueueStatus.QUEUED]
        parts = [f"{counts[QueueStatus.DONE]} completed", f"{running} running", f"{queued} queued"]
        if counts[QueueStatus.ERROR]:
            parts.append(f"{counts[QueueStatus.ERROR]} error")
        if counts[QueueStatus.CANCELLED]:
            parts.append(f"{counts[QueueStatus.CANCELLED]} cancelled")
        self.summary_label.setText(" • ".join(parts) if has_items else "Queue is empty")
        active = next((item for item in self.queue.items if item.status in ACTIVE_STATUSES), None)
        self.progress_bar.setValue(active.progress if active else (100 if has_items and not retryable else 0))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._processing:
            self._closing_after_stop = True
            self._stop_batch()
            event.ignore()
            return
        self._save_settings()
        event.accept()
