# Audio Transcript

[English](README.md) · [Русский](README-ru.md) · [Español](README-es.md) · [Deutsch](README-de.md)

Audio Transcript ist ein kleines Windows-11-Desktopprogramm für originalgetreue Transkripte von Telegram-Sprachnachrichten, Audiodateien und Tonspuren lokaler Videos. Es bietet eine sequenzielle Warteschlange, Vorschau, Zwischenablage sowie TXT- und Markdown-Dateien.

Die Spracherkennung läuft lokal mit `faster-whisper` und CTranslate2. Nach dem Herunterladen der Abhängigkeiten und Modelle funktioniert die Verarbeitung lokaler Dateien offline. Audio und Transkripte bleiben auf diesem Computer; die App verwendet keine Transkriptions-API, Konten, Telemetrie, Cloud-Speicherung, Datenbank oder Server.

## Voraussetzungen

- Windows 11 und 64-Bit-Python 3.11 oder 3.12.
- Internet für die Einrichtung und für Audio-Downloads von YouTube.
- Für YouTube: Node.js 22+ oder Deno 2.3+ im PATH.
- Ausreichend freier Speicher für beide Whisper-Modelle.

Die App nutzt die CPU mit CTranslate2 `int8`; eine separate GPU ist nicht erforderlich.

## Erstinstallation

In PowerShell im Stammverzeichnis des Repositorys:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\bootstrap_models.bat
```

Das Skript lädt beide CTranslate2-Modelle in Projektordner:

- `models\whisper-large-v3`: **Genauigkeit — Whisper large-v3**.
- `models\whisper-large-v3-turbo`: **Schnell — Whisper large-v3-turbo**.

Wiederholte Ausführung überspringt vollständige Modelle. Git ignoriert die Modelldateien. Beim normalen Start werden keine Modelle heruntergeladen; fehlende Modelle führen zu einer verständlichen Fehlermeldung mit Anleitung.

## Start und Sprache

Doppelklicken Sie auf `run.bat`. Es startet die App mit `.venv\Scripts\pythonw.exe`; im Alltag ist kein Terminal nötig.

Wählen Sie oberhalb der Einstellungen **Sprache der Oberfläche**: English, Русский, Español oder Deutsch. Die Auswahl bleibt bei ausgeblendeten Einstellungen sichtbar und funktioniert während der Verarbeitung. Änderungen gelten sofort und werden in `config/settings.json` gespeichert. Beim ersten Start wird eine unterstützte Windows-Anzeigesprache verwendet, andernfalls Englisch.

Die Auswahl betrifft nur die Oberfläche. Die Sprache der Aufnahme wird automatisch erkannt; Transkripttext, Dateinamen und Markdown-Metadaten bleiben erhalten. Technische Fehlerdetails behalten ihren ursprünglichen Wortlaut.

## Arbeitsablauf

1. Öffnen Sie bei Bedarf **Einstellungen**. **Genauigkeit** bevorzugt höchste Texttreue, **Schnell** verkürzt die CPU-Verarbeitungszeit.
2. Geben Sie optional einen Standardsprecher ein. Er kann pro Zeile geändert werden.
3. Wählen Sie **Projektordner / transcripts** oder **Neben der Quelldatei**.
4. Ziehen Sie Dateien ins Fenster oder verwenden Sie **+ Dateien**, **+ Ordner** oder **Eingang** für `inbox\`. Unterordner werden nicht durchsucht. Für YouTube fügen Sie einen Link ein und drücken **Link hinzufügen** oder Enter.
5. Ordnen Sie mit **Nach oben / Nach unten**, auch mit mehreren ausgewählten Zeilen. Eine Spaltenüberschrift sortiert aufsteigend, ein weiterer Klick absteigend. **Hinzugefügt** zeigt lokale Zeit und Datum der Aufnahme in diese Sitzung, nicht die Dateiänderungszeit.
6. Drücken Sie **Transkribieren**. Dateien werden sequenziell in der sichtbaren Reihenfolge verarbeitet; das Fenster bleibt bedienbar. Umordnen ist währenddessen gesperrt.
7. Wählen Sie eine fertige Zeile zum Lesen, **Kopieren** für den reinen Text oder **Ordner öffnen** für die Ergebnisdateien.

**Stoppen** fordert einen sicheren Abbruch an: fertige Ergebnisse bleiben erhalten, weitere Dateien starten nicht und wartende Einträge können später fortgesetzt werden. **Auswahl wiederholen** verarbeitet nur ausgewählte fehlerhafte oder abgebrochene Zeilen in Warteschlangenreihenfolge. **Fertige entfernen** entfernt fertige Zeilen. Entfernen und Leeren betreffen ausschließlich die Warteschlange; Quelldateien und Transkripte werden nie gelöscht.

**Einstellungen ausblenden** schafft Platz für Warteschlange und Vorschau. Die Schaltfläche zeigt Modell und Ausgabeziel; ihr Tooltip enthält den vollständigen Text. Der Zustand wird lokal gespeichert. Sortieren ist eine einmalige Aktion: neue Dateien kommen ans Ende, manuelles Verschieben ersetzt die vorherige Sortierung. Unbekannte Dauern stehen bei aufsteigender Sortierung zuerst. Warteschlange und Hinzufügezeiten werden nach einem Neustart nicht wiederhergestellt.

## YouTube-Videos

**Link hinzufügen** prüft und erfasst ein Video ohne Kontakt zu YouTube. **Transkribieren** lädt den Ton herunter und verarbeitet ihn mit dem ausgewählten lokalen Whisper-Modell. Videos und lokale Dateien teilen dieselbe sequenzielle Warteschlange. Download- und Transkriptionsfortschritt werden getrennt dargestellt. Stoppen wirkt am nächsten sicheren Abbruchpunkt; eine laufende Netzwerkanfrage kann bis zu ihrem Timeout dauern.

Bei einer Bot-Prüfung erscheint **Warten auf Wiederholung** für 10 Sekunden. Danach folgt genau ein weiterer Versuch mit einer neuen Gast-Sitzung des Downloaders. Stoppen bricht auch die Wartezeit ab. Scheitert der zweite Versuch, bleibt **Auswahl wiederholen** für später verfügbar; weitere Einträge laufen weiter. Andere Fehlerkategorien lösen diesen Zusatzversuch nicht aus; begrenzte Verbindungs- und Fragmentwiederholungen des Downloaders bleiben bestehen.

Die Fehleransicht unterscheidet Bot-Prüfungen, Zugriffsbeschränkungen, nicht verfügbare Videos, Netzwerk-/Serverfehler, abgelehnte Medienanfragen, fehlende Komponenten und Audioformate. Sie enthält Phase, Versuchszahl, Komponentenversionen und höchstens fünf feste Warnzusammenfassungen. Originalprotokolle des Downloaders, Cookies, Anfrage-Header und Medien-URLs werden nicht aufbewahrt; es wird kein Diagnoseprotokoll auf die Festplatte geschrieben.

Unterstützt werden `youtube.com/watch?v=...`, `youtu.be/...`, Shorts und eingebettete Videolinks. Tracking-, Zeit- und Playlistparameter werden entfernt: verarbeitet wird immer ein vollständiges Einzelvideo. Reine Playlist-/Kanallinks, laufende und angekündigte Livestreams sind ausgeschlossen. Videos müssen ohne Anmeldung zugänglich sein; die App importiert keine Browser-Cookies und verwendet keine Konten.

`yt-dlp` lädt Audio in einen temporären Ordner `config/youtube-*`, der nach Erfolg, Fehler oder Abbruch entfernt wird. Erzwungenes Prozessende oder Stromausfall kann den Ordner zurücklassen. Es entsteht kein dauerhaftes Video-/Audioarchiv; lokale Quelldateien werden nicht entfernt.

YouTube-Ergebnisse liegen immer unter `transcripts/YYYY/YYYY-MM-DD/youtube-VIDEO_ID/`, auch wenn für lokale Dateien die Ausgabe neben der Quelle gewählt ist. Bei Namenskollisionen folgt eine Nummer. Markdown enthält Video-URL und Titel; TXT ausschließlich den Text des lokalen Modells. Der Titel erscheint in der fertigen Zeile. Wiederholen lädt das Audio erneut herunter.

`yt-dlp[default]` enthält passende JavaScript-Skripte zur Lösung von Prüfungen. Ein unterstütztes Node.js oder Deno ist erforderlich; siehe die [offizielle yt-dlp-Anleitung](https://github.com/yt-dlp/yt-dlp/wiki/EJS). Eine separate FFmpeg-Installation ist nicht nötig: PyAV dekodiert das Audio. Downloader-Komponenten und Modelle werden während des Betriebs nicht automatisch installiert.

Nach dem Abrufen neuer Projektänderungen aktualisieren Sie die Umgebung:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

YouTube-Änderungen können unabhängig davon ein Downloader-Update erfordern:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade "yt-dlp[default]"
```

## Formate, Ordner und Ergebnisse

Audio: `.ogg` (einschließlich Telegram Ogg/Opus), `.mp3`, `.m4a`, `.wav`, `.webm`, `.amr` (AMR-NB / AMR-WB).

Video: `.mp4`, `.m4v`, `.mkv`, `.mov`, `.avi`, `.wmv`, `.asf`, `.flv`, `.webm`, `.mpg`, `.mpeg`, `.ts`, `.mts`, `.m2ts`, `.vob`, `.ogv`, `.3gp`, `.3g2`. Hinzufügen erfolgt über die üblichen Aktionen. PyAV dekodiert die erste Audiospur direkt; Audioexport und separate FFmpeg-Installation entfallen. Bilder und Untertitel werden nicht verarbeitet. Die tatsächliche Unterstützung hängt von einer lesbaren, unverschlüsselten, dekodierbaren Audiospur ab. Videos ohne Ton oder mit unlesbarer Spur verursachen einen Fehler pro Datei; die Warteschlange läuft weiter.

Quelldateien können überall im lokalen Dateisystem bleiben: sie werden nie kopiert, verschoben, umbenannt oder gelöscht. Videos nutzen dieselben Ausgabeziele, den Überschreibschutz, TXT/Markdown, Vorschau und Zwischenablage wie Audio.

- `inbox\`: optionaler Eingangsordner; keine Unterordnersuche.
- `models\`: die beiden lokalen Modelle.
- `transcripts\`: Standardausgabe.
- `config\settings.json`: lokale Oberflächeneinstellungen, nicht in Git.

Die Projektausgabe verwendet das Verarbeitungsdatum:

```text
transcripts\YYYY\YYYY-MM-DD\source-name\
  transcript.txt
  transcript.md
```

Neben der Quelle wird `source-name_transcript\` angelegt. Bestehende Ordner werden nie überschrieben; neue Ergebnisse erhalten `_2`, `_3` usw. TXT enthält nur Modelltext. Markdown ergänzt Quelle, Verarbeitungszeit, Dauer, erkannte Sprache, optionalen Sprecher und tatsächliches Modell.

## Datenschutz

PyAV dekodiert lokal; das Whisper-Modell im Projekt erkennt Sprache auf der CPU. Lokale Dateien verursachen keine beabsichtigten Netzwerkanfragen. YouTube-Downloads kontaktieren YouTube und seine Medienserver; Erkennung bleibt lokal, Transkripte werden nicht hochgeladen. Es erfolgt keine Zusammenfassung oder semantische Überarbeitung und keine dauerhafte Kopie des Quellaudios. Die zuvor ausdrücklich gewünschte YouTube-Funktion erweitert die ursprüngliche Offline-Eingabegrenze aus `BRIEF.md`; diese Datei bleibt unverändert. `inbox\`, `transcripts\`, `models\`, `.venv\` und `config\settings.json` sind private Laufzeitdaten, die durch Git-Regeln geschützt werden.

## Prüfungen

```powershell
.\.venv\Scripts\python.exe -m pytest
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m audio_transcript --smoke-test
```

Entfernen Sie `QT_QPA_PLATFORM` vor dem normalen sichtbaren Start aus der Terminalumgebung, falls die Variable noch gesetzt ist.

## Übersetzungen pflegen

Die App verwendet `QTranslator` und Qt Linguist. Editierbare `.ts` und kompilierte `.qm` liegen in `src/audio_transcript/translations/` und werden mit dem Python-Paket ausgeliefert. Übersetzungsdienste und Laufzeitdownloads sind unnötig. Auch der englische Katalog liefert korrekte Pluralformen. Für Qt-Standarddialoge werden Qt-Übersetzungen geladen; native Windows-Dialoge verwenden die Windows-Sprache.

Neue Oberflächentexte in `MainWindow` werden mit `self.tr("English source text")` markiert. Verwenden Sie vollständige Vorlagen mit benannten Platzhaltern und für Mengen `self.tr("%n item(s)", None, count)`. `_status("English source text", ...)` wird ebenfalls extrahiert. Interne Einstellungs-, Modell- und Statusschlüssel sowie Ergebnisdateien bleiben unabhängig von übersetzten Beschriftungen.

```powershell
# Neue/geänderte Texte extrahieren; vorhandene Übersetzungen erhalten:
.\.venv\Scripts\python.exe scripts\update_translations.py --update
# Alle vier .ts mit Qt Linguist oder einem XML-Editor bearbeiten, dann kompilieren:
.\.venv\Scripts\python.exe scripts\update_translations.py
.\.venv\Scripts\python.exe -m pytest
```

Committen Sie `.ts` und `.qm` gemeinsam. Tests prüfen Abdeckung, Platzhalter, Pluralformen, Übereinstimmung der kompilierten Kataloge und Sprachwechsel im Betrieb. Halten Sie alle vier README-Versionen aktuell.

## Fehlerbehebung

- **Modell fehlt:** `bootstrap_models.bat` mit Internet ausführen. Beide Modellordner benötigen `config.json`, `model.bin` und `tokenizer.json`.
- **Audio nicht lesbar:** Vollständigkeit und Dateiendung prüfen. Ein Dateifehler beendet die übrige Warteschlange nicht.
- **CPU langsam:** Profil Schnell wählen. Große Whisper-Modelle benötigen viel Rechenleistung und Speicher, besonders bei langen Aufnahmen.
- **`run.bat` meldet fehlende Einrichtung:** `.venv` erstellen und Projekt mit den Befehlen oben installieren.
- **Video ohne Ton:** Eine Audiospur ist nötig; bei mehreren wird die erste genutzt.
- **Ordner/Eingang leer:** Nur unterstützte Dateien direkt im gewählten Ordner werden erfasst.
- **Suffix `_2` oder höher:** Ein Ergebnisordner existiert bereits; Überschreiben wird verhindert.
- **YouTube-Bot-Prüfung:** Browserwiedergabe garantiert keinen automatisierten Download. Nach dem einmaligen Wiederholen nach 10 Sekunden später erneut versuchen. Anmeldung oder Update garantiert keine Lösung; Browser-Sitzungen, Cookies und Konten werden nicht verwendet.
- **Andere YouTube-Fehler:** Kategorie und Diagnose helfen bei Netzwerk-, Zugriffs-, Format- oder Komponentenproblemen. Bei Änderungen des Dienstes eine neue `yt-dlp[default]`-Version prüfen.
- **JavaScript-Laufzeit fehlt:** Node.js 22+ oder Deno 2.3+ zum PATH hinzufügen und App neu starten. Für lokale Dateien unnötig.
