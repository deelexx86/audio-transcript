# Audio Transcript

Audio Transcript is a focused Windows 11 desktop utility for turning Telegram voice messages and other common audio files into faithful text. It provides a sequential queue, transcript preview, clipboard copy, and both TXT and Markdown artifacts.

Transcription runs locally with `faster-whisper` and CTranslate2. After dependencies and models have been downloaded during setup, local-file transcription works offline: audio and transcripts stay on this computer, and the app uses no transcription API, account, telemetry, cloud storage, backend, or local server.

## Requirements

- Windows 11
- 64-bit Python 3.11 or 3.12
- Internet access for setup and for downloading audio from YouTube; local-file transcription remains offline
- For YouTube: Node.js 22+ or Deno 2.3+ available on PATH
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

1. Expand **Show settings** if needed. Choose **Accuracy** for maximum fidelity or **Fast** for lower CPU processing time.
2. Optionally enter a default speaker. Each queued file's speaker remains editable.
3. Choose **Workspace / transcripts** or **Same folder as source**.
4. Drop files into the window, use **+ Files**, use non-recursive **+ Folder**, or scan `inbox\`. Alternatively, paste a YouTube video link into the **YouTube** field and select **Add Link** (or press Enter).
5. Arrange the queue with **Move Up / Move Down** (multiple rows may be selected), or click any column header to sort ascending; click again for descending. **Added** records the local date/time of addition to this session, not the file modification time.
6. Select **Transcribe**. Files run sequentially in the displayed order while the window remains responsive. Reordering is disabled during processing.
7. Select a completed row to preview, **Copy** its clean text, or **Open Folder** for its artifacts.

**Stop** requests safe cancellation of the current batch. Completed outputs are preserved, no further queued file starts, and remaining queued items can be restarted. **Retry Selected** processes only selected Error or Cancelled rows, in queue order; unrelated rows stay unchanged. **Remove Completed** removes Done rows. Remove, Remove Completed, and Clear affect only the UI queue; local source audio and generated artifacts are never deleted.

**Hide settings** collapses the model, speaker, and output controls to give the queue and preview more room. The selected model and output remain visible in the Show settings button; the expanded/collapsed preference is saved locally.

Sorting is a one-time queue action. Newly added files append at the end, and manual moves override the previous sort. Unknown durations sort before known durations in ascending order. The queue and addition timestamps are session-only and are not restored after restarting.

## YouTube videos

**Add Link** validates and queues one video without contacting YouTube. **Transcribe** downloads the audio, then uses the selected local Whisper model. YouTube videos and local files share the same sequential queue. Download progress is shown separately from transcription progress; Stop requests cancellation at the next safe download/inference boundary (an in-flight network request may take up to its timeout).

Supported links include `youtube.com/watch?v=...`, `youtu.be/...`, Shorts, and embedded-video URLs. Tracking, timestamps, and playlist parameters are stripped: a link always transcribes the entire single video. Playlist-only/channel URLs, current live streams, and upcoming streams are not supported. Videos must be accessible without signing in; the app does not import browser cookies or use accounts.

Audio is downloaded with `yt-dlp` into an app-created temporary `config/youtube-*` directory. It is removed after completion, failure, or cancellation. A forced process termination or power loss may leave this temporary directory behind. Local source files are never removed. No permanent video or audio archive is created.

YouTube outputs always use `transcripts/YYYY/YYYY-MM-DD/youtube-VIDEO_ID/`, even when **Same folder as source** is selected for local files. Existing outputs receive a numbered suffix. Markdown includes the source video URL and title; TXT remains only the local model's transcript. Video titles appear in completed queue rows. Retrying a YouTube item downloads the audio again.

The Python dependency `yt-dlp[default]` includes its matching JavaScript solver scripts. A supported Node.js or Deno runtime is required; see the [official yt-dlp runtime guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS) for setup. No standalone FFmpeg installation is needed: audio-only downloads are decoded with the existing PyAV dependency. Neither downloader components nor speech models are silently installed at runtime.

To update an existing environment after pulling these changes:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

YouTube changes can require a downloader update independently of the app:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade "yt-dlp[default]"
```

## Inputs and local folders

Supported input formats are `.ogg` (including Telegram Ogg/Opus), `.mp3`, `.m4a`, `.wav`, `.webm`, and `.amr` (AMR-NB / AMR-WB, decoded locally by the existing PyAV dependency). Source files may remain anywhere on the local filesystem and are never copied, moved, renamed, or deleted by the app.

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

During normal use, PyAV decodes local audio and the selected repository-local Whisper model performs inference on the CPU. Local-file processing makes no intentional network requests. YouTube downloads contact YouTube and its media delivery hosts; speech recognition still runs locally, and transcripts are not uploaded. The app performs no semantic rewriting or summarization and does not permanently duplicate source audio. This explicitly requested YouTube workflow extends the original BRIEF.md offline-input boundary; BRIEF.md itself is unchanged. Treat `inbox\`, `transcripts\`, `models\`, `.venv\`, and `config\settings.json` as private runtime state; repository ignore rules protect them from accidental commits.

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
- **YouTube download failed:** check internet access and video availability without signing in. If multiple public videos fail, update `yt-dlp[default]` using the command above. Authentication, age/region restrictions, and YouTube service changes can prevent a download; a failed row does not stop the rest of the queue.
- **YouTube needs a JavaScript runtime:** make Node.js 22+ or Deno 2.3+ available on PATH, then restart the app. Local-file transcription does not need this runtime.
