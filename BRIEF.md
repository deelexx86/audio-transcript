# Audio Transcript — Product, UX & Engineering Brief

**Repository:** `deelexx86/audio-transcript`  
**Local workspace:** `D:\projects\audio-transcript`  
**Platform:** Windows 11  
**Status:** V2 governance baseline with authorized multi-model NVIDIA GPU and native speaker attribution<br>
**Reference implementation:** `main` at `793c500aa072c0005ef282fa6a0383ef904d113b` (reviewed 2026-10-11)  
**Artifact role:** Maintained source of truth for product boundaries, user workflows, engineering constraints, and acceptance requirements.  

> This document describes both the accepted, already implemented application and the next development increments. A planned capability is **not** a claim that it currently works. For actual runtime behavior, inspect the current code and tests.

---

## 1. Product purpose and boundary

Audio Transcript is a Windows desktop application for transforming spoken content from local audio, local video, and supported online media into faithful, useful text artifacts.

Typical contexts include work, learning, meetings, lectures, negotiations, and personal tasks. The application is not limited to Telegram voice messages or commercial conversations.

**Core workflow:**

`audio / video / supported URL → source acquisition → speech recognition → preview → TXT / Markdown → user's downstream workflow`

The application's principal responsibility **ends with an accurate and accessible transcript**. Summarization, interpretation, meeting notes, dialogue reconstruction, and other semantic work belong to tools selected separately by the user (for example, ChatGPT). They are **not** part of the planned application pipeline.

Accuracy of meaning and preservation of critical wording take priority over literary polish. Special attention is required for negations, numbers, amounts, names, dates, technical terminology, qualifiers, and Russian/English code-switching.

**Out of scope for the current roadmap:** automatic summaries, inferred dialogue rewriting, speaker identity recognition, live microphone capture, embedded chat/LLM analysis, document management, cloud inference or synchronization, accounts, backend/server, and databases. Any future expansion requires a distinct owner decision.

---

## 2. Current accepted product — implemented baseline

The following describes capabilities already present in the referenced `main` implementation, not future requirements:

- **Desktop/runtime:** Python, PySide6, repository-local `.venv`, `run.bat`, no separate application installation.
- **Local STT:** `faster-whisper` + CTranslate2, CPU `int8`, repository-local `Whisper large-v3` (Accuracy) and `large-v3-turbo` (Fast). Model download/bootstrap is explicit; after setup, local-file transcription can work offline.
- **Input:** local audio including Telegram Ogg/Opus and AMR; many local video containers; supported individual YouTube video URLs through `yt-dlp`. PyAV decodes the selected audio stream.
- **Queue:** drag & drop, Add Files, non-recursive Add Folder and Inbox, YouTube Add Link, deduplication, ordering/reordering, column sorting, editable per-file speaker, sequential processing, Retry Selected and Remove Completed.
- **Processing:** responsive worker-based UI, per-file statuses and progress, cancellation requests, isolated per-file failures, bounded YouTube retry behavior.
- **Outputs:** append-safe `transcript.txt` and `transcript.md`, preview, Copy and Open Folder, dated workspace folders or same-source-folder mode for local files.
- **Localization:** English, Russian, Spanish, German; Qt Linguist catalogs, immediate language switching, persisted interface choice and localized documentation.
- **Private runtime workspace:** ignored `models/`, `inbox/`, `transcripts/`, settings and temporary content.

Do not regress any of these accepted workflows while implementing V2 increments. Validate against the current code and README, not against assumptions from the original MVP.

---

## 3. Stable engineering invariants

1. **GPU is the primary target.** Fresh settings select on-device NVIDIA CUDA. The two existing Whisper models retain explicit local CPU and local NVIDIA CUDA execution offline after setup. Remote NVIDIA CUDA runs on a Windows host chosen by the user through existing OpenSSH access. Retain previously selected modes and never substitute a model or fall back to CPU.
2. **External transfers are explicit and contextual.** YouTube fetching acquires source media. Selecting Remote NVIDIA GPU authorizes temporary transfer of each queued media file to the configured SSH host. Show the active mode and transfer phase. Authenticate the host, preserve local storage for final transcripts, and never switch execution modes automatically.
3. **Source preservation.** Do not rename, move, modify, delete, or permanently duplicate local source media as a processing side effect.
4. **Faithful transcript.** No automatic LLM rewriting, semantic correction, summarization, or inferred dialogue restructuring. STT model punctuation is acceptable.
5. **Sequential, observable work.** Preserve a responsive GUI, predictable queue order, cancellation semantics, isolated failures, and inspectable task states. Concurrent transcription requires separate justification.
6. **Safe artifacts.** Never silently overwrite successful outputs. Preserve atomic/complete-write behavior and human-readable filenames. Failures must not masquerade as successful files.
7. **Private data do not enter Git.** Source media, models, transcripts, credentials, local settings, downloaded YouTube media, and generated caches remain ignored. Preserve tracked `.gitignore` markers for the runtime directories.
8. **Small inspectable architecture.** Keep Python/PySide6/PyAV and the existing desktop workflow unless an evidence-backed improvement requires a bounded change. Avoid speculative service layers or introducing a database by default.
9. **Truthful status.** Show what the application knows; no fabricated ETA, upload progress, quality promises, or successful verification claims.

---

## 4. Input and output contract

### 4.1 Inputs

The application accepts media through local file/folder selection, drag & drop, `inbox/`, and supported YouTube URLs. The current supported extension list and URL forms are defined in the implementation and maintained in README; they should not be duplicated in multiple competing hard-coded lists.

Folder and Inbox scanning are non-recursive unless a future task explicitly changes this. For video, speech recognition uses an audio track; video imagery and embedded subtitles are not transcribed. Unsupported, unreadable, encrypted, or silent media must yield understandable per-item errors and must not terminate the remaining batch.

YouTube media acquisition is a separate, internet-dependent stage. Downloaded intermediate media stays temporary and is removed on normal completion/failure/cancellation. Hard termination may leave residual temporary files, which stabilization should handle safely.

### 4.2 Workspace and outputs

The repository is both source checkout and application runtime home:

```text
D:\projects\audio-transcript\
├─ .venv\                 # local, ignored
├─ models\                # tracked directory marker; contents ignored
├─ inbox\                 # tracked directory marker; contents ignored
├─ transcripts\           # tracked directory marker; contents ignored
├─ config\                # local settings and temporary runtime material
├─ src\
├─ tests\
├─ BRIEF.md
├─ AGENTS.md
└─ run.bat
```

Canonical workspace output:

```text
transcripts\YYYY\YYYY-MM-DD\source-name\
    transcript.txt
    transcript.md
```

The same-folder mode creates a dedicated `_transcript` directory beside the source. If an output directory already exists, use a readable incremented suffix (`_2`, `_3`, ...). YouTube output uses the workspace irrespective of the same-folder preference.

`transcript.txt` contains **only recognized text**. `transcript.md` records compact descriptive metadata such as source, processing date/time, source duration, detected language, optional speaker, actual engine/model, and a matching transcript body. For YouTube, it may also include the normalized source URL and title. Do not expose private system paths unnecessarily.

Future engines must preserve these output contracts. GPU runs record the execution mode in Markdown. The existing TXT format and older artifacts remain valid. When the selected model returns native speaker-attributed text, also save `transcript.speakers.txt` with anonymous labels and original timings where emitted. Keep the optional user-entered speaker as file metadata. Do not guess identities or timestamps. Use native full-recording state for speaker consistency when available. Reject over-limit inputs explicitly and report detected runtime truncation instead of presenting it as complete.

---

## 5. UI and localization contract

The main window remains a focused workspace for source intake, queue control, progress, transcript preview, copying, and opening outputs. It must not become a configuration dashboard.

Current interface languages — **English, Russian, Spanish, German** — remain supported. Any new user-visible status, timer, label, dialog, error explanation, or setting must be localized in all four Qt catalogs; editable `.ts` and compiled `.qm` are maintained together. Internal identifiers and artifact content must not depend on translated text. Native system dialogs may follow Windows locale.

Keep execution mode and SSH destination in the **Acceleration** dialog. The main window shows the selected execution mode and retains frequently changed file options. Lock changes to execution mode, SSH destination and model during an active batch. Preserve efficient operation at ordinary Windows window sizes and display scaling.

Provide a **Model Manager** for the complete catalog. Show the upstream model, available checkpoint, license, runtime, numeric precision, supported mode, capabilities, installation state and observed preflight status. Separate device/runtime availability and SSH failures from missing weights. Model installation and scoped removal must be observable and must support cancellation where practical. Keep unavailable candidates visible without presenting them as usable.

---

## 6. R1 — Processing Time, Speed & ETA (next functional increment)

### 6.1 User outcome

For a long recording, the user can see how long processing has taken, whether the operation is moving forward, and a reasonable **approximate remaining-time estimate when enough evidence exists**. The same timing contract should be reusable by later CPU, GPU, and cloud engines.

### 6.2 Required information

While processing a file, show:

- **Elapsed wall-clock time** since active processing began, updated while the worker is busy.
- **Processing phase** (for example, preparing/loading, downloading, transcribing, saving, waiting to retry).
- **Progress** where grounded in a measurable media position or documented download signal.
- **Estimated time remaining (ETA)** only while the estimate is defensible; otherwise show a localized state such as `Оценивается…` or `Недоступно`.
- **Effective transcription speed**, where measurable, expressed consistently as audio-time processed per wall-clock time (`× realtime`).
- **Actual processing duration** when complete, available for later comparison/history and, where appropriate, new artifact metadata.

For a sequential batch, preserve a clear completed/running/queued summary. A **whole-batch ETA is optional** and must not be shown unless sufficient durations and representative throughput are available; never extrapolate uncertain YouTube/network delays as known.

### 6.3 Estimation contract

- Use monotonic elapsed-time measurement for durations, not wall-clock timestamps vulnerable to clock changes.
- Distinguish **model loading**, source acquisition, SSH transfer, transcription, and artifact saving. Do not extrapolate one phase's speed into another.
- For local `faster-whisper`, progress may use completed segment time relative to audio duration. Smoothed processing throughput may estimate remaining transcription time.
- Suppress early unstable numerical estimates until meaningful progress/time samples exist. Smooth updates and round appropriately rather than showing false second-level precision.
- Refresh elapsed time on the UI clock even if no new segment has been delivered, without blocking the Qt event loop.
- If duration is unknown, progress stalls, throughput is unreliable, or an opaque provider supplies no usable progress, prefer `ETA unavailable` over a guess.
- On Stop, error, or completion, stop the running timer, retain the measured elapsed duration for that task, and never show a running ETA for a terminal state.
- Retry timing starts a new attempt; do not present a previous attempt's estimate as belonging to the current run.

### 6.4 R1 acceptance

- Current-file elapsed timer works during model startup and lengthy inference, including periods without progress callbacks.
- ETA appears only after meaningful evidence; it remains approximate and avoids pathological jumps or negative values.
- Stop, failures, retries, batch transitions, and YouTube download/retry states display coherent times and reset correctly.
- Existing transcript accuracy, sequential queue behavior, output safety, and four interface languages are unaffected.
- Deterministic tests cover timing and estimation boundaries using a controllable clock; a long real-world audio smoke evaluates usability of ETA.

---

## 7. R2 — CI and runtime stabilization

Add GitHub Actions verification suitable for a public Windows/Python desktop repository:

- Python tests and import/runtime smoke without downloading several-gigabyte STT models.
- Translation-catalog completeness/build checks for all four languages.
- Packaging/import sanity as appropriate; no installer is required.
- No private media, model files, API credentials, or personal transcripts in CI artifacts or commits.

Review operational edge cases supported by evidence: cancellation and closing during work, incomplete or leftover temporary downloads, corrupted settings, artifact-write failures, file/path errors, and long-running tasks. Prefer targeted fixes and regression tests to a broad refactor. CI cannot replace real local audio/video and GUI acceptance.

---

## 8. R3 — Settings UX

Move growing configuration out of the main workspace into a dedicated Qt settings window/dialog, without changing the application framework.

Potential groups are General, Model Manager, Acceleration, and Files/History; **only expose groups when the associated feature exists**. Preserve live usability and the current model/output/speaker workflow. Avoid building empty speculative screens.

Store non-secret preferences in ignored `config/settings.json`. Future API secrets must be handled separately by a suitable OS credential facility, never in Git, plain application settings, or logs.

Acceptance: clear access to settings, persisted behavior, predictable changes during an active job, responsive layouts, and translation coverage in all four languages.

---

## 9. R4 — Transcript History

Make successful prior transcription results accessible from inside the application without requiring Explorer navigation.

Minimum capabilities:

- Discover existing results in `transcripts/`, including artifacts created before the history feature.
- Present source name/title, processing date, duration, engine/model where available, and artifact location.
- Open/preview the existing transcript, Copy, and Open Folder.
- Search/filter by available filename/title/source metadata.
- Handle missing, moved, partially written, malformed, or inaccessible files gracefully.

Prefer filesystem artifacts as the source of truth. A small private local index may track outputs written outside the workspace in **Same folder as source** mode, without copying transcript content. Do not add a database, mandatory transcript ingestion, or full-text indexing without a demonstrated need.

History is **not** a conversation compiler, semantic library, or document-management system.

---

## 10. R5 — Multi-model NVIDIA GPU inference

- Preserve the two CTranslate2 Whisper models in all three execution modes. Support additional ASR families over verified Windows OpenSSH using isolated, on-demand CUDA inference. Record actual model and execution precision in Markdown.
- Store new remote weights and model caches under `D:\models\audio-transcript`, with a separate directory per checkpoint. Keep local Whisper weights in the repository's ignored `models\` directory. Do not implicitly fetch weights during inference.
- Before transferring media, check the selected checkpoint and required runtime. Return recognized text and native speaker information over SSH. Save final artifacts on the primary computer and release temporary media and GPU resources on completion, error, cancellation, or lost connection.
- Validate feasible CUDA configurations on the available NVIDIA hardware with identical Russian, English, mixed-language and multi-speaker inputs. Include longer recordings for long-form candidates. Measure fidelity, completeness, speaker attribution, timing, throughput, storage and peak GPU memory. Document scope and use the legacy CPU path for regression coverage.

## 11. R6 — Cloud STT

Cloud transcription is outside the authorized roadmap. YouTube source acquisition, explicit model downloads and user-selected SSH processing are the supported network operations.

## 12. Development sequence and acceptance gates

| Step | Status at this brief | Execution boundary |
|---|---|---|
| R0 — Product contract refresh | ACCEPTED — 2026-10-11 | Maintained product and roadmap contract; supersedes the MVP-only brief |
| R1 — Processing Time & ETA | Planned / next | Independent timing instrumentation, credible progress estimation, localized UI and tests |
| R2 — CI & Stability | Planned | Windows automated verification and bounded reliability fixes |
| R3 — Settings UX | Planned | Dedicated settings UI, no change to core user workflow |
| R4 — History | Planned | Access existing transcript artifacts in-app without duplicating content |
| R5 — Multi-model NVIDIA GPU | Authorized | Catalog, managed weights, on-demand Windows SSH CUDA, native speaker outputs and GPU validation |
| R6 — Cloud STT | Out of scope | Requires a separate roadmap decision |
| R7 — Integration acceptance | Planned after approved changes | Revalidate local baseline, additional modes, localization, docs, privacy and Git hygiene |

Use scoped Codex tasks with an accepted starting SHA, bounded implementation, proportional tests, manual smoke where needed, and follow the task’s Git publication instructions. Do not create extra governance documents merely to restate this brief.

**Compatibility criterion across stages:** a user with the existing Windows installation and local model files can continue transcribing local audio/video with the accepted CPU profiles and familiar TXT/Markdown outputs.

---

## 13. Documentation and public repository

`BRIEF.md` states maintained product intent; `AGENTS.md` states agent/repository operating instructions; README files document actual usage. Keep English, Russian, Spanish and German README guides aligned when user-facing behavior changes.

The previous `BRIEF.md` originated as a one-time MVP contract. This consolidated revision supersedes its outdated restrictions (such as the absolute ban on network input and the original Telegram-only framing) while preserving local privacy and faithful transcript principles. Public documentation must distinguish **offline local processing**, **online source acquisition**, **opt-in processing on a selected SSH host**, and **explicit model downloads**.

Do not include private recordings, personal transcript content, credentials, downloaded models, or private runtime paths in public repository files.

---

## 14. Primary rule

> Improve the user's speed and reliability of reaching a faithful transcript, without turning Audio Transcript into an automatic interpretation platform.

When a proposed feature does not clearly strengthen that result, defer it until actual usage provides evidence.
