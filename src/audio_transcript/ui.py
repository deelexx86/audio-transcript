from __future__ import annotations

from pathlib import Path
from time import monotonic

from PySide6.QtCore import QEvent, QItemSelectionModel, QThread, QTimer, Qt, QUrl
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
    QSizePolicy,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from audio_transcript.audio import SUPPORTED_EXTENSIONS, format_duration, probe_duration, scan_folder
from audio_transcript.errors import ProcessingFailure
from audio_transcript.i18n import LANGUAGES, language_manager
from audio_transcript.paths import INBOX_DIR, ensure_runtime_directories
from audio_transcript.profiles import PROFILES, PROFILES_BY_KEY
from audio_transcript.queueing import ACTIVE_STATUSES, AddResult, QueueItem, QueueManager, QueueStatus
from audio_transcript.settings import AppSettings, SettingsStore
from audio_transcript.worker import BatchWorker, WorkItem


class MainWindow(QMainWindow):
    def __init__(self, settings_store: SettingsStore | None = None) -> None:
        super().__init__()
        ensure_runtime_directories()
        self.settings_store = settings_store or SettingsStore()
        self.settings = self.settings_store.load()
        self.languages = language_manager()
        self.languages.set_language(self.settings.interface_language)
        self._ui_ready = False
        self._status_message = None
        self._status_deadline: float | None = None
        self.queue = QueueManager()
        self._row_by_id: dict[str, int] = {}
        self._sort_column: int | None = None
        self._sort_descending = False
        self._processing = False
        self._closing_after_stop = False
        self._batch_stopped = False
        self._thread: QThread | None = None
        self._worker: BatchWorker | None = None
        self._build_ui()
        self.setMinimumHeight(max(560, self.minimumSizeHint().height()))
        self._restore_settings()
        self._ui_ready = True
        self._retranslate_ui()
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
        self.subtitle = QLabel("Faithful transcripts from local audio and video")
        self.subtitle.setObjectName("subtitle")
        title_block.addWidget(title)
        title_block.addWidget(self.subtitle)
        self.badge = QLabel("LOCAL TRANSCRIPTION")
        self.badge.setObjectName("badge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addLayout(title_block)
        header.addStretch()
        header.addWidget(self.badge)
        outer.addLayout(header)

        self.settings_toggle = QPushButton("Hide settings")
        self.settings_toggle.setCheckable(True)
        self.settings_toggle.setChecked(True)
        self.settings_toggle.toggled.connect(self._toggle_settings)
        preferences = QHBoxLayout()
        self.settings_toggle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.settings_toggle.setMinimumWidth(150)
        preferences.addWidget(self.settings_toggle, 1)
        preferences.addSpacing(18)
        self.language_label = QLabel()
        preferences.addWidget(self.language_label)
        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(self.language_combo.findData(self.languages.language))
        self.language_combo.currentIndexChanged.connect(self._change_language)
        preferences.addWidget(self.language_combo)
        outer.addLayout(preferences)
        controls = self.settings_panel = QFrame()
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
        self.model_label = QLabel()
        control_layout.addRow(self.model_label, self.model_combo)
        self.speaker_label = QLabel()
        control_layout.addRow(self.speaker_label, self.speaker_edit)
        self.output_label = QLabel()
        control_layout.addRow(self.output_label, self.output_combo)
        outer.addWidget(controls)

        youtube_layout = QHBoxLayout()
        youtube_layout.addWidget(QLabel("YouTube"))
        self.youtube_edit = QLineEdit()
        self.youtube_edit.setPlaceholderText("Paste a video link")
        self.youtube_edit.setToolTip("Downloads audio when Transcribe starts; speech recognition stays local.")
        self.add_youtube_button = QPushButton("Add Link")
        youtube_layout.addWidget(self.youtube_edit, 1)
        youtube_layout.addWidget(self.add_youtube_button)
        outer.addLayout(youtube_layout)
        self.youtube_hint = QLabel("YouTube needs internet. Results save to Workspace / transcripts.")
        self.youtube_hint.setObjectName("subtitle")
        outer.addWidget(self.youtube_hint)

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
        self.drop_hint = QLabel("Drop audio or video files here")
        self.drop_hint.setToolTip("Supported formats: " + ", ".join(
            extension.removeprefix(".").upper() for extension in sorted(SUPPORTED_EXTENSIONS)
        ))
        self.drop_hint.setObjectName("dropHint")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        queue_layout.addWidget(self.drop_hint)
        ordering_layout = QHBoxLayout()
        self.move_up_button = QPushButton("Move Up")
        self.move_down_button = QPushButton("Move Down")
        self.retry_selected_button = QPushButton("Retry Selected")
        self.retry_selected_button.setToolTip("Retry only selected Error or Cancelled items.")
        self.remove_completed_button = QPushButton("Remove Completed")
        self.remove_completed_button.setToolTip("Remove Done rows; keep audio and transcript files.")
        ordering_layout.addWidget(self.move_up_button)
        ordering_layout.addWidget(self.move_down_button)
        ordering_layout.addWidget(self.retry_selected_button)
        ordering_layout.addWidget(self.remove_completed_button)
        ordering_layout.addStretch()
        queue_layout.addLayout(ordering_layout)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("File / Video", "Duration", "Speaker", "Status", "Added"))
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setToolTip("Click a column header to sort; click again to reverse.")
        self.table.horizontalHeader().sectionClicked.connect(self._sort_queue)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(2, 120)
        self.table.horizontalHeaderItem(4).setToolTip("Local date and time added to this queue")
        self.table.setMinimumHeight(175)
        queue_layout.addWidget(self.table)
        queue_panel.setMinimumHeight(queue_panel.minimumSizeHint().height())
        self.splitter.addWidget(queue_panel)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_header = QHBoxLayout()
        self.preview_title = QLabel("Transcript preview")
        self.preview_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.preview_title.setObjectName("sectionTitle")
        self.copy_button = QPushButton("Copy")
        self.open_folder_button = QPushButton("Open Folder")
        preview_header.addWidget(self.preview_title, 1)
        preview_header.addWidget(self.copy_button)
        preview_header.addWidget(self.open_folder_button)
        preview_layout.addLayout(preview_header)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select a completed file to inspect its transcript.")
        self.preview.setMinimumHeight(130)
        preview_layout.addWidget(self.preview)
        preview_panel.setMinimumHeight(preview_panel.minimumSizeHint().height())
        self.splitter.addWidget(preview_panel)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        outer.addWidget(self.splitter, 1)

        footer = QHBoxLayout()
        self.summary_label = QLabel("Queue is empty")
        self.summary_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.summary_label.setMinimumWidth(80)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedWidth(210)
        self.stop_button = QPushButton("Stop")
        self.transcribe_button = QPushButton("Transcribe")
        self.transcribe_button.setObjectName("primaryButton")
        footer.addWidget(self.summary_label, 1)
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
        self.add_youtube_button.clicked.connect(self._add_youtube)
        self.youtube_edit.returnPressed.connect(self._add_youtube)
        self.retry_selected_button.clicked.connect(self._retry_selected)
        self.remove_completed_button.clicked.connect(self._remove_completed)
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))
        self.transcribe_button.clicked.connect(self._start_batch)
        self.stop_button.clicked.connect(self._stop_batch)
        self.copy_button.clicked.connect(self._copy_transcript)
        self.open_folder_button.clicked.connect(self._open_output_folder)
        self.table.itemSelectionChanged.connect(self._show_selected)
        self.table.itemChanged.connect(self._table_item_changed)

    def _change_language(self) -> None:
        self.languages.set_language(str(self.language_combo.currentData()))
        self._retranslate_ui()
        self._save_settings()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange and getattr(self, "_ui_ready", False):
            self._retranslate_ui()
        super().changeEvent(event)

    def _status(self, source: str, timeout: int = 0, *, n: int = -1, **values) -> None:
        self._status_message = (source, n, values)
        self._status_deadline = monotonic() + timeout / 1000 if timeout else None
        self.statusBar().showMessage(self.tr(source, None, n).format(**values), timeout)

    def _retranslate_ui(self) -> None:
        self.language_label.setText(self.tr("Interface language"))
        self.subtitle.setText(self.tr('Faithful transcripts from local audio and video'))
        self.badge.setText(self.tr('LOCAL TRANSCRIPTION'))
        self.add_youtube_button.setText(self.tr('Add Link'))
        self.youtube_hint.setText(self.tr('YouTube needs internet. Results save to Workspace / transcripts.'))
        self.add_files_button.setText(self.tr('+ Files'))
        self.add_folder_button.setText(self.tr('+ Folder'))
        self.inbox_button.setText(self.tr('Inbox'))
        self.remove_button.setText(self.tr('Remove'))
        self.clear_button.setText(self.tr('Clear'))
        self.drop_hint.setText(self.tr('Drop audio or video files here'))
        self.move_up_button.setText(self.tr('Move Up'))
        self.move_down_button.setText(self.tr('Move Down'))
        self.retry_selected_button.setText(self.tr('Retry Selected'))
        self.remove_completed_button.setText(self.tr('Remove Completed'))
        self.copy_button.setText(self.tr('Copy'))
        self.open_folder_button.setText(self.tr('Open Folder'))
        self.stop_button.setText(self.tr('Stop'))
        self.transcribe_button.setText(self.tr('Transcribe'))
        self.speaker_edit.setPlaceholderText(self.tr('Optional default for newly added files'))
        self.youtube_edit.setPlaceholderText(self.tr('Paste a video link'))
        self.youtube_edit.setToolTip(self.tr('Downloads audio when Transcribe starts; speech recognition stays local.'))
        self.retry_selected_button.setToolTip(self.tr('Retry only selected Error or Cancelled items.'))
        self.remove_completed_button.setToolTip(self.tr('Remove Done rows; keep audio and transcript files.'))
        self.table.horizontalHeader().setToolTip(self.tr('Click a column header to sort; click again to reverse.'))
        self.table.horizontalHeaderItem(4).setToolTip(self.tr('Local date and time added to this queue'))
        self.preview.setPlaceholderText(self.tr('Select a completed file to inspect its transcript.'))
        self.model_label.setText(self.tr("Model"))
        self.speaker_label.setText(self.tr("Speaker"))
        self.output_label.setText(self.tr("Output"))
        self.model_combo.setItemText(0, self.tr("Accuracy — Whisper large-v3"))
        self.model_combo.setItemText(1, self.tr("Fast — Whisper large-v3-turbo"))
        self.output_combo.setItemText(0, self.tr("Workspace / transcripts"))
        self.output_combo.setItemText(1, self.tr("Same folder as source"))
        self.table.setHorizontalHeaderLabels([self.tr("File / Video"), self.tr("Duration"), self.tr("Speaker"), self.tr("Status"), self.tr("Added")])
        self.drop_hint.setToolTip(self.tr("Supported formats: {formats}").format(formats=", ".join(extension.removeprefix(".").upper() for extension in sorted(SUPPORTED_EXTENSIONS))))
        self.language_combo.setToolTip(self.tr("Interface language; speech language is detected automatically."))
        self.language_combo.setAccessibleName(self.tr("Interface language"))
        self._toggle_settings(self.settings_toggle.isChecked())
        self.table.blockSignals(True)
        try:
            for item in self.queue.items:
                self._refresh_row(item)
        finally:
            self.table.blockSignals(False)
        self._show_selected()
        if self._status_message and self.statusBar().currentMessage():
            source, n, values = self._status_message
            if source == "Using local model: {model}":
                values = {"model": self.model_combo.currentText()}
            timeout = max(1, int((self._status_deadline - monotonic()) * 1000)) if self._status_deadline else 0
            message = self._addition_message(values["result"]) if source is None else self.tr(source, None, n).format(**values)
            self.statusBar().showMessage(message, timeout)
        self.centralWidget().layout().activate()

    def _toggle_settings(self, expanded: bool) -> None:
        self.settings_panel.setVisible(expanded)
        summary = self.tr("Show settings · {model} · {output}").format(model=self.model_combo.currentText().split(" — ")[0], output=self.output_combo.currentText())
        self.settings_toggle.setText(self.tr("Hide settings") if expanded else summary)
        self.settings_toggle.setToolTip(self.settings_toggle.text())
        self.centralWidget().layout().invalidate()
        QTimer.singleShot(0, self._update_minimum_height)

    def _update_minimum_height(self) -> None:
        self.centralWidget().layout().activate()
        self.layout().activate()
        self.setMinimumHeight(max(560, self.minimumSizeHint().height()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_summary_text"):
            self._fit_summary()

    def _fit_summary(self) -> None:
        self.summary_label.setText(self.summary_label.fontMetrics().elidedText(
            self._summary_text, Qt.TextElideMode.ElideRight, self.summary_label.width()
        ))
        self.summary_label.setToolTip(self._summary_text)

    def _add_youtube(self) -> None:
        if self._processing:
            return
        try:
            item = self.queue.add_youtube(self.youtube_edit.text(), self.speaker_edit.text())
        except ValueError:
            self._status("Paste a YouTube video link (watch, youtu.be, or Shorts), not a playlist or channel.", 10000)
            return
        if item is None:
            self._status("This YouTube video is already in the queue.", 6000)
            return
        self._reset_sort_indicator()
        self._append_row(item)
        self.youtube_edit.clear()
        self.table.selectRow(self._row_by_id[item.id])
        self._status("Video queued. Transcribe downloads audio, then transcribes locally.", 6000)
        self._update_actions()

    def _restore_settings(self) -> None:
        model_index = self.model_combo.findData(self.settings.model_profile)
        self.model_combo.setCurrentIndex(max(0, model_index))
        output_index = self.output_combo.findData(self.settings.output_mode)
        self.output_combo.setCurrentIndex(max(0, output_index))
        self.speaker_edit.setText(self.settings.default_speaker)
        self.settings_toggle.setChecked(self.settings.settings_expanded)
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
            settings_expanded=self.settings_toggle.isChecked(),
            interface_language=self.languages.language,
        )
        try:
            self.settings_store.save(current)
        except OSError as exc:
            self._status("Could not save settings: {error}", 8000, error=exc)

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
            self, self.tr("Add audio or video files"), initial, self.tr("Audio and video files ({pattern});;All files (*)").format(pattern=pattern)
        )
        if files:
            self.settings.last_source_directory = str(Path(files[0]).parent)
            self._add_paths(files)

    def _choose_folder(self) -> None:
        initial = self.settings.last_source_directory or str(INBOX_DIR)
        folder = QFileDialog.getExistingDirectory(self, self.tr("Add audio or video folder"), initial)
        if folder:
            self.settings.last_source_directory = folder
            self._add_paths(scan_folder(folder))

    def _add_inbox(self) -> None:
        self._add_paths(scan_folder(INBOX_DIR))

    def _add_paths(self, paths: list[str | Path]) -> None:
        if self._processing:
            return
        result = self.queue.add_paths(paths, self.speaker_edit.text())
        if result.added:
            self._reset_sort_indicator()
        for item in result.added:
            try:
                item.duration = probe_duration(item.source)
            except Exception:
                item.duration = None
            self._append_row(item)
        self._status_message = (None, -1, {"result": result})
        self._status_deadline = monotonic() + 6
        self.statusBar().showMessage(self._addition_message(result), 6000)
        self._update_actions()
        if result.added and self.table.currentRow() < 0:
            self.table.selectRow(0)

    def _addition_message(self, result: AddResult) -> str:
        messages: list[str] = []
        if result.added:
            messages.append(self.tr("%n file(s) added", None, len(result.added)))
        if result.duplicates:
            messages.append(self.tr("%n duplicate(s) skipped", None, result.duplicates))
        if result.unsupported:
            messages.append(self.tr("%n unsupported file(s) skipped", None, result.unsupported))
        if result.missing:
            messages.append(self.tr("%n missing file(s) skipped", None, result.missing))
        if not messages:
            messages.append(self.tr("No supported audio or video files found"))
        return " • ".join(messages)

    def _append_row(self, item: QueueItem) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        file_cell = QTableWidgetItem(item.display_name)
        file_cell.setData(Qt.ItemDataRole.UserRole, item.id)
        file_cell.setToolTip(item.source_url or str(item.source))
        file_cell.setFlags(file_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        duration_cell = QTableWidgetItem(format_duration(item.duration))
        duration_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        duration_cell.setFlags(duration_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        speaker_cell = QTableWidgetItem(item.speaker)
        status_cell = QTableWidgetItem(self._status_text(item.status))
        status_cell.setFlags(status_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        added_cell = QTableWidgetItem(item.added_at.strftime("%Y-%m-%d %H:%M:%S"))
        added_cell.setFlags(added_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        added_cell.setToolTip(item.added_at.isoformat(timespec="microseconds"))
        for column, cell in enumerate((file_cell, duration_cell, speaker_cell, status_cell, added_cell)):
            self.table.setItem(row, column, cell)
        self._row_by_id[item.id] = row

    def _reset_sort_indicator(self) -> None:
        self._sort_column = None
        self.table.horizontalHeader().setSortIndicatorShown(False)

    def _move_selected(self, offset: int) -> None:
        if self._processing:
            return
        self.queue.move_ids(self._selected_ids(), offset)
        self._reset_sort_indicator()
        self._render_queue_order()

    def _sort_queue(self, column: int) -> None:
        if self._processing:
            return
        self._sort_descending = not self._sort_descending if self._sort_column == column else False
        self._sort_column = column
        self.queue.sort_by(
            ("file", "duration", "speaker", "status", "added")[column],
            descending=self._sort_descending,
        )
        header = self.table.horizontalHeader()
        header.setSortIndicator(
            column,
            Qt.SortOrder.DescendingOrder if self._sort_descending else Qt.SortOrder.AscendingOrder,
        )
        header.setSortIndicatorShown(True)
        self._render_queue_order()

    def _render_queue_order(self) -> None:
        selected_ids = set(self._selected_ids())
        current = self._selected_item()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self._row_by_id.clear()
        for item in self.queue.items:
            self._append_row(item)
            self._refresh_row(item)
        if current:
            self.table.setCurrentCell(
                self._row_by_id[current.id], 0, QItemSelectionModel.SelectionFlag.NoUpdate
            )
        for item_id in selected_ids:
            index = self.table.model().index(self._row_by_id[item_id], 0)
            self.table.selectionModel().select(
                index,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
        self.table.blockSignals(False)
        self._show_selected()

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
        self._remove_ids(set(self._selected_ids()))

    def _remove_completed(self) -> None:
        self._remove_ids({item.id for item in self.queue.items if item.status == QueueStatus.DONE})

    def _remove_ids(self, selected: set[str]) -> None:
        if self._processing:
            return
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
        if self._processing:
            return
        self._reset_sort_indicator()
        self.queue.clear()
        self.table.setRowCount(0)
        self._row_by_id.clear()
        self.preview.clear()
        self.preview_title.setText(self.tr("Transcript preview"))
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
            if self._sort_column == 2:
                self._reset_sort_indicator()

    def _start_batch(self) -> None:
        self._run_items(self.queue.retryable_items())

    def _retry_selected(self) -> None:
        selected = set(self._selected_ids())
        self._run_items([
            item for item in self.queue.items
            if item.id in selected and item.status in {QueueStatus.ERROR, QueueStatus.CANCELLED}
        ])

    def _run_items(self, retryable: list[QueueItem]) -> None:
        if self._processing or not retryable:
            return
        profile = PROFILES_BY_KEY[str(self.model_combo.currentData())]
        output_mode = str(self.output_combo.currentData())
        self._processing = True
        self._reset_sort_indicator()
        for item in retryable:
            item.status = QueueStatus.QUEUED
            item.progress = 0
            item.error = ""
            item.transcript = ""
            item.output_directory = None
            self._refresh_row(item)
        work = [WorkItem(item.id, item.source, item.speaker, item.duration, item.source_url) for item in retryable]
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
        self._show_selected()
        self._update_actions()
        self._status("Using local model: {model}", model=self.model_combo.currentText())
        self._thread.start()

    def _stop_batch(self) -> None:
        if self._worker and self._processing:
            self._batch_stopped = True
            self._worker.request_stop()
            self.stop_button.setEnabled(False)
            self._status(
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
        item.title = str(payload.get("title") or "")
        item.language = str(payload["language"]) if payload["language"] else None
        item.duration = float(payload["duration"]) if payload["duration"] is not None else item.duration
        item.model_name = str(payload["model_name"])
        item.output_directory = Path(payload["output_directory"])
        self._refresh_row(item)
        if self._selected_item() is item:
            self._show_selected()
        self._update_actions()

    def _on_item_failed(self, item_id: str, message: str | ProcessingFailure) -> None:
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
        if self._batch_stopped:
            self._status("Processing stopped; queued files were preserved.", 8000)
        else:
            self._status("Batch finished.", 8000)
        if self._closing_after_stop:
            self.close()

    def _status_text(self, status: QueueStatus) -> str:
        return {
            QueueStatus.QUEUED: self.tr("Queued"),
            QueueStatus.PREPARING: self.tr("Preparing"),
            QueueStatus.DOWNLOADING: self.tr("Downloading"),
            QueueStatus.RETRYING: self.tr("Waiting to retry"),
            QueueStatus.TRANSCRIBING: self.tr("Transcribing"),
            QueueStatus.SAVING: self.tr("Saving"),
            QueueStatus.DONE: self.tr("Done"),
            QueueStatus.ERROR: self.tr("Error"),
            QueueStatus.CANCELLED: self.tr("Cancelled"),
        }[status]

    def _refresh_row(self, item: QueueItem) -> None:
        row = self._row_by_id.get(item.id)
        if row is None:
            return
        self.table.item(row, 0).setText(item.display_name)
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
                f"{self._status_text(item.status)} {item.progress}%"
                if item.status in {QueueStatus.TRANSCRIBING, QueueStatus.DOWNLOADING} and item.progress >= 0
                else self._status_text(item.status)
            )

    def _show_selected(self) -> None:
        item = self._selected_item()
        if not item:
            self.preview_title.setText(self.tr("Transcript preview"))
            self.preview.clear()
        else:
            self.preview_title.setText(self.tr("Transcript — {name}").format(name=item.display_name))
            self.preview_title.setToolTip(item.display_name)
            if item.status == QueueStatus.DONE:
                if self.preview.toPlainText() != item.transcript:
                    self.preview.setPlainText(item.transcript)
            elif item.status == QueueStatus.ERROR:
                self.preview.setPlainText(self._failure_text(item.error))
            elif item.status == QueueStatus.CANCELLED:
                self.preview.setPlainText(self.tr("Transcription was stopped. This file can be transcribed again."))
            else:
                self.preview.setPlainText(self.tr("Source:\n{source}\n\nStatus: {status}").format(source=item.source_url or item.source, status=self._status_text(item.status)))
        self._update_actions()

    def _failure_text(self, failure: str | ProcessingFailure) -> str:
        if isinstance(failure, str):
            return failure
        explanations = {
            "transcription": self.tr("Transcription failed. Check that the file contains a readable audio track and that the local model is installed."),
            "model_missing": self.tr("The selected model is not installed. Run bootstrap_models.bat while online, then try again."),
            "bot_check": self.tr("YouTube requested an anti-bot check. The automatic retry failed. Try Retry Selected later; browser playback may still work."),
            "access_restricted": self.tr("YouTube requires access permissions. This app does not use accounts or browser cookies."),
            "unavailable": self.tr("This YouTube video is unavailable or restricted in your location."),
            "components": self.tr("Check Node.js 22+ or Deno 2.3+ and the yt-dlp[default] installation. See README for setup."),
            "network": self.tr("YouTube connection, timeout, or server error. Check connectivity and try Retry Selected later."),
            "request_rejected": self.tr("YouTube rejected the media request (HTTP 403). Try later; see README for downloader troubleshooting."),
            "formats": self.tr("YouTube returned no usable audio format. Check component versions and the diagnostic details."),
            "download_failed": self.tr("YouTube download failed. See the diagnostic details and README troubleshooting."),
        }
        return self.tr("{explanation}\n\nSource:\n{source}\n\nTechnical details:\n{details}").format(
            explanation=explanations.get(failure.kind, explanations["transcription"]),
            source=failure.source, details=failure.details,
        )

    def _copy_transcript(self) -> None:
        item = self._selected_item()
        if item and item.status == QueueStatus.DONE:
            QApplication.clipboard().setText(item.transcript)
            self._status("Transcript copied to the clipboard.", 4000)

    def _open_output_folder(self) -> None:
        item = self._selected_item()
        if item and item.output_directory and item.output_directory.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.output_directory)))

    def _update_actions(self) -> None:
        selected = self._selected_item()
        has_items = bool(self.queue.items)
        selected_ids = set(self._selected_ids())
        retryable = bool(self.queue.retryable_items())
        for widget in (
            self.add_files_button,
            self.add_folder_button,
            self.inbox_button,
            self.model_combo,
            self.speaker_edit,
            self.output_combo,
            self.youtube_edit,
            self.add_youtube_button,
        ):
            widget.setEnabled(not self._processing)
        self.remove_button.setEnabled(not self._processing and bool(selected_ids))
        self.retry_selected_button.setEnabled(not self._processing and any(
            item.id in selected_ids and item.status in {QueueStatus.ERROR, QueueStatus.CANCELLED}
            for item in self.queue.items
        ))
        self.remove_completed_button.setEnabled(not self._processing and any(
            item.status == QueueStatus.DONE for item in self.queue.items
        ))
        movable_up = any(
            item.id in selected_ids and index > 0
            and self.queue.items[index - 1].id not in selected_ids
            for index, item in enumerate(self.queue.items)
        )
        movable_down = any(
            item.id in selected_ids and index + 1 < len(self.queue.items)
            and self.queue.items[index + 1].id not in selected_ids
            for index, item in enumerate(self.queue.items)
        )
        self.move_up_button.setEnabled(not self._processing and movable_up)
        self.move_down_button.setEnabled(not self._processing and movable_down)
        self.table.horizontalHeader().setEnabled(not self._processing)
        self.clear_button.setEnabled(not self._processing and has_items)
        self.transcribe_button.setEnabled(not self._processing and retryable)
        self.stop_button.setEnabled(self._processing and bool(self._worker) and not self._batch_stopped)
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
        parts = [self.tr("%n completed", None, counts[QueueStatus.DONE]), self.tr("%n running", None, running), self.tr("%n queued", None, queued)]
        if counts[QueueStatus.ERROR]:
            parts.append(self.tr("%n error(s)", None, counts[QueueStatus.ERROR]))
        if counts[QueueStatus.CANCELLED]:
            parts.append(self.tr("%n cancelled", None, counts[QueueStatus.CANCELLED]))
        self._summary_text = " • ".join(parts) if has_items else self.tr("Queue is empty")
        self._fit_summary()
        active = next((item for item in self.queue.items if item.status in ACTIVE_STATUSES), None)
        self.progress_bar.setRange(0, 0 if active and active.progress < 0 else 100)
        self.progress_bar.setValue(active.progress if active else (100 if has_items and not retryable else 0))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._processing:
            self._closing_after_stop = True
            self._stop_batch()
            event.ignore()
            return
        self._save_settings()
        event.accept()
