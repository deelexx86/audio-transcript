from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from audio_transcript.paths import SETTINGS_PATH


@dataclass(slots=True)
class AppSettings:
    model_profile: str = "accuracy"
    output_mode: str = "workspace"
    last_source_directory: str = ""
    default_speaker: str = ""
    window_width: int = 1040
    window_height: int = 760
    splitter_sizes: list[int] | None = None
    settings_expanded: bool = True
    interface_language: str = ""


class SettingsStore:
    def __init__(self, path: str | Path = SETTINGS_PATH) -> None:
        self.path = Path(path)

    def load(self) -> AppSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return AppSettings()
            allowed = AppSettings.__dataclass_fields__.keys()
            values = {key: value for key, value in data.items() if key in allowed}
            settings = AppSettings(**values)
            if settings.model_profile not in {"accuracy", "fast"}:
                settings.model_profile = "accuracy"
            if settings.output_mode not in {"workspace", "source"}:
                settings.output_mode = "workspace"
            settings.window_width = max(760, int(settings.window_width))
            settings.window_height = max(560, int(settings.window_height))
            if not isinstance(settings.splitter_sizes, list):
                settings.splitter_sizes = None
            if not isinstance(settings.settings_expanded, bool):
                settings.settings_expanded = True
            if settings.interface_language not in ("", "en", "ru", "es", "de"):
                settings.interface_language = ""
            return settings
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
