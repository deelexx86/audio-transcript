"""Qt Linguist catalogs; language choices affect presentation only."""
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator


LANGUAGES = {"en": "English", "ru": "Русский", "es": "Español", "de": "Deutsch"}
CATALOG_DIR = Path(__file__).with_name("translations")


def system_language() -> str:
    for language in QLocale.system().uiLanguages():
        code = language.replace("_", "-").split("-")[0]
        if code in LANGUAGES:
            return code
    return "en"


class LanguageManager:
    """Own translators for the lifetime of QApplication, including Qt dialogs."""

    def __init__(self) -> None:
        self.language = ""
        self._translators: list[QTranslator] = []

    def set_language(self, language: str) -> None:
        language = language if language in LANGUAGES else system_language()
        if language == self.language:
            return
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("Create QApplication before selecting an interface language.")
        catalog = QTranslator()
        if not catalog.load(str(CATALOG_DIR / f"app_{language}.qm")):
            raise RuntimeError(f"Interface translation is missing: app_{language}.qm")
        qt_catalog = QTranslator()
        qt_loaded = qt_catalog.load(
            f"qtbase_{language}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        )
        for translator in self._translators:
            app.removeTranslator(translator)
        self._translators = [qt_catalog, catalog] if qt_loaded else [catalog]
        self.language = language
        for translator in self._translators:
            app.installTranslator(translator)


def language_manager() -> LanguageManager:
    app = QCoreApplication.instance()
    if app is None:
        raise RuntimeError("Create QApplication before accessing translations.")
    if not hasattr(app, "_audio_transcript_languages"):
        app._audio_transcript_languages = LanguageManager()
    return app._audio_transcript_languages
