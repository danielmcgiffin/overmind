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
- `sc2replaystats.json` — optional raw supplemental data pulled from the configured Sc2ReplayStats account.
- `report.md` — compatibility index linking the separated outputs.

All player-facing timestamps use real elapsed time. Raw game loops remain the canonical internal coordinate.

## Optional Sc2ReplayStats pull and upload

The analyzer can pull the account's latest replay from Sc2ReplayStats on each analysis. Blizzard's local `s2protocol` extraction remains authoritative, and external data is kept separate in `sc2replaystats.json` and the evidence report. Analysis never uploads a local replay.

Set the authorization value in the environment using the variable named by `[sc2replaystats].auth_env`; do not put the key in `config.toml`, source code, reports, or Git:

```bash
export SC2REPLAYSTATS_AUTH='hash;token;timestamp'
./sc2review analyze "game.SC2Replay" --player "PlayerName"
```

The API response is cached under `.cache/sc2replaystats/<replay-hash>/` for the configured TTL. Force a fresh pull with:

```bash
./sc2review analyze "game.SC2Replay" --player "PlayerName" --refresh-sc2replaystats
```

If the credential is absent, the service is unavailable, or the remote latest replay cannot be confidently matched to the local file, local analysis still completes and records the external status as `not_configured`, `error`, or `latest_remote_unverified`.

To upload every replay currently in the configured Multiplayer folder, then keep watching for new files:

```bash
./sc2review upload --watch
```

Use `--replay-dir "/path/to/Multiplayer"` when `[replays].directory` is not configured. Uploads are keyed by replay content hash and recorded in `.cache/sc2replaystats/upload-state.json`; already-submitted replays are skipped and failed uploads are retried on the next scan. Sc2ReplayStats receives the replay file through its documented upload endpoint, so use this watcher only when you intend to share the folder's replays.

The default coaching lens is spending and resource conversion: meaningful float episodes, supply room, worker/base benchmarks, production capacity, larva when observable, and bounded purchase equivalents. Combat is included in the short review only when it explains a spending window or replacement need.

For a shareable checkout, commit the source, documentation, tests, `pyproject.toml`, and `uv.lock`. Do not commit `.venv`, `.cache`, `output`, or replay files; those are local and are ignored by Git.

To create a portable source archive instead, run `./scripts/package_repo.sh`. Repository setup, remote selection, and licensing are intentionally left to the maintainer.

The authoritative extraction path is Blizzard's `s2protocol`. `sc2reader` is an optional convenience adapter and is never the canonical internal model.
