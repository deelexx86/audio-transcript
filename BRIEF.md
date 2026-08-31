# Audio Transcript — Product & Implementation Brief

**Repository:** `D:\projects\audio-transcript`  
**Target platform:** Windows 11  
**Target hardware:** AMD Ryzen 5 5600, 64 GB RAM  
**Status:** READY FOR OWNER REVIEW  
**Purpose:** Source of truth for product scope, UX behavior, filesystem rules, privacy boundaries and MVP acceptance criteria.

---

## 1. Purpose

`Audio Transcript` is a small local desktop application for converting voice messages and audio files into faithful text transcripts.

The primary use case is:

> Telegram voice message → local transcription → TXT / Markdown artifact → transfer to ChatGPT for commercial negotiation analysis.

The application is an internal working tool.

It is **not** intended to become:

- a commercial SaaS product;
- a transcription platform;
- a document-management system;
- a negotiation-analysis system;
- a Telegram bot;
- a cloud service.

The main design principle is:

> Build the simplest reliable local tool that makes audio → transcript a short, repeatable workflow.

---

## 2. Primary goals

The MVP must allow the user to:

1. take a Telegram `.ogg` voice message or another common audio file;
2. add it to the application by drag & drop, file selection, folder selection or the repository `inbox`;
3. transcribe it entirely on the local computer;
4. inspect the transcript inside the application;
5. save the result as `.txt` and `.md`;
6. copy the clean transcript directly to the clipboard;
7. pass the transcript to ChatGPT for further analysis.

No manual audio conversion should be required.

No terminal interaction should be required during normal daily use.

---

## 3. Core product priorities

Priorities, in order:

1. **Transcript fidelity**
2. **Local privacy**
3. **Reliable workflow**
4. **Simple batch processing**
5. **Clear UI state**
6. **Low maintenance complexity**
7. **Reasonable CPU performance**
8. Visual polish

The application must preserve the source meaning as closely as the selected speech-to-text model allows.

For negotiation analysis, the following details are especially important:

- exact wording;
- argument order;
- negations;
- monetary amounts;
- names;
- reservations and qualifications;
- emotionally meaningful wording;
- technical terminology;
- mixed Russian / English terminology.

The application must not intentionally rewrite the speaker's meaning for readability.

---

## 4. Local-only architecture

The MVP must use fully local speech-to-text inference.

There must be no dependency on:

- OpenAI Speech-to-Text API;
- any other cloud transcription API;
- remote backend;
- local backend/server;
- user accounts;
- authentication;
- API keys;
- cloud storage;
- database.

Normal transcription must work without internet access after the application dependencies and model files have been installed.

Initial development/setup may use the internet to:

- install Python dependencies;
- download required speech-to-text model files.

Normal runtime transcription must not initiate network requests.

No telemetry, analytics or remote crash reporting should be added.

---

## 5. Technology baseline

The intended MVP stack is:

- Python 3.11+;
- PySide6 for the Windows desktop UI;
- `faster-whisper`;
- CTranslate2;
- PyAV for local audio decoding.

The implementation is CPU-first.

Target hardware:

- AMD Ryzen 5 5600;
- 6 cores / 12 threads;
- 64 GB DDR4 RAM;
- Windows 11.

The MVP must not depend on a discrete GPU.

CPU `int8` inference is the preferred baseline unless implementation testing demonstrates a materially better supported configuration.

A change of the fundamental technology stack is allowed only if a concrete blocker makes the accepted stack impractical.

Do not replace the stack merely because another framework is more modern or theoretically more extensible.

---

## 6. Speech-to-text model profiles

The UI exposes two user-facing model profiles.

### Accuracy

Default profile.

Intended model:

`Whisper large-v3`

Purpose:

- maximize transcript quality;
- use for commercial negotiations and recordings where exact wording matters most.

### Fast

Alternative profile.

Intended model:

`Whisper large-v3-turbo`

Purpose:

- reduce processing time when speed is more important;
- provide a practical fallback if `large-v3` is too slow for a particular batch or recording.

The user-facing UI must use the names:

- `Accuracy — Whisper large-v3`
- `Fast — Whisper large-v3-turbo`

Implementation may map these profiles to the exact model identifiers required by the selected runtime.

The application must not expose low-level model parameters such as:

- `compute_type`;
- beam size;
- thread count;
- internal model paths;
- CTranslate2 settings.

Those are implementation concerns, not normal user controls.

---

## 7. Model storage

Model files must be stored inside the repository workspace:

```text
D:\projects\audio-transcript\models\
```

Model files must never be committed to Git.

The `models` directory itself must remain part of the repository structure.

Recommended Git pattern:

```text
models\
└─ .gitignore
```

with directory-local ignore behavior equivalent to:

```gitignore
*
!.gitignore
```

The application must explicitly use the repository-local model storage rather than silently scattering downloaded model files across unrelated user cache directories where reasonably possible.

Normal runtime must use already-local model files.

If a required model is missing, the application must show a clear actionable error rather than failing obscurely.

Silent network downloads during normal transcription are not desired.

---

## 8. Repository and runtime model

The repository is also the operating directory of the application.

Canonical location:

```text
D:\projects\audio-transcript
```

No separate application installation is required for the MVP.

The expected top-level runtime structure is:

```text
D:\projects\audio-transcript\
│
├─ BRIEF.md
├─ AGENTS.md
├─ README.md
├─ run.bat
│
├─ .venv\
├─ models\
├─ inbox\
├─ transcripts\
├─ config\
├─ application source
└─ tests
```

Exact internal source-code organization may be chosen during implementation as long as it remains small, understandable and consistent with this brief.

---

## 9. Development / setup responsibility

Codex is expected to perform through the terminal everything that can reasonably be automated, including:

- repository initialization where needed;
- Python virtual environment creation;
- Python dependency installation;
- model download/bootstrap;
- local configuration;
- test execution;
- application launch;
- available CLI-based dependency setup.

The user should only be asked to perform a manual installation when a dependency genuinely requires a normal Windows GUI installer or equivalent manual Windows interaction.

Avoid manual installation requirements whenever a reliable terminal-based solution exists.

---

## 10. Application launch

Normal use must not require opening a terminal.

The repository must provide:

```text
run.bat
```

which launches the application using the repository-local virtual environment.

Expected conceptual behavior:

```text
run.bat
  ↓
.venv Python
  ↓
desktop application
```

Double-clicking `run.bat` should be sufficient for normal application startup after initial setup is complete.

---

## 11. Input artifact organization

The repository contains a canonical optional input directory:

```text
D:\projects\audio-transcript\inbox\
```

The directory exists to prevent local organizational chaos and provide a predictable location for saved Telegram messages.

Example:

```text
inbox\
├─ audio_2026-08-31_12-44-51.ogg
├─ audio_2026-08-31_13-02-18.ogg
└─ meeting.m4a
```

The `inbox` directory is a convenience workflow, not a restriction.

The application must also accept audio files from arbitrary local filesystem locations.

The application must never automatically:

- copy source audio into another permanent location;
- rename source audio;
- move source audio;
- delete source audio.

Source files remain under user control.

---

## 12. Input formats

Mandatory supported formats:

- `.ogg`, including Telegram Ogg/Opus voice messages;
- `.mp3`;
- `.m4a`;
- `.wav`;
- `.webm`.

Other common audio formats may be supported where PyAV can decode them reliably without materially increasing complexity.

The application should prefer capability-based decoding over requiring manual format conversion.

Unsupported or corrupted files must produce a clear per-file error.

One bad file must not terminate an entire batch.

---

## 13. Ways to add audio

The main UI must support four input paths.

### Drag & drop

Audio files can be dropped directly into the main application window / queue area.

This is part of the MVP, not deferred polish.

### Add Files

The user can select one or multiple audio files using the standard Windows file picker.

### Add Folder

The user can select a folder.

The application adds supported audio files located directly in that folder.

Folder scanning is **non-recursive** in the MVP.

Subdirectories are not traversed.

### Inbox

A dedicated `Inbox` action scans:

```text
D:\projects\audio-transcript\inbox
```

and adds supported files located directly in that folder.

Inbox scanning is non-recursive.

Processing a file from `inbox` must not move or delete it.

---

## 14. Duplicate input behavior

Within the current queue, the same absolute source path must not be added twice.

If duplicate additions are attempted:

- ignore the duplicate;
- do not show an intrusive modal dialog;
- optionally show a short status message such as:

```text
1 duplicate skipped
```

This rule applies to files added through:

- drag & drop;
- Add Files;
- Add Folder;
- Inbox.

---

## 15. Output artifact organization

The canonical output directory is:

```text
D:\projects\audio-transcript\transcripts\
```

The default output mode is:

`Workspace / transcripts`

Outputs are organized by processing date:

```text
transcripts\
└─ YYYY\
   └─ YYYY-MM-DD\
      └─ source-name\
         ├─ transcript.txt
         └─ transcript.md
```

Example:

```text
transcripts\
└─ 2026\
   └─ 2026-08-31\
      ├─ audio_2026-08-31_12-44-51\
      │  ├─ transcript.txt
      │  └─ transcript.md
      │
      └─ meeting\
         ├─ transcript.txt
         └─ transcript.md
```

Source audio must not be copied into the transcript directory.

---

## 16. Alternative output mode

The UI also supports:

`Same folder as source`

In this mode the application creates a dedicated transcript directory beside the source file rather than placing loose generated files into the source directory.

Conceptually:

```text
meeting.m4a
meeting_transcript\
├─ transcript.txt
└─ transcript.md
```

The exact suffix may be adjusted if necessary, but the following rules must remain:

- generated artifacts are grouped together;
- source audio is untouched;
- no silent overwrite occurs.

---

## 17. Output collisions and retranscription

Generated artifacts are append-safe by default.

Existing output must never be silently overwritten.

If the target output directory already exists, create a human-readable incremented variant.

Example:

```text
meeting\
meeting_2\
meeting_3\
```

or in same-source-folder mode:

```text
meeting_transcript\
meeting_transcript_2\
meeting_transcript_3\
```

Do not use UUIDs in user-visible folder names.

Do not implement content hashing, transcript history databases or complex version management in the MVP.

---

## 18. Git handling of runtime artifacts

The following directories must exist as part of repository structure but their generated/private contents must be ignored by Git:

```text
models\
inbox\
transcripts\
```

Recommended pattern:

```text
<directory>\
└─ .gitignore
```

where all contents except the `.gitignore` marker are ignored.

The following must also be excluded from Git:

- `.venv`;
- local settings;
- downloaded model files;
- source audio;
- generated transcripts;
- temporary files;
- Python caches;
- local IDE/runtime files where applicable.

The repository must never accidentally become an archive of commercial negotiation recordings or transcripts.

---

## 19. Settings

Application settings are stored locally.

Preferred location:

```text
D:\projects\audio-transcript\config\settings.json
```

The runtime settings file must not be committed.

Settings may include:

- selected model profile;
- output mode;
- last source directory;
- default speaker;
- window geometry;
- splitter position.

Do not create a database for settings.

No dedicated settings screen is required.

---

## 20. Main UI architecture

The application uses one primary desktop window.

Do not create:

- wizard flows;
- multiple configuration screens;
- tab-based product architecture;
- separate dashboard;
- document library;
- history browser.

The main application should expose the entire normal workflow on one screen.

Conceptual layout:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Audio Transcript                                      LOCAL • OFFLINE       │
│                                                                              │
│ Model       [ Accuracy — Whisper large-v3 ▼ ]                                │
│ Speaker     [ ______________________________ ]                               │
│ Output      [ Workspace / transcripts      ▼ ]                              │
│                                                                              │
│ [ + Files ]   [ + Folder ]   [ Inbox ]   [ Remove ]   [ Clear ]             │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                        Drop audio files here                                 │
│                                                                              │
│ File                         Duration   Speaker       Status                  │
│ audio_001.ogg                   02:43   Евгений       Done                   │
│ audio_002.ogg                   01:16   Евгений       Transcribing 62%        │
│ meeting.m4a                     17:22   —              Queued                 │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ Transcript — audio_001.ogg                            [ Copy ] [ Folder ]     │
│ ──────────────────────────────────────────────────────────────────────────── │
│                                                                              │
│ Transcript text...                                                          │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ 1 completed • 1 running • 1 queued             [ progress ]                 │
│                                                    [ Stop ] [ Transcribe ]   │
└──────────────────────────────────────────────────────────────────────────────┘
```

The exact visual implementation may differ, but the interaction model and information hierarchy must remain recognizable.

---

## 21. UI principles

The UI should feel like a focused Windows work utility.

Priorities:

- clear hierarchy;
- reasonable spacing;
- readable typography;
- obvious enabled/disabled states;
- useful resizing;
- no visual clutter;
- no decorative complexity;
- no unnecessary custom widgets where standard Qt controls are sufficient.

Do not spend implementation complexity on visual effects.

Good UX is defined by workflow efficiency and clarity, not decorative design.

---

## 22. Header / global controls

The main control area contains:

### Model

Two profiles:

- `Accuracy — Whisper large-v3`
- `Fast — Whisper large-v3-turbo`

Default:

`Accuracy`

### Speaker

A free-text field.

The value acts as the default speaker assigned to files added after the value is set.

The field is optional.

Speaker name is metadata only.

It is **not** speaker diarization and must not imply automated speaker recognition.

### Output

Options:

- `Workspace / transcripts`
- `Same folder as source`

Default:

`Workspace / transcripts`

---

## 23. Queue

Each source audio file appears as one queue item.

Required visible columns:

- File
- Duration
- Speaker
- Status

Do not expose unnecessary technical columns such as:

- absolute path;
- codec;
- bitrate;
- model filesystem path;
- internal IDs.

The full source path may be exposed through a tooltip or contextual detail if useful.

The Speaker value must be editable per queue item.

This allows one batch to contain files from different speakers.

---

## 24. Queue actions

Required actions:

- `+ Files`
- `+ Folder`
- `Inbox`
- `Remove`
- `Clear`
- `Transcribe`
- `Stop`

`Remove` removes selected queued items from the UI only.

It must not delete source files or generated files.

`Clear` clears queue state.

It must not delete source files or generated artifacts.

Actions should be appropriately disabled while their operation would be unsafe.

---

## 25. Processing model

Batch transcription is sequential in the MVP.

Conceptually:

```text
file 1
  ↓
file 2
  ↓
file 3
```

Do not implement concurrent transcription.

Reasons:

- predictable CPU use;
- simpler failure behavior;
- simpler cancellation;
- simpler progress;
- lower implementation complexity.

The UI must remain responsive while transcription is running.

Long-running audio decode and inference must not execute on the main UI thread.

---

## 26. File state machine

Each queue item should have a clear state.

Expected states:

```text
Queued
Preparing
Transcribing
Saving
Done
Error
Cancelled
```

Avoid a generic ambiguous `Processing...` state when a more precise state is known.

---

## 27. Progress behavior

Where the inference runtime exposes segment timestamps, transcription progress should be estimated using:

```text
processed audio position / total duration
```

The UI should provide:

- current-file progress;
- useful batch summary.

Example:

```text
1 completed • 1 running • 3 queued
```

Do not build complex per-row animated progress widgets unless needed.

A text percentage in the queue plus one main progress indicator is sufficient.

Progress is allowed to be approximate.

Do not fabricate precision that the runtime cannot support.

---

## 28. Stop / cancellation semantics

`Stop` means:

- request safe termination of the current processing sequence;
- do not start further queued files;
- preserve already completed outputs;
- keep remaining queued items available for a later restart.

Cancellation must not intentionally leave partially written final transcript artifacts.

Temporary/intermediate resources should be cleaned up where practical.

The exact ability to interrupt a model inference call may depend on runtime behavior.

If immediate interruption is not technically safe, the UI must still behave honestly and stop before beginning the next file.

---

## 29. Error behavior

A single-file error must not terminate the remaining batch.

Example:

```text
voice_001.ogg    Done
voice_002.ogg    Error
voice_003.ogg    Transcribing
```

Do not show a modal dialog for every per-file failure.

When an errored queue row is selected, the transcript/detail area should show a useful error message.

Example:

```text
Transcription failed

Could not decode audio file.

Source:
D:\...\voice_002.ogg

Details:
<useful technical message>
```

Modal dialogs are acceptable only for errors that block the whole application or require immediate user intervention.

Error messages should be understandable first and technically useful second.

---

## 30. Transcript preview

When a completed queue item is selected, the lower section shows its full transcript.

The preview is:

- read-only;
- selectable;
- scrollable;
- plain text;
- not summarized;
- not semantically rewritten.

The application should preserve transcript readability without changing meaning.

Only trivial formatting normalization such as surrounding whitespace cleanup is acceptable.

---

## 31. Copy action

A `Copy` action must copy the clean transcript text to the Windows clipboard.

It should copy the equivalent of:

```text
transcript.txt
```

It must not copy Markdown metadata unless explicitly implemented as a separate future action.

Primary use:

```text
transcript
  ↓
Copy
  ↓
ChatGPT
```

---

## 32. Open Folder action

A `Folder` / `Open Folder` action must open Windows Explorer at the generated artifact directory for the selected completed item.

Example:

```text
D:\projects\audio-transcript\
transcripts\
2026\
2026-08-31\
audio_2026-08-31_12-44-51\
```

This must require one user action.

---

## 33. TXT output contract

`transcript.txt` contains only the transcript body.

Example:

```text
Добрый день. По поводу нашего предложения...
```

Do not include:

- Markdown metadata;
- summary;
- model commentary;
- confidence explanation;
- interpretation;
- AI-generated correction.

---

## 34. Markdown output contract

`transcript.md` contains minimal metadata plus the same transcript.

Required structure:

```markdown
# Transcript

Source: audio_2026-08-25_13-41-49.ogg
Processed: 2026-08-31 17:10
Duration: 02:43
Language: ru
Speaker: Евгений
Model: whisper-large-v3

## Transcript

Полный текст голосового сообщения...
```

Rules:

- `Source` contains the filename, not the absolute Windows path;
- `Processed` uses local date/time;
- `Duration` uses a human-readable format;
- `Language` contains detected language when available;
- `Speaker` is omitted completely if blank;
- `Model` records the actual transcription model used.

Do not expose unrelated local filesystem information in the Markdown artifact.

---

## 35. Transcript fidelity rules

The speech-to-text result must be preserved as the authoritative transcript output.

Do not add an LLM post-processing layer in the MVP.

Do not automatically:

- summarize;
- rewrite;
- improve style;
- restructure arguments;
- remove repetitions;
- correct perceived speaker mistakes;
- reinterpret unclear phrases;
- normalize meaning;
- change numbers based on context guesses.

Punctuation or textual normalization produced directly by the selected STT model is acceptable.

Application-side semantic rewriting is not.

A later optional AI interpretation layer, if ever added, must remain separate from the original transcript.

---

## 36. Language behavior

Language detection should be automatic.

A dedicated language selector is not required in the MVP.

Detected language should be included in Markdown metadata when available.

The application must remain suitable for recordings containing:

- Russian;
- English technical terms;
- product names;
- company names;
- mixed Russian/English speech.

---

## 37. Privacy and security

Privacy is a core requirement.

During normal transcription:

- source audio remains local;
- model inference remains local;
- transcripts remain local;
- no external speech-to-text API is called;
- no cloud storage is used;
- no telemetry is transmitted.

The README must clearly state this local-processing model.

Runtime audio must not be duplicated permanently unless the user explicitly copies it outside the application's normal workflow.

The application must not silently archive input files.

---

## 38. README responsibility

`README.md` is operational documentation, not the product source of truth.

It should be created or updated against the actual implementation.

It should explain:

- prerequisites;
- initial setup;
- model bootstrap;
- application launch;
- `run.bat`;
- supported formats;
- `inbox`;
- `transcripts`;
- model profiles;
- normal workflow;
- privacy behavior;
- common errors/troubleshooting.

If README behavior conflicts with this brief, the implementation or README should be corrected rather than silently changing this brief.

---

## 39. Explicit non-goals for MVP

Do not implement unless a later task explicitly authorizes it:

- cloud transcription;
- OpenAI API integration;
- other external STT APIs;
- local web server;
- backend;
- database;
- login/accounts;
- Telegram bot;
- automatic Telegram downloads;
- microphone recording;
- audio editing;
- waveform editor;
- embedded audio player;
- speaker diarization;
- automatic speaker recognition;
- transcript summary;
- semantic correction;
- negotiation analysis;
- client/project tags;
- transcript library;
- full-text search;
- history database;
- recursive folder crawling;
- concurrent multi-file inference;
- GPU requirement;
- installer;
- Windows Store/MSIX packaging;
- auto-update;
- system tray application;
- cloud sync;
- separate knowledge-management layer.

---

## 40. Testing expectations

Automated tests should focus on deterministic application logic rather than visual pixel testing.

Useful test areas include:

- supported-format filtering;
- folder scanning;
- duplicate queue prevention;
- settings load/save;
- artifact naming;
- output path generation;
- collision handling;
- Markdown generation;
- TXT generation;
- queue state transitions;
- source path handling;
- Unicode/Cyrillic filenames;
- mocked transcription boundary behavior;
- error handling where practical.

Do not create an unnecessarily complex GUI test framework only to increase test count.

A real runtime smoke test remains necessary because the core value depends on actual local audio decoding and STT inference.

---

## 41. Manual acceptance scenarios

### Scenario A — Telegram voice

Given:

```text
Telegram .ogg / Opus voice message
```

The user can:

```text
drop/select file
→ transcribe locally
→ preview transcript
→ receive TXT + Markdown
→ copy clean transcript
```

without converting audio manually.

### Scenario B — batch

Given several Telegram `.ogg` messages:

```text
Add Folder / Inbox
→ queue
→ sequential processing
→ one artifact directory per source
```

A failure in one item does not invalidate completed items or prevent later items from processing.

### Scenario C — mixed input

The user can process common combinations such as:

```text
.ogg
.mp3
.m4a
.wav
```

in one queue.

### Scenario D — persistence

After restarting the application, appropriate UI preferences such as model profile and output mode are restored.

### Scenario E — Git safety

After normal use:

```text
models\
inbox\
transcripts\
.venv\
local settings
```

must not appear as accidental Git changes containing private/generated data.

---

## 42. Quality evaluation

Initial acceptance must include real negotiation-like speech where possible.

Evaluate transcription specifically for:

- negations;
- amounts;
- names;
- technical vocabulary;
- English terms inside Russian speech;
- long sentences;
- hesitations and qualifications.

Compare `Accuracy` and `Fast` on at least one identical recording.

Record:

- audio duration;
- processing time;
- obvious transcript errors;
- subjective fidelity.

Do not optimize model choice from theoretical benchmarks alone if real local recordings provide better evidence.

---

## 43. Definition of Done

The MVP is complete when all of the following are true.

### Setup

- application runs on Windows 11;
- project uses repository-local `.venv`;
- required model files are stored locally under `models`;
- normal use requires no terminal interaction;
- `run.bat` launches the application.

### Input

- real Telegram `.ogg` / Opus can be added and decoded;
- `.mp3`, `.m4a`, `.wav` are supported;
- drag & drop works;
- Add Files works;
- Add Folder works;
- Inbox works;
- duplicate source paths are handled safely.

### Transcription

- transcription occurs locally;
- `Accuracy` uses large-v3;
- `Fast` uses large-v3-turbo;
- UI remains responsive;
- batch processing is sequential;
- processing states are understandable;
- per-file failures are isolated;
- Stop behavior is safe and understandable.

### Output

- every successful transcription generates `.txt`;
- every successful transcription generates `.md`;
- canonical dated output structure is used;
- output collisions do not overwrite existing artifacts;
- source audio remains untouched;
- transcript preview works;
- Copy works;
- Open Folder works.

### Fidelity

- no automatic summary is produced;
- no semantic rewriting layer is added;
- clean transcript remains available as the primary artifact.

### Privacy

- no external transcription API is used;
- normal inference works offline;
- no telemetry is added;
- source audio and transcripts remain local.

### Repository hygiene

- runtime artifact directories exist in repository structure;
- their contents are ignored;
- model files are ignored;
- audio files are ignored;
- transcript files are ignored;
- `.venv` is ignored;
- local settings are ignored;
- automated tests pass;
- repository is clean apart from intentional source/documentation changes.

---

## 44. Product boundary after MVP

Once the Definition of Done is satisfied, the application should be considered complete for its intended initial purpose.

Do not continue adding functionality merely because it is easy to imagine.

Further work must be driven by observed use.

Possible later work, only if evidence justifies it:

- performance tuning;
- changing default model profile;
- controlled benchmark against another Russian STT model such as GigaAM;
- improved cancellation behavior;
- minor UX corrections;
- packaging if `run.bat + .venv` proves inconvenient.

The default decision after successful acceptance is:

> stop development and use the tool.

---

## 45. Primary rule

> Audio Transcript is a local transcription utility, not an AI analysis platform.

Its responsibility begins with a local audio file and ends with a faithful, usable local transcript artifact.