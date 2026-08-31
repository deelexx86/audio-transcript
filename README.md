# Audio Transcript

Audio Transcript is a focused Windows 11 desktop utility for turning Telegram voice messages and other common audio files into faithful text. It provides a sequential queue, transcript preview, clipboard copy, and both TXT and Markdown artifacts.

Transcription runs locally with `faster-whisper` and CTranslate2. After dependencies and models have been downloaded during setup, normal transcription works offline: audio and transcripts stay on this computer, and the app uses no transcription API, account, telemetry, cloud storage, backend, or local server.

## Requirements

- Windows 11
- 64-bit Python 3.11 or 3.12
- Internet access for initial dependency and model download only
- Substantial free disk space for both Whisper models

The application is CPU-first and uses CTranslate2 `int8`; a discrete GPU is not required.

## Initial setup

From PowerShell in the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\bootstrap_models.bat
```

`bootstrap_models.bat` downloads both required CTranslate2 models into repository-local folders:

- `models\whisper-large-v3` for **Accuracy — Whisper large-v3**
- `models\whisper-large-v3-turbo` for **Fast — Whisper large-v3-turbo**

The bootstrap is repeatable and skips complete models. Model files are intentionally ignored by Git. Normal application startup never downloads a model; a missing model produces an actionable local error.

## Launch

Double-click `run.bat`. It starts the desktop application with `.venv\Scripts\pythonw.exe`, so normal use does not require a terminal.

## Workflow

1. Choose **Accuracy** for maximum fidelity or **Fast** for lower CPU processing time.
2. Optionally enter a default speaker. Each queued file's speaker remains editable.
3. Choose **Workspace / transcripts** or **Same folder as source**.
4. Drop files into the window, use **+ Files**, use non-recursive **+ Folder**, or scan `inbox\`.
5. Select **Transcribe**. Files run sequentially while the window remains responsive.
6. Select a completed row to preview, **Copy** its clean text, or **Open Folder** for its artifacts.

**Stop** requests safe cancellation of the current batch. Completed outputs are preserved, no further queued file starts, and remaining queued items can be restarted. Remove and Clear affect only the UI queue; source audio and generated artifacts are never deleted.

## Inputs and local folders

Supported input formats are `.ogg` (including Telegram Ogg/Opus), `.mp3`, `.m4a`, `.wav`, and `.webm`. Source files may remain anywhere on the local filesystem and are never copied, moved, renamed, or deleted by the app.

- `inbox\` is an optional staging folder for saved voice messages. The Inbox action scans only that folder, not subfolders.
- `models\` contains the two local speech-to-text models.
- `transcripts\` contains default workspace output.
- `config\settings.json` stores local UI preferences and is not committed.

Workspace outputs use the processing date and an append-safe source folder:

```text
transcripts\YYYY\YYYY-MM-DD\source-name\
  transcript.txt
  transcript.md
```

Same-folder mode creates `source-name_transcript\` beside the audio. Existing folders are never overwritten; retranscription creates `_2`, `_3`, and so on. `transcript.txt` contains only clean model output. `transcript.md` adds minimal source, processing time, duration, detected language, optional speaker, and actual model metadata.

## Privacy

During normal use, PyAV decodes local audio and the selected repository-local Whisper model performs inference on the CPU. The app makes no intentional network requests, performs no semantic rewriting or summarization, and does not permanently duplicate source audio. Treat `inbox\`, `transcripts\`, `models\`, `.venv\`, and `config\settings.json` as private runtime state; repository ignore rules protect them from accidental commits.

## Tests and installation check

```powershell
.\.venv\Scripts\python.exe -m pytest
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m audio_transcript --smoke-test
```

Remove the `QT_QPA_PLATFORM` environment variable before launching the normal visible application if it remains set in the current terminal.

## Troubleshooting

- **Model is not installed:** run `bootstrap_models.bat` while online. Both model folders must contain `config.json`, `model.bin`, and `tokenizer.json`.
- **Audio cannot be decoded:** confirm the file is complete and uses a supported extension. A corrupt or unsupported stream is reported on that queue row; later files continue.
- **CPU transcription is slow:** use the Fast profile. Large Whisper models are compute- and memory-intensive, especially for long recordings.
- **`run.bat` says setup is missing:** create `.venv` and install the project using the Initial setup commands.
- **No files appear from Add Folder or Inbox:** scanning is intentionally non-recursive and includes only supported audio files directly in the selected folder.
- **Output folder has `_2` or a higher suffix:** an earlier artifact folder already exists; the app never silently overwrites it.
