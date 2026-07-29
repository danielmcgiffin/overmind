# Instructions for future coding agents

This project is a persistent StarCraft II replay-review instrument. Before installing packages, researching replay semantics, or creating a new parser, inspect the existing project and read `PROJECT_STATE.md`, `docs/replay-semantics.md`, and `docs/review-method.md`.

Reuse existing commands, the canonical time utilities, normalized schemas, cache format, derivation logic, and tests. Do not create a parallel parser or scatter SC2 loop/time constants through the codebase. Use `./sc2review bootstrap` only when the environment is missing or the lockfile changed; do not reinstall dependencies on every invocation.

Keep facts extracted from replay events and snapshots separate from strategic interpretations. Every derived finding must retain evidence references, and every coaching conclusion must be labeled as a conclusion or inference rather than presented as a replay fact. Preserve raw event evidence needed to audit reports.

Run the relevant tests and an end-to-end `./sc2review analyze ...` validation before handing off changes. Update `PROJECT_STATE.md` when parser behavior, supported builds, schemas, commands, or known limitations change.

The optional Sc2ReplayStats integration keeps pulled API payloads separate from local replay facts and strategic interpretations. Read its credential from the configured environment variable; never put authorization values in tracked files, output, cache metadata, logs, or commits. Analysis must not upload files implicitly. The upload watcher is an explicit command and must preserve hash-based duplicate protection, retryable failures, and the no-delete/no-move behavior.
