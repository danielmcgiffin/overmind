# Contributing

This repository is designed to be repeatable on a local StarCraft II replay collection.

Before changing code, read [`AGENTS.md`](AGENTS.md), [`PROJECT_STATE.md`](PROJECT_STATE.md), [`docs/replay-semantics.md`](docs/replay-semantics.md), and [`docs/review-method.md`](docs/review-method.md). Reuse the existing parser, schemas, cache, time module, derivation functions, and tests.

## Development checks

```bash
./sc2review bootstrap
./.venv/bin/python -m pytest -q
```

For an end-to-end check:

```bash
./sc2review analyze "/path/to/game.SC2Replay" --player "ExactName"
```

The output directory contains a short `review.md`, detailed `evidence.md`, and complete structured evidence. Do not commit `.SC2Replay` files, `.venv`, `.cache`, or generated `output/` directories.

Set a contributor's local replay folder in `config.toml` under `[replays].directory`, or pass `--replay-dir` for a one-off command. Never put that personal path into source documentation or a commit.

## Shareable source package

Run:

```bash
./scripts/package_repo.sh
```

This creates `dist/sc2-replay-reviewer-source.tar.gz` from the source, documentation, tests, and pinned dependency files. It deliberately excludes local replay data and generated analysis artifacts.
