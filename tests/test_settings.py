from __future__ import annotations

import json
from pathlib import Path

from audio_transcript.settings import AppSettings, SettingsStore


def test_settings_round_trip_with_cyrillic(tmp_path: Path) -> None:
    path = tmp_path / "config" / "settings.json"
    store = SettingsStore(path)
    expected = AppSettings(
        model_profile="fast",
        output_mode="source",
        last_source_directory=r"D:\Аудио",
        default_speaker="Евгений",
        window_width=1200,
        window_height=800,
        splitter_sizes=[420, 260],
    )

    store.save(expected)

    assert store.load() == expected
    assert "Евгений" in path.read_text(encoding="utf-8")
    assert not path.with_suffix(".json.tmp").exists()


def test_invalid_settings_fall_back_safely(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")

    assert SettingsStore(path).load() == AppSettings()


def test_unknown_values_are_normalized(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model_profile": "other", "output_mode": "cloud"}))
    loaded = SettingsStore(path).load()
    assert loaded.model_profile == "accuracy"
    assert loaded.output_mode == "workspace"
