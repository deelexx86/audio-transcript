from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "models"
INBOX_DIR = PROJECT_ROOT / "inbox"
TRANSCRIPTS_DIR = PROJECT_ROOT / "transcripts"
CONFIG_DIR = PROJECT_ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"


def ensure_runtime_directories() -> None:
    for path in (MODELS_DIR, INBOX_DIR, TRANSCRIPTS_DIR, CONFIG_DIR):
        path.mkdir(parents=True, exist_ok=True)
