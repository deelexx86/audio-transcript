# Audio Transcript — Product, UX & Engineering Brief

**Repository:** `deelexx86/audio-transcript`  
**Local workspace:** `D:\projects\audio-transcript`  
**Platform:** Windows 11  
**Status:** V2 ACCEPTED — 2026-10-11; R0 governance baseline  
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

**Out of scope for the current roadmap:** automatic summaries, dialogue compilation/export, speaker diarization or recognition, embedded chat/LLM analysis, document-management platform, cloud synchronization, accounts, backend/server, and database by default. Any future expansion requires a distinct owner decision.

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

1. **Local is the default.** The existing CPU mode must remain usable with no cloud account, API key, or network connection after local setup. Future GPU support must also perform inference locally.
2. **External transfers are explicit and contextual.** YouTube fetching uses the network to acquire source media. A future cloud STT option may upload media **only after the user deliberately selects that mode and is clearly informed**. Never silently switch from local to cloud.
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

Future engines must preserve these output contracts. Engine-specific fields may be added without rewriting or invalidating older artifacts.

---

## 5. UI and localization contract

The main window remains a focused workspace for source intake, queue control, progress, transcript preview, copying, and opening outputs. It must not become a configuration dashboard.

Current interface languages — **English, Russian, Spanish, German** — remain supported. Any new user-visible status, timer, label, dialog, error explanation, or setting must be localized in all four Qt catalogs; editable `.ts` and compiled `.qm` are maintained together. Internal identifiers and artifact content must not depend on translated text. Native system dialogs may follow Windows locale.

The next UI improvement introduces a **separate Settings window/dialog**, retaining only frequently changed choices and concise active-engine status in the main window. Preserve efficient operation at ordinary Windows window sizes and display scaling. Implement this as a bounded reorganization of the existing UI, not a framework rewrite.

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
- Distinguish **model loading**, source acquisition, transcription, and artifact saving. Do not extrapolate one phase's speed into another.
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

Potential groups are General, Local Models, Acceleration, Cloud STT, and Files/History; **only expose groups when the associated feature exists**. Preserve live usability and the current model/output/speaker workflow. Avoid building empty speculative screens.

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

## 10. R5 — Optional local GPU inference

GPU support is a **conditional capability**, not a justification to destabilize the working CPU engine.

First run a bounded feasibility and benchmark task on the **actual installed hardware and drivers**. Establish device compatibility and compare representative recordings against the accepted CPU baseline for speed, fidelity, reliability, memory, and setup complexity. The backend is selected from evidence; examples include CTranslate2/CUDA where supported or an alternative Vulkan-capable local backend where practical.

Proceed to implementation only if the measured benefit and maintainability justify it.

If implemented:

- Keep CPU as a fully functional fallback **selected explicitly or predictably**, with no hidden downgrade of model quality.
- Detect/report unavailable devices, missing driver/runtime components, model-format requirements, and configuration errors intelligibly.
- Preserve the existing queue, transcript, artifact, localization, Stop, and timing/ETA contracts.
- Do not demand a discrete GPU for ordinary installation or use.

---

## 11. R6 — Optional cloud STT provider

A cloud STT option may improve latency or quality for some recordings, but it changes confidentiality, cost, network, and failure behavior. It must remain **opt-in**, not the default.

Provider and initial model are **not yet selected**. First compare concrete candidates on representative Russian, English-term, short and long recordings, considering fidelity, latency, actual total cost, accepted media formats and upload size/duration limits, and integration complexity. Select one first production provider based on evidence. Do not implement multiple providers just because an abstraction permits it.

Implementation requirements, if authorized:

- Explicit user choice of cloud processing and clear indication that media is transmitted to the provider; no automatic local-to-cloud fallback.
- Protect API credentials using an appropriate Windows secret store, separate from ordinary settings, source code, Git, logs, and exported transcripts.
- Honor provider input limits. For long recordings, any local conversion/chunking must preserve speech continuity as well as practical; explain residual limitations.
- Bound retries, timeouts, upload operations, and cost exposure. Show real elapsed time and only credible progress/ETA.
- No raw media, auth headers, credentials, or provider response payloads in persistent diagnostic logs.
- Output remains standard UTF-8 TXT/Markdown with actual provider/model identification and source provenance. Source media remains unchanged; local and cloud histories remain accessible through the same result browser.
- Local CPU transcription remains fully usable if the network or provider fails or the user has no API key.

Users decide whether a particular recording (especially recordings of other people) is appropriate for external transmission. The app must not obscure that decision.

---

## 12. Development sequence and acceptance gates

| Step | Status at this brief | Execution boundary |
|---|---|---|
| R0 — Product contract refresh | ACCEPTED — 2026-10-11 | Maintained product and roadmap contract; supersedes the MVP-only brief |
| R1 — Processing Time & ETA | Planned / next | Independent timing instrumentation, credible progress estimation, localized UI and tests |
| R2 — CI & Stability | Planned | Windows automated verification and bounded reliability fixes |
| R3 — Settings UX | Planned | Dedicated settings UI, no change to core user workflow |
| R4 — History | Planned | Access existing transcript artifacts in-app without duplicating content |
| R5 — GPU feasibility/integration | Conditional | Benchmark first; implementation only after acceptance of evidence |
| R6 — Cloud STT | Conditional | Provider choice, privacy and long-audio design gate before implementation |
| R7 — Integration acceptance | Planned after approved changes | Revalidate local baseline, additional modes, localization, docs, privacy and Git hygiene |

Use scoped Codex tasks with an accepted starting SHA, bounded implementation, proportional tests, manual smoke where needed, and PR/merge after owner acceptance. Do not combine GPU, cloud, history, and UI redesign into one implementation prompt. Do not create extra governance documents merely to restate this brief.

**Compatibility criterion across stages:** a user with the existing Windows installation and local model files can continue transcribing local audio/video with the accepted CPU profiles and familiar TXT/Markdown outputs.

---

## 13. Documentation and public repository

`BRIEF.md` states maintained product intent; `AGENTS.md` states agent/repository operating instructions; README files document actual usage. Keep English, Russian, Spanish and German README guides aligned when user-facing behavior changes.

The previous `BRIEF.md` originated as a one-time MVP contract. This consolidated revision supersedes its outdated restrictions (such as the absolute ban on network input and the original Telegram-only framing) while preserving local privacy and faithful transcript principles. Public documentation must distinguish **offline local processing**, **online source acquisition**, and **opt-in future cloud recognition**.

Do not include private recordings, personal transcript content, credentials, downloaded models, or private runtime paths in public repository files.

---

## 14. Primary rule

> Improve the user's speed and reliability of reaching a faithful transcript, without turning Audio Transcript into an automatic interpretation platform.

When a proposed feature does not clearly strengthen that result, defer it until actual usage provides evidence.
