# Audio Transcript

[English](README.md) · [Русский](README-ru.md) · [Español](README-es.md) · [Deutsch](README-de.md)

Audio Transcript is a focused Windows 11 desktop utility for turning Telegram voice messages, common audio files, and the audio from local video files into faithful text. It provides a sequential queue, transcript preview, clipboard copy, and both TXT and Markdown artifacts.

Whisper uses faster-whisper and CTranslate2. The additional remote GPU models use audio.cpp. Local CPU and local NVIDIA GPU processing work offline after setup. An optional SSH mode sends media to a Windows GPU computer you select. Transcripts are saved on this computer.

## Requirements

- Windows 11
- 64-bit Python 3.11 or 3.12
- Internet access for setup and for downloading audio from YouTube; local-file transcription remains offline
- For YouTube: Node.js 22+ or Deno 2.3+ available on PATH
- Substantial free disk space for both Whisper models

Fresh settings select Local NVIDIA GPU. Select Local CPU in **Acceleration…** for the legacy Whisper CTranslate2 `int8` workflow.

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

## NVIDIA acceleration

Use **Acceleration…** to select **Local CPU**, **Local NVIDIA GPU**, or **Remote NVIDIA GPU**. Both Whisper checkpoints are available in all three modes. The additional models run over SSH. The main window shows the selected mode. Settings persist, and a failure stays in the selected mode.

- **Local NVIDIA GPU** requires Windows x64, a CUDA-compatible NVIDIA GPU with float16 support, a current driver compatible with CUDA 12.8, and the local models. Run `.\.venv\Scripts\python.exe scripts\setup_gpu.py` once from the repository. CUDA libraries are installed in the project environment.
- **Remote NVIDIA GPU** requires a Windows x64 host with Python 3.11, an NVIDIA driver, and Windows OpenSSH using its default command shell. Configure key-based SSH access and verify the host key before provisioning. Run `.\.venv\Scripts\python.exe scripts\setup_gpu.py --remote gpu-tts` once, replacing `gpu-tts` with your SSH alias if needed. Setup provisions the worker, CTranslate2 CUDA dependencies and the pinned Windows audio.cpp 0.9.6 build under `%LOCALAPPDATA%\AudioTranscriptGpu`. The audio.cpp build requires a driver compatible with CUDA 13.3. Use `--worker-only` for a Whisper-only host. Use Model Manager to download weights to `D:\models\audio-transcript`.

Choose the matching SSH alias in the application. Jobs use the verified host key and non-interactive OpenSSH. **Uploading over SSH** shows activity while the file is transferred. Stop closes the job's SSH session, and a remote lease expires after about 45 seconds without data or a heartbeat if the connection disappears. The worker uses a delete-on-close temporary media file and exits after each item, releasing its GPU memory.

## Model Manager

Select the target in **Acceleration…**, then open **Model Manager**. The catalog displays all 12 checkpoints, including models unavailable in the selected mode. It shows managed file status, the runtime and device preflight, supported modes, native capabilities and exact checkpoint files. CUDA preflight checks the runtime and device. Individual audio, context and GPU memory constraints can still produce a per-file error.

- **Download** installs the pinned checkpoint. The progress bar follows received bytes. Cancelling leaves resumable partial files. Completed checkpoints are reusable offline.
- **Remove files** asks for confirmation and removes only managed files for the selected checkpoint. An active inference or model operation holds the model lock.
- **Use selected model** applies an installed checkpoint that passes preflight. Settings preserve the selection and SSH alias. Open **Refresh** to recheck storage and runtime after an external change.

Each inference uses the selected model, with no model or execution-mode substitution. The [catalog manifest](src/audio_transcript/model_catalog.py) records package revisions, filenames, checksums, licenses and runtime options. After a baseline upgrade, move existing complete remote Whisper directories from the former worker's `models` folder into `D:\models\audio-transcript` before downloading replacements. Preserve the per-model folder names.

`transcript.txt` and `transcript.md` retain the plain recognized text. Models with native speaker output also write `transcript.speakers.txt` when speaker-attributed text is available. Timestamps appear only when the model emits them. The VibeVoice streaming checkpoints emit native speaker labels without timestamps. Each whole recording is passed to the selected runtime in one session, and duration-limit errors are reported per item. During opaque inference, elapsed time remains available. The application needs position observations to estimate speed or ETA.

## Workflow

Choose **Interface language** above the settings panel: English, Русский, Español, or Deutsch. The selector stays visible when settings are collapsed and works during processing. Changes apply immediately and are saved in `config/settings.json`. On first launch, the app uses a supported Windows display language, falling back to English. The language setting affects the interface. Transcript text, filenames and Markdown metadata remain independent. Technical diagnostic details retain their original wording.

1. Choose a ready model in **Model Manager**. Expand **Show settings** for the selected model, speaker and output settings.
2. Optionally enter a default speaker. Each queued file's speaker remains editable.
3. Choose **Workspace / transcripts** or **Same folder as source**.
4. Drop files into the window, use **+ Files**, use non-recursive **+ Folder**, or scan `inbox\`. Alternatively, paste a YouTube video link into the **YouTube** field and select **Add Link** (or press Enter).
5. Arrange the queue with **Move Up / Move Down** (multiple rows may be selected), or click any column header to sort ascending; click again for descending. **Added** records the local date/time of addition to this session, not the file modification time.
6. Select **Transcribe**. Files run sequentially in the displayed order while the window remains responsive. Reordering is disabled during processing.
7. Select a completed row to preview, **Copy** its clean text, or **Open Folder** for its artifacts.

**Stop** requests safe cancellation of the current batch. Completed outputs are preserved, no further queued file starts, and remaining queued items can be restarted. **Retry Selected** processes only selected Error or Cancelled rows, in queue order; unrelated rows stay unchanged. **Remove Completed** removes Done rows. Remove, Remove Completed, and Clear affect only the UI queue; local source audio and generated artifacts are never deleted.

**Hide settings** collapses the model, speaker, and output controls to give the queue and preview more room. The selected model and output remain visible in the Show settings button; the expanded/collapsed preference is saved locally.

Sorting is a one-time queue action. Newly added files append at the end, and manual moves override the previous sort. Unknown durations sort before known durations in ascending order. The queue and addition timestamps are session-only and are not restored after restarting.

## Processing time, speed and remaining time

Below the preview, the current-file area shows the phase, processed media position, **Elapsed**, **Remaining**, and **Speed**, separately from the batch counts. Elapsed uses a monotonic clock and refreshes every half second, including model loading, decoding, downloading, SSH upload, retry waits and saving. Stop keeps this clock running until a safe termination point. Done, Error and Cancelled retain the measured duration; selecting a finished row shows that attempt's timing. Retry Selected starts fresh measurements. Durations are kept in the session's per-item result state; GPU runs also record the execution mode in Markdown.

Speed is processed audio time divided by actual inference time, displayed as **× realtime**; model loading, decoding, downloads, SSH upload and saving are excluded. Remaining is a transcription-only approximation, not a batch or download ETA. It requires at least three advancing observations separated by a second, five seconds of inference and five seconds of media progress. Burst-delivered segments are coalesced, throughput is smoothed, and estimates are rounded up to minutes (five-minute steps above ten minutes). Early observations show **Estimating…**; unknown duration, non-transcription phases or stalled progress show **Unavailable**. Stale estimates expire after 30–120 seconds depending on observed intervals, and recovery requires fresh observations. These conservative thresholds may suppress ETA for short recordings or slow inference windows.

## YouTube videos

**Add Link** validates and queues one video without contacting YouTube. **Transcribe** downloads the audio, then uses the selected Whisper model in the active execution mode. YouTube videos and local files share the same sequential queue. Download progress is shown separately from transcription progress; Stop requests cancellation at the next safe download/inference boundary (an in-flight network request may take up to its timeout).

If YouTube requests an anti-bot check, the row shows **Waiting to retry** for 10 seconds, then the app tries once with a fresh downloader guest session. **Stop** also cancels this wait. If the second attempt fails, the row remains available for **Retry Selected** later; subsequent queue items continue normally. Other error categories do not trigger this extra retry (the downloader still has its bounded connection/fragment retries).

The error preview distinguishes anti-bot checks, access restrictions, unavailable videos, connection/server errors, rejected media requests, missing components, and missing audio formats. It includes the failing stage, attempt count, downloader/runtime versions, and at most five fixed warning summaries. Raw downloader logs, cookies, request headers, and media URLs are not retained in these diagnostics; no diagnostic log is written to disk.

Supported links include `youtube.com/watch?v=...`, `youtu.be/...`, Shorts, and embedded-video URLs. Tracking, timestamps, and playlist parameters are stripped: a link always transcribes the entire single video. Playlist-only/channel URLs, current live streams, and upcoming streams are not supported. Videos must be accessible without signing in; the app does not import browser cookies or use accounts.

Audio is downloaded with `yt-dlp` into an app-created temporary `config/youtube-*` directory. It is removed after completion, failure, or cancellation. A forced process termination or power loss may leave this temporary directory behind. Local source files are never removed. No permanent video or audio archive is created.

YouTube outputs always use `transcripts/YYYY/YYYY-MM-DD/youtube-VIDEO_ID/`, even when **Same folder as source** is selected for local files. Existing outputs receive a numbered suffix. Markdown includes the source video URL and title; TXT remains only the model's transcript. Video titles appear in completed queue rows. Retrying a YouTube item downloads the audio again.

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

Supported audio formats are `.ogg` (including Telegram Ogg/Opus), `.mp3`, `.m4a`, `.wav`, `.webm`, and `.amr` (AMR-NB / AMR-WB).

Supported video containers are `.mp4`, `.m4v`, `.mkv`, `.mov`, `.avi`, `.wmv`, `.asf`, `.flv`, `.webm`, `.mpg`, `.mpeg`, `.ts`, `.mts`, `.m2ts`, `.vob`, `.ogv`, `.3gp`, and `.3g2`. Add local videos through **+ Files**, **+ Folder**, **Inbox**, or drag & drop, then select **Transcribe** as usual. The first audio track is decoded directly by the existing PyAV dependency and transcribed in the selected execution mode; no separate audio export or standalone FFmpeg installation is needed. Video images and subtitles are not processed. Actual compatibility depends on a readable, unencrypted audio track supported by the decoder. Videos with no audio or unreadable audio produce a per-file error; the remaining batch continues.

Source files may remain anywhere on the local filesystem and are never moved, renamed, or deleted by the app. Video transcripts use the same output modes, collision handling, TXT/Markdown artifacts, preview, and clipboard actions as audio transcripts.

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

PyAV decodes and the selected model recognizes speech on the machine selected in **Acceleration…**. CPU and local GPU modes keep source media on this computer. Remote GPU mode transfers the complete selected media file (including video if present) or downloaded YouTube audio to the chosen SSH host, then returns transcript text. Output files are saved locally. YouTube downloads contact YouTube and its media delivery hosts. The app performs no semantic rewriting or summarization. Git ignore rules protect private runtime data in `inbox\`, `transcripts\`, `models\`, `.venv\` and `config\settings.json`.

## Tests and installation check

```powershell
.\.venv\Scripts\python.exe -m pytest
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m audio_transcript --smoke-test
```

Remove the `QT_QPA_PLATFORM` environment variable before launching the normal visible application if it remains set in the current terminal.

## Maintaining translations

The app uses Qt's native `QTranslator` and Qt Linguist catalogs in `src/audio_transcript/translations/`. Editable `.ts` files and compiled `.qm` files are included in the Python package; no runtime download or translation service is used. The English catalog also supplies proper plural forms. Qt's bundled translations are loaded for standard Qt dialogs; native Windows dialogs follow Windows language settings.

Wrap new interface text in `self.tr("English source text")` in `MainWindow`. Use complete templates with named placeholders; use `self.tr("%n item(s)", None, count)` for counts. `_status("English source text", ...)` is also extracted. Keep internal settings/profile/status identifiers and generated artifacts independent of translated labels.

```powershell
# Extract new/changed strings; existing translations are retained.
.\.venv\Scripts\python.exe scripts\update_translations.py --update
# Edit all four .ts catalogs with Qt Linguist or an XML editor, then compile:
.\.venv\Scripts\python.exe scripts\update_translations.py
.\.venv\Scripts\python.exe -m pytest
```

Commit the updated `.ts` and `.qm` files together. Translation tests check coverage, placeholders, plural forms, compiled catalog consistency, and live language changes. Keep the four README versions aligned when the workflow changes.

## Troubleshooting

- **Model is not installed:** run `bootstrap_models.bat` while online. Both model folders must contain `config.json`, `model.bin`, and `tokenizer.json`.
- **Audio cannot be decoded:** confirm the file is complete and uses a supported extension. A corrupt or unsupported stream is reported on that queue row; later files continue.
- **CPU transcription is slow:** use the Fast profile. Large Whisper models are compute- and memory-intensive, especially for long recordings.
- **`run.bat` says setup is missing:** create `.venv` and install the project using the Initial setup commands.
- **Video contains no audio:** the app requires an audio track; silent videos cannot be transcribed. For multi-track videos, the first audio track is used.
- **No files appear from Add Folder or Inbox:** scanning is intentionally non-recursive and includes only supported audio and video files directly in the selected folder.
- **Output folder has `_2` or a higher suffix:** an earlier artifact folder already exists; the app never silently overwrites it.
- **YouTube requested an anti-bot check:** public browser playback can still work while an automated request is rejected. The app retries once after 10 seconds. If rejected again, try **Retry Selected** later. Login or a downloader update is not a guaranteed fix; the app does not automatically access browser sessions, cookies, or accounts.
- **Other YouTube download failures:** use the error category and diagnostic summary to distinguish connectivity, access, format, and component problems. Check for a newer `yt-dlp[default]` release when service compatibility changes; a failed row does not stop the rest of the queue.
- **YouTube needs a JavaScript runtime:** make Node.js 22+ or Deno 2.3+ available on PATH, then restart the app. Local-file transcription does not need this runtime.
