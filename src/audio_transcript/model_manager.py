"""Model catalog and lifecycle controls for the selected execution mode."""
from __future__ import annotations

from threading import Event

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QMessageBox, QProgressBar,
    QPushButton, QTextBrowser, QVBoxLayout,
)

from audio_transcript.acceleration import ExecutionMode
from audio_transcript.model_catalog import CATALOG
from audio_transcript.model_service import ModelWorkerError, transact
from audio_transcript.transcription import TranscriptionCancelled


class ModelOperation(QThread):
    status = Signal(dict)
    progress = Signal(int)
    failed = Signal(str, bool)
    cancelled = Signal()

    def __init__(self, parent, mode, alias, action, key):
        super().__init__(parent)
        self.mode, self.alias, self.action, self.key = mode, alias, action, key
        self.stop = Event()

    def run(self):
        try:
            status = transact(
                self.mode, self.alias, self.action, self.key,
                lambda current, total: self.progress.emit(min(99, current * 100 // total)),
                self.stop.is_set,
            )
        except TranscriptionCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc), isinstance(exc, ModelWorkerError))
        else:
            self.status.emit(status)


class ModelManager(QDialog):
    def __init__(self, parent, mode, alias, key):
        super().__init__(parent)
        self.mode, self.alias = mode, alias
        self.model_status = {}
        self.selected_key = None
        self.operation = None
        self.root = ""
        self.connected = False
        self.ssh_status = None
        self.setWindowTitle(self.tr("Model Manager"))
        self.resize(870, 500)
        outer = QVBoxLayout(self)
        self.location = QLabel()
        outer.addWidget(self.location)
        content = QHBoxLayout()
        self.catalog = QListWidget()
        for model in CATALOG:
            self.catalog.addItem(model.display_name)
        self.details = QTextBrowser()
        content.addWidget(self.catalog, 5)
        content.addWidget(self.details, 6)
        outer.addLayout(content)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        outer.addWidget(self.feedback)
        self.progress = QProgressBar()
        self.progress.hide()
        outer.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton(self.tr("Refresh"))
        self.download_button = QPushButton(self.tr("Download"))
        self.remove_button = QPushButton(self.tr("Remove files"))
        self.use_button = QPushButton(self.tr("Use selected model"))
        self.cancel_button = QPushButton(self.tr("Cancel operation"))
        self.close_button = QPushButton(self.tr("Close"))
        for button in (self.refresh_button, self.download_button, self.remove_button, self.use_button,
                       self.cancel_button, self.close_button):
            buttons.addWidget(button)
        outer.addLayout(buttons)
        self.catalog.currentRowChanged.connect(self.show_model)
        self.refresh_button.clicked.connect(lambda: self.start("status"))
        self.download_button.clicked.connect(lambda: self.start("download"))
        self.remove_button.clicked.connect(self.confirm_remove)
        self.use_button.clicked.connect(self.choose)
        self.cancel_button.clicked.connect(self.cancel_operation)
        self.close_button.clicked.connect(self.reject)
        self.catalog.setCurrentRow(next((i for i, model in enumerate(CATALOG) if model.key == key), 0))
        self.start("status")

    @property
    def model(self):
        return CATALOG[self.catalog.currentRow()]

    def mode_name(self, mode):
        return {
            ExecutionMode.CPU: self.tr("Local CPU"), ExecutionMode.LOCAL_CUDA: self.tr("Local NVIDIA GPU"),
            ExecutionMode.REMOTE_CUDA: self.tr("Remote NVIDIA GPU"),
        }[mode]

    def show_model(self):
        model = self.model
        status = self.model_status.get(model.key, {})
        supported = self.mode in model.modes
        installed = status.get("bytes")
        runtime = status.get("runtime")
        modes = ", ".join(self.mode_name(mode) for mode in model.modes)
        capabilities = [self.tr("Speech recognition")]
        if model.speakers:
            capabilities.append(self.tr("Anonymous speaker labels"))
        if model.timestamps:
            capabilities.append(self.tr("Native timestamps"))
        if model.streamed:
            capabilities.append(self.tr("Recorded-file streaming"))
        elif model.family == "gigaam_asr" and model.key.endswith("rnnt"):
            capabilities.append(self.tr("Russian speech"))
        else:
            capabilities.append(self.tr("Multilingual speech"))
        storage = self.tr("Unknown")
        if self.connected:
            storage = (self.tr("Installed · {size:.2f} GiB").format(size=installed / 2**30) if installed
                       else self.tr("Partial files") if status.get("managed") else self.tr("Missing"))
        eligibility = {
            "ready": self.tr("CUDA/runtime preflight passed") if self.mode != ExecutionMode.CPU else self.tr("Runtime available"),
            "runtime": self.tr("Runtime unavailable"),
            "hardware": self.tr("No compatible CUDA device detected"),
        }.get(runtime, self.tr("Unknown")) if supported else self.tr("Unavailable in this mode")
        use = self.tr("Ready for transcription") if supported and installed and runtime == "ready" else self.tr("Unavailable for transcription")
        amount = sum(entry.size for entry in model.files)
        source = self.tr("Checkpoint size · {size:.2f} GiB").format(size=amount / 2**30)
        engine = "audio.cpp 0.9.6 / CUDA" if model.family else "faster-whisper / CTranslate2"
        descriptions = {
            "accuracy": self.tr("Full-size multilingual Whisper checkpoint."),
            "fast": self.tr("Whisper checkpoint with a smaller decoder."),
            "qwen3-asr-0.6b": self.tr("Compact multilingual ASR with automatic language identification."),
            "qwen3-asr-1.7b": self.tr("Larger Qwen ASR checkpoint with automatic language identification."),
            "gigaam-v3-e2e-rnnt": self.tr("Russian RNN-T with punctuation and text normalization."),
            "gigaam-multilingual-large": self.tr("Large multilingual GigaAM checkpoint with a CTC decoder."),
            "parakeet-tdt-v3": self.tr("Multilingual FastConformer with a duration-aware decoder."),
            "vibevoice-asr": self.tr("Single-pass transcription with timestamped speaker turns."),
            "vibevoice-streaming-1.5b": self.tr("Compact stateful decoder for speaker-attributed recorded audio."),
            "vibevoice-streaming-7b": self.tr("Larger stateful decoder for speaker-attributed recorded audio."),
            "moss-transcribe-diarize": self.tr("Long-form ASR with anonymous, timestamped speaker segments."),
            "nemotron-transcribe": self.tr("Expert weights staged from host storage for CUDA inference."),
        }
        lines = [
            model.display_name, descriptions[model.key], "",
            self.tr("Capabilities") + " · " + ", ".join(capabilities),
            self.tr("Execution modes") + " · " + modes,
            self.tr("Weights") + " · " + storage,
            self.tr("Runtime and device") + " · " + eligibility,
            self.tr("Selection") + " · " + use, "",
            self.tr("Upstream") + " · " + model.upstream,
            self.tr("Checkpoint source") + " · " + model.repository + " @ " + model.revision,
            self.tr("License") + " · " + model.license,
            self.tr("Runtime") + " · " + engine,
            self.tr("Precision") + " · " + model.precision,
            source, *(entry.name for entry in model.files),
        ]
        if model.limit is not None:
            lines.append(self.tr("Application duration limit · {minutes} minutes").format(minutes=model.limit // 60))
        self.details.setPlainText("\n".join(lines))
        ssh_label = ""
        if self.mode == ExecutionMode.REMOTE_CUDA:
            ssh_label = {
                True: self.tr("SSH worker connected"),
                False: self.tr("SSH worker unavailable"),
                None: self.tr("SSH status unknown"),
            }[self.ssh_status]
        self.location.setText(
            f"{self.mode_name(self.mode)}{(' · ' + self.alias) if self.mode == ExecutionMode.REMOTE_CUDA else ''}"
            f"{(' · ' + ssh_label) if ssh_label else ''}"
            f"{(' · ' + self.root) if self.root else ''}"
        )
        idle = self.operation is None
        self.catalog.setEnabled(idle)
        self.refresh_button.setEnabled(idle)
        self.download_button.setEnabled(idle and self.connected and supported and not installed)
        self.remove_button.setEnabled(idle and self.connected and supported and bool(status.get("managed")))
        self.use_button.setEnabled(idle and supported and bool(installed) and runtime == "ready")
        self.cancel_button.setEnabled(not idle)
        self.close_button.setEnabled(idle)

    def start(self, action):
        if self.operation is not None:
            return
        self.feedback.setText({
            "status": self.tr("Checking model files and runtime…"),
            "download": self.tr("Downloading checkpoint…"),
            "remove": self.tr("Removing model files…"),
        }[action])
        self.progress.setRange(0, 0)
        self.progress.show()
        job = self.operation = ModelOperation(self, self.mode, self.alias, action, self.model.key)
        job.progress.connect(self.update_progress)
        job.status.connect(self.receive)
        job.failed.connect(self.failed)
        job.cancelled.connect(self.cancelled)
        job.finished.connect(self.finish)
        self.show_model()
        job.start()

    def confirm_remove(self):
        if QMessageBox.question(
            self, self.tr("Remove files"),
            self.tr("Remove the managed checkpoint files for {model}?").format(model=self.model.display_name),
        ) == QMessageBox.StandardButton.Yes:
            self.start("remove")

    def choose(self):
        self.selected_key = self.model.key
        self.accept()

    def update_progress(self, value):
        self.progress.setRange(0, 100)
        self.progress.setValue(value)

    def receive(self, response):
        self.connected = True
        self.ssh_status = True
        self.root = response["root"]
        self.model_status = response["models"]
        self.feedback.setText(self.tr("Model status updated."))

    def failed(self, details, reached_worker):
        self.ssh_status = reached_worker
        self.connected = False
        self.model_status = {}
        self.feedback.setText(self.tr("Model operation failed. Refresh to check the current status.") + "\n" + details)

    def cancelled(self):
        self.ssh_status = None
        self.connected = False
        self.model_status = {}
        self.feedback.setText(self.tr("Operation cancelled. Refresh to check the current status."))

    def finish(self):
        self.operation.deleteLater()
        self.operation = None
        self.progress.hide()
        self.show_model()

    def cancel_operation(self):
        if self.operation is not None:
            self.operation.stop.set()
            self.feedback.setText(self.tr("Cancelling…"))
            self.cancel_button.setEnabled(False)

    def reject(self):
        if self.operation is not None:
            self.cancel_operation()
        else:
            super().reject()
