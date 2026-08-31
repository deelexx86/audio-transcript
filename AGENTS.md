# AGENTS.md

## 1. Repository purpose

This repository contains `Audio Transcript`, a small local Windows desktop application for converting audio files into faithful local text transcripts.

The maintained product, UX, privacy and architectural contract is:

`BRIEF.md`

Read `BRIEF.md` before any material implementation, refactoring or review work.

---

## 2. Source of truth

Use the following priority:

1. explicit instructions in the current task;
2. `BRIEF.md`;
3. this `AGENTS.md`;
4. existing implementation and tests;
5. `README.md`.

A task instruction may override `BRIEF.md` only when the override is explicit.

Do not silently resolve a material conflict between the task and `BRIEF.md`. Surface the conflict in the final report.

Do not modify `BRIEF.md` or `AGENTS.md` unless the task explicitly requests it.

`README.md` is operational documentation and should describe the actual accepted implementation.

---

## 3. Working directory

Canonical repository and runtime root:

```text
D:\projects\audio-transcript
```

The application is intended to run in place from this repository.

Do not introduce a separate installation location, deployment environment or application server unless explicitly requested.

Use repository-relative paths where practical rather than hard-coding the absolute repository path into application logic.

---

## 4. Product boundary

Keep the implementation within the scope defined by `BRIEF.md`.

In particular, preserve these invariants:

- local speech-to-text inference;
- no external transcription API;
- no backend/server;
- no database;
- no accounts or authentication;
- no telemetry;
- source audio and generated transcripts remain local;
- transcript fidelity takes precedence over automatic rewriting or interpretation;
- the application remains a focused transcription utility.

Do not add speculative platform architecture or future-facing abstractions for features that are not currently required.

Prefer the simplest implementation that reliably satisfies the accepted workflow.

---

## 5. Implementation approach

Before changing code:

1. inspect the current repository state;
2. read the relevant source, tests and documentation;
3. understand the existing implementation before proposing replacement architecture;
4. identify the smallest coherent change that satisfies the task.

Prefer:

- clear module boundaries;
- straightforward Python;
- standard PySide6 mechanisms;
- deterministic filesystem behavior;
- explicit error handling;
- small testable units;
- maintainability over abstraction depth.

Avoid:

- unnecessary frameworks;
- dependency proliferation;
- premature plugin systems;
- generic service/repository layers without a concrete need;
- duplicated configuration;
- clever abstractions that make a small desktop utility harder to inspect.

Refactor only when it materially improves correctness, maintainability or the current task.

---

## 6. UI / UX discipline

The interaction model defined in `BRIEF.md` is part of the product contract.

Do not treat UI/UX as placeholder work.

When implementing or changing the UI:

- preserve the agreed single-window workflow;
- keep normal actions discoverable;
- keep the UI responsive during long-running work;
- use clear loading, progress, success and error states;
- avoid modal-dialog spam during batch operations;
- handle window resizing and long filenames reasonably;
- prefer native/standard Qt controls over decorative custom components;
- do not expose implementation parameters that are not meaningful user choices.

Do not redesign an accepted workflow during unrelated refactoring.

---

## 7. Filesystem and private artifacts

The repository intentionally contains these runtime directories:

```text
models\
inbox\
transcripts\
```

The directories belong to the repository structure.

Their runtime contents do not belong in Git.

Preserve directory-local ignore rules so Git tracks the directory marker while ignoring generated/private contents.

Also keep out of Git:

- `.venv`;
- downloaded models;
- source audio;
- generated transcripts;
- local settings;
- temporary files;
- caches;
- machine-specific artifacts.

Before committing, explicitly inspect Git status and ensure that no audio, transcript, model or other private/runtime artifact is staged.

Never delete, move, rename or overwrite source audio as a side effect of normal processing.

---

## 8. Environment and dependency setup

Use a repository-local Python virtual environment:

```text
.venv
```

Codex should perform terminal-based setup itself where practical, including:

- creating/updating the virtual environment;
- installing Python dependencies;
- running setup scripts;
- downloading/bootstraping local models when required;
- running tests and validation commands.

Do not ask the user to manually execute terminal commands that Codex can execute.

The user should only need to perform a manual installation when a required component genuinely needs a normal Windows GUI installer or equivalent interaction that Codex cannot perform.

Avoid introducing such manual dependencies unless materially justified.

Do not install unrelated global tooling when a repository-local solution is sufficient.

---

## 9. Model handling

Model files must remain local and must not be committed.

Use the repository-local model storage defined by `BRIEF.md`.

Do not make normal transcription depend on an implicit network download.

After model bootstrap, normal transcription should operate offline.

If a required model is missing, fail clearly and actionably.

Do not silently substitute a different speech-to-text model or profile.

---

## 10. Runtime behavior

Long-running decoding and transcription work must not block the Qt UI thread.

Preserve the sequential batch-processing model unless a task explicitly changes it.

A failure in one queue item should not corrupt completed work or unnecessarily terminate the rest of the batch.

Generated final artifacts must not be silently overwritten.

Temporary or partially written artifacts should not be presented as successful final output.

Resource cleanup must be handled deliberately, especially for:

- worker threads;
- model/runtime resources;
- opened audio resources;
- temporary files if any are introduced.

---

## 11. Testing and verification

Every implementation task must include relevant verification.

Prefer tests for deterministic behavior such as:

- path handling;
- format filtering;
- queue logic;
- settings;
- artifact generation;
- collision handling;
- Markdown/TXT generation;
- state transitions;
- Unicode/Cyrillic filenames;
- error boundaries.

Do not build elaborate GUI pixel tests merely to increase coverage.

For changes affecting actual transcription, audio decoding, model loading or Windows UI behavior, automated tests alone are insufficient. Perform the strongest practical runtime smoke available in the current environment and report what was and was not verified.

Do not claim a test passed if it was not run.

---

## 12. Documentation

Update `README.md` when implementation changes alter:

- setup;
- dependencies;
- model bootstrap;
- launch procedure;
- supported formats;
- filesystem behavior;
- user workflow;
- troubleshooting;
- privacy behavior.

Do not duplicate the full product specification from `BRIEF.md` into README.

Do not create additional durable documentation files unless the task requires them or there is a clear maintained purpose that cannot reasonably live in `BRIEF.md`, `AGENTS.md` or `README.md`.

---

## 13. Git discipline

Before implementation:

- inspect current branch and working-tree state;
- do not discard unrelated user changes;
- establish the exact starting state.

During implementation:

- keep changes within the task scope;
- do not mix unrelated cleanup;
- do not commit runtime/private artifacts.

Before completion:

- run relevant verification;
- run `git diff --check`;
- inspect `git status`;
- inspect the final diff for accidental scope expansion.

Follow the current task for branch, commit and push requirements.

Do not merge branches, rewrite shared history or modify unrelated branches unless explicitly authorized.

---

## 14. Final report

For an implementation task, report concisely:

- what was implemented;
- material design decisions;
- files materially changed;
- tests/checks run and their results;
- runtime smoke performed;
- anything not verified;
- assumptions or remaining blockers;
- Git branch/commit/push state when relevant.

Do not replace verification evidence with a narrative summary.

If the implementation materially deviates from `BRIEF.md`, state that explicitly and explain why.

---

## 15. Primary rule

> Keep Audio Transcript small, local, inspectable and reliable.

Implement the accepted workflow completely before expanding the product.