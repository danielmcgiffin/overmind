# overmind

SC2 Replay Agent — persistent, local StarCraft II replay analysis for causal coaching reviews.

Persistent, local StarCraft II replay analysis for causal coaching reviews. The player-facing output is intentionally short; the complete audit trail is generated separately.

Read [`AGENTS.md`](AGENTS.md) and [`PROJECT_STATE.md`](PROJECT_STATE.md) before changing the project. Bootstrap once with:

```bash
./sc2review bootstrap
```

Analyze a replay with:

```bash
./sc2review analyze "/path/to/game.SC2Replay" --player "PlayerName"
```

To configure a personal replay folder, edit `[replays].directory` in [`config.toml`](config.toml):

```toml
[replays]
directory = "/path/to/StarCraft II/Replays/Multiplayer"
```

Then use the filename from that folder:

```bash
./sc2review analyze "game.SC2Replay" --player "PlayerName"
```

An explicit full path still works, and `--replay-dir` can override the configured folder for one command. The config template contains no personal replay path.

The default output is written below `output/<replay-content-hash>/`. The replay itself is never copied into the repository or output cache.

Each analysis bundle contains:

- `review.md` — 200–400 word spending-first coaching review with a float timeline and one measurable trigger.
- `evidence.md` — detailed timeline, tables, caveats, methodology, and source references.
- `replay.json`, `timeline.csv`, `engagements.json`, and `findings.json` — complete structured evidence.
- `report.md` — compatibility index linking the separated outputs.

All player-facing timestamps use real elapsed time. Raw game loops remain the canonical internal coordinate.

The default coaching lens is spending and resource conversion: meaningful float episodes, supply room, worker/base benchmarks, production capacity, larva when observable, and bounded purchase equivalents. Combat is included in the short review only when it explains a spending window or replacement need.

For a shareable checkout, commit the source, documentation, tests, `pyproject.toml`, and `uv.lock`. Do not commit `.venv`, `.cache`, `output`, or replay files; those are local and are ignored by Git.

To create a portable source archive instead, run `./scripts/package_repo.sh`. Repository setup, remote selection, and licensing are intentionally left to the maintainer.

The authoritative extraction path is Blizzard's `s2protocol`. `sc2reader` is an optional convenience adapter and is never the canonical internal model.
