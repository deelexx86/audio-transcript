from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from audio_transcript.errors import ProcessingFailure
from audio_transcript.i18n import CATALOG_DIR, LANGUAGES, language_manager, system_language
from audio_transcript.queueing import QueueStatus
from audio_transcript.settings import AppSettings, SettingsStore
from audio_transcript.ui import MainWindow


def messages(path):
    return {
        (context.findtext("name"), message.findtext("source")): message
        for context in ET.parse(path).findall("context")
        for message in context.findall("message")
    }


def test_catalogs_cover_current_source_and_compiled_translations(tmp_path):
    app = QApplication.instance() or QApplication([])
    extracted = tmp_path / "extracted.ts"
    root = Path(__file__).resolve().parents[1]
    subprocess.run([
        str(Path(sys.executable).with_name("pyside6-lupdate.exe" if sys.platform == "win32" else "pyside6-lupdate")),
        str(root / "src/audio_transcript/ui.py"), "-tr-function-alias", "tr+=_status",
        "-locations", "none", "-source-language", "en", "-ts", str(extracted),
    ], check=True, capture_output=True)
    expected = messages(extracted)
    for code in LANGUAGES:
        catalog = messages(CATALOG_DIR / f"app_{code}.ts")
        assert catalog.keys() == expected.keys()
        compiled = QTranslator()
        assert compiled.load(str(CATALOG_DIR / f"app_{code}.qm"))
        for (context, source), message in catalog.items():
            translation = message.find("translation")
            assert translation.get("type") not in {"unfinished", "vanished", "obsolete"}
            forms = translation.findall("numerusform")
            texts = [form.text for form in forms] if forms else [translation.text]
            assert all(texts)
            placeholders = lambda value: set(re.findall(r"\{\w+\}|%n", value))
            assert all(placeholders(text) == placeholders(source) for text in texts)
            if forms:
                assert len(forms) == (3 if code == "ru" else 2)
                # Cover singular, paucal, plural and the Russian 11-14 exception.
                for count in (0, 1, 2, 5, 11, 12, 14, 21, 22, 25, 101):
                    form_index = (
                        0 if count % 10 == 1 and count % 100 != 11
                        else 1 if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14)
                        else 2
                    ) if code == "ru" else (0 if count == 1 else 1)
                    assert compiled.translate(context, source, None, count) == texts[form_index]
            else:
                assert compiled.translate(context, source) == texts[0]


@pytest.mark.parametrize("code,label", [("en", "Transcribe"), ("ru", "Расшифровать"), ("es", "Transcribir"), ("de", "Transkribieren")])
def test_live_language_switch_preserves_workflow_and_persists(code, label, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(interface_language="en"))
    window = MainWindow(store)
    window.show()
    monkeypatch.setattr("audio_transcript.ui.probe_duration", lambda _: 3)
    source = tmp_path / "Разговор.wav"
    source.write_bytes(b"source unchanged")
    window._add_paths([source])
    item = window.queue.items[0]
    item.status = QueueStatus.DONE
    item.transcript = "Original transcript. Исходный текст."
    item.speaker = "Иван"
    window.table.item(0, 2).setText(item.speaker)
    item.output_directory = tmp_path
    window._refresh_row(item)
    window._show_selected()
    cursor = window.preview.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(8, cursor.MoveMode.KeepAnchor)
    window.preview.setTextCursor(cursor)
    window.settings_toggle.setChecked(False)
    window.model_combo.setCurrentIndex(1)
    window.output_combo.setCurrentIndex(1)
    window._processing = True
    window._update_actions()
    window.language_combo.setCurrentIndex(window.language_combo.findData(code))
    app.processEvents()
    assert window.transcribe_button.text() == label
    assert window.language_combo.isVisible() and window.language_combo.isEnabled()
    assert not window.settings_panel.isVisible()
    assert window._selected_item() is item
    assert window._selected_ids() == [item.id]
    assert item.status == QueueStatus.DONE
    assert item.speaker == "Иван"
    assert window.preview.toPlainText() == item.transcript
    assert window.preview.textCursor().selectedText() == "Original"
    assert window.model_combo.currentData() == "fast"
    assert window.output_combo.currentData() == "source"
    assert not window.transcribe_button.isEnabled()
    window._copy_transcript()
    assert QApplication.clipboard().text() == item.transcript
    assert source.read_bytes() == b"source unchanged"
    window._processing = False
    window.close()
    assert store.load().interface_language == code
    reopened = MainWindow(store)
    assert reopened.transcribe_button.text() == label
    reopened.close()


def test_existing_error_and_active_progress_retranslate(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(interface_language="en"))
    window = MainWindow(store)
    window.youtube_edit.setText("https://youtu.be/jNQXAC9IVRw")
    window._add_youtube()
    item = window.queue.items[0]
    failure = ProcessingFailure(item.source_url, "HTTP 403; diagnostic remains original", "request_rejected")
    window._on_item_failed(item.id, failure)
    window.language_combo.setCurrentIndex(window.language_combo.findData("ru"))
    app.processEvents()
    assert "отклонил" in window.preview.toPlainText()
    assert failure.details in window.preview.toPlainText()
    assert item.source_url in window.preview.toPlainText()
    assert window.table.item(0, 3).text() == "Ошибка"
    window._on_state_changed(item.id, QueueStatus.TRANSCRIBING.value, 37)
    window.language_combo.setCurrentIndex(window.language_combo.findData("de"))
    app.processEvents()
    assert window.table.item(0, 3).text() == "Transkription 37%"
    assert item.progress == 37
    assert "Status: Transkription" in window.preview.toPlainText()
    window.close()


def test_first_launch_uses_system_language_and_unsupported_language_falls_back(tmp_path, monkeypatch):
    class SystemLocale:
        def uiLanguages(self):
            return ["pt-BR", "es-MX"]
    monkeypatch.setattr(QLocale, "system", lambda: SystemLocale())
    assert system_language() == "es"
    app = QApplication.instance() or QApplication([])
    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    assert window.language_combo.currentData() == "es"
    window.close()
    monkeypatch.setattr(SystemLocale, "uiLanguages", lambda _: ["ja-JP"])
    assert system_language() == "en"
    language_manager().set_language("en")


def test_language_settings_handle_old_and_invalid_values(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    for value in ('{}', '{"interface_language": "xx"}', '{"interface_language": null}', '{"interface_language": []}'):
        store.path.write_text(value, encoding="utf-8")
        assert store.load().interface_language == ""
    store.save(AppSettings(interface_language="de"))
    assert store.load().interface_language == "de"


@pytest.mark.parametrize("code", LANGUAGES)
def test_narrow_layout_preserves_queue_and_preview_space(code, tmp_path):
    app = QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(interface_language=code))
    window = MainWindow(store)
    window.show()
    for expanded in (True, False):
        window.settings_toggle.setChecked(expanded)
        app.processEvents()
        window.resize(760, 600)
        app.processEvents()
        assert window.width() == 760
        assert window.language_combo.isVisible()
        assert window.splitter.height() >= sum(
            window.splitter.widget(i).minimumHeight() for i in range(2)
        ) + window.splitter.handleWidth()
        assert window.transcribe_button.geometry().right() <= window.centralWidget().width()
    window.close()


def test_threaded_failures_reach_localized_ui_and_batch_continues(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(interface_language="en"))
    window = MainWindow(store)
    sources = [tmp_path / name for name in ("broken.wav", "повреждённый.mp4")]
    for source in sources:
        source.write_bytes(b"invalid media for local error-boundary test")
    window._add_paths(sources)
    window._start_batch()
    window.language_combo.setCurrentIndex(window.language_combo.findData("ru"))
    deadline = time.monotonic() + 5
    while window._processing and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not window._processing
    assert all(item.status == QueueStatus.ERROR for item in window.queue.items)
    assert all(isinstance(item.error, ProcessingFailure) for item in window.queue.items)
    assert "Не удалось выполнить расшифровку" in window.preview.toPlainText()
    assert "Технические сведения:" in window.preview.toPlainText()
    assert all(source.read_bytes() == b"invalid media for local error-boundary test" for source in sources)
    window.close()


def test_transient_addition_message_retranslates_with_plural_forms(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(interface_language="en"))
    window = MainWindow(store)
    source = tmp_path / "empty.wav"
    source.touch()
    window._add_paths([source])
    window._add_paths([source, source])
    assert window.statusBar().currentMessage() == "2 duplicates skipped"
    window.language_combo.setCurrentIndex(window.language_combo.findData("ru"))
    app.processEvents()
    assert window.statusBar().currentMessage() == "Пропущено 2 дубликата"
    window.close()
