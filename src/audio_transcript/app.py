from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from audio_transcript.ui import MainWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audio Transcript local desktop application")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Start the window briefly and exit; intended for installation verification.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Audio Transcript")
    app.setOrganizationName("Audio Transcript")
    window = MainWindow()
    window.show()
    if args.smoke_test:
        QTimer.singleShot(350, window.close)
    return app.exec()
