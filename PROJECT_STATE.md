# Project state

Last updated: 2026-07-29

## Architecture

The project is a local Python package exposed through `./sc2review` and `uv run sc2review`. The flow is:

1. `parser.py` opens the MPQ, selects an exact bundled s2protocol module when available or the nearest lower generated protocol module when the generated schemas decode the replay, and emits normalized metadata, participants, attributes, tracker events, game events, and messages.
2. `derive.py` turns normalized events into unit lifecycles, snapshots, worker/supply/resource facts, losses, army composition/value, structure/upgrade/expansion timings, candidate economy flags, and auditable resource-float episodes with bounded purchase equivalents.
3. `engagements.py` clusters deaths using both game-loop proximity and map position, then computes local losses, pre/post state, and approximate reinforcement observations.
4. `review.py` generates structured facts and explicitly labeled inferences, including candidate negative turning points, favorable transitions, and a causal chain. Killer-attributed losses are retained per engagement so cheap-unit trades are not automatically labeled failures.
5. `reports.py` writes the concise spending-first `review.md`, the detailed audit `evidence.md`, and a compatibility `report.md` index; `pipeline.py` handles the content-hash cache and replay-specific outputs.
6. `sc2replaystats.py` optionally pulls the account's latest remote replay as supplemental external data and provides an explicit hash-tracked folder uploader. It uses the documented HTTPS API, keeps upload state locally, and never merges remote payloads into canonical extraction facts or coaching inferences.

The canonical internal model is JSON-compatible dictionaries with stable evidence IDs. Parser-specific dictionaries are retained only inside each normalized event's `payload` for auditability; downstream code uses normalized top-level fields. The current derivation facts version is `1.2`, including float start-bank fields, float episodes, and bounded purchase power.

## Installed tools and selection decisions

- `uv` manages the project environment and checked-in `uv.lock`.
- `s2protocol==5.0.16.97563.0` is the authoritative low-level replay decoder and provides protocol modules through build `97563`.
- `sc2reader==1.9.0` is retained only for convenience/compatibility. The current parser uses it only as a fallback for legacy MPQ header bootstrap decoding; it is not the canonical event model.
- `pytest==8.3.5` runs the automated tests.
- The parser includes a narrow `imp` compatibility shim because the pinned s2protocol versions loader still imports Python's removed `imp` module on Python 3.13. The generated decoder code itself is not forked.

`./sc2review bootstrap` is idempotent and runs `uv sync --locked`. Analysis commands use the existing `.venv` and never bootstrap or reinstall dependencies.

## Current commands

```bash
./sc2review bootstrap
./sc2review analyze "/path/to/game.SC2Replay" --player "ExactName"
./sc2review analyze "/path/to/game.SC2Replay" --player "ExactName" --refresh-sc2replaystats
./sc2review upload
./sc2review upload --watch
uv run sc2review analyze "/path/to/game.SC2Replay" --player "ExactName"
./sc2review inspect "/path/to/game.SC2Replay"
./sc2review timeline "/path/to/game.SC2Replay" --player "ExactName"
./sc2review engagements "/path/to/game.SC2Replay" --player "ExactName"
./sc2review validate "/path/to/game.SC2Replay"
```

The normal analyze command writes `output/<sha256>/replay.json`, `timeline.csv`, `engagements.json`, `findings.json`, `sc2replaystats.json`, `review.md`, `evidence.md`, `report.md`, and `run-metadata.json`. `review.md` is a 200–400 word spending-first coaching output with five default sections; `evidence.md` owns the detailed audit trail. Normalized extraction is cached under `.cache/sc2review/<sha256>/replay.json` and is reused only when its replay hash, schema version, and parser version still match. Optional external responses are cached under `.cache/sc2replaystats/<sha256>/` with a 15-minute default TTL.

Replay lookup is persistent but user-local: set `[replays].directory` in `config.toml`, then pass a filename. An explicit path or `--replay-dir` overrides it. The shareable config template intentionally leaves the directory empty.

## Verified status

- The project bootstraps successfully in the current workspace.
- `pytest` passes all 22 tests.
- Synthetic normalized event fixtures validate the vertical slice, including spatial engagement separation and approximate reinforcement-wave detection.
- The requested licensed replay fixture was not mounted in this workspace. An auxiliary local replay was decoded end to end without parser warnings: base build `94137`, compatible lower protocol `93333`, 616 tracker events, 1,392 game events, 14 messages, and 77 player-stat snapshots. `tests/fixtures/README.md` documents how to supply a local fixture.
- The auxiliary analysis produced five spatial engagements and a full output bundle under the replay hash directory. Its conclusions are validation output, not hard-coded rules.
- No Blizzard replay file is checked in or copied into project outputs.
- A recent local Faster-speed replay was decoded end to end at base build `97563`. Its favorable armored-unit removal, worker-line damage, income disruption, and later bank-conversion guidance were checked against the raw tracker events. Report prose and macro benchmarks are replay-dynamic rather than copied from another game.
- The newest local replay at the time of this update was `Rainfall LE (11).SC2Replay`, hash `5cc6ee579702b9284a4e801f69520ff4d6386e6785b3c1dc5d6020a70328c93d`. It produced a 5:00–9:40 real-time float episode peaking at 3,070 minerals / 806 gas, with 48 workers, 3 bases, 26 supply room, 3 tracked unit-producing structures, and 13 observed larva. The report treats the late supply pressure and candidate unconverted production as evidence-backed constraints, not proof of queue state or attention.

## Known limitations

- A real replay needs a matching or safely decodable lower generated protocol module in the installed s2protocol release. Builds newer than the bundled maximum or older than the bundled minimum fail clearly and list recent supported protocol builds.
- `s2protocol` provides player-stat snapshots, but it does not provide full combat simulation state, vision, camera attention, control-group use, intent, or exact order/queue semantics for every build.
- Unit positions are event/snapshot observations. The project never interpolates positions between sparse tracker observations.
- Worker production pauses cannot be proven from a worker-count plateau alone; supply pressure, resource floats, and plateaus are emitted as candidates with qualifications.
- Production capacity counts known unit-producing structures, not empty queues. Larva is `null` when no Larva was observed, and purchase equivalents distinguish resource-only bounds from immediate bounds constrained by supply, larva, and tech.
- A float episode may overlap fighting because the tracker records deaths over an interval. “Bank spent after fighting” is only true when a later stats snapshot shows a substantial drop; no later snapshot is treated as proof of conversion.
- Unit-value fallback uses a small transparent common-unit cost table. Where available, player-stat active-force resource values are preferred. Unknown units remain in an unknown bucket rather than being invented.
- A candidate engagement requires at least two players, two deaths, and spatially compatible death positions. Games with missing death positions can have fewer detected engagements.
- Engagement classification is still heuristic. It uses local losses, known costs, killer attribution, and a small armored-core table; it does not simulate combat or prove the exact tactical sequence between sparse tracker events.
- MMR is sourced from lobby scaled rating when present; APM is currently marked unavailable in decoded replay streams.
- Expansion timing is based on completed town-hall tracker units after the first town hall and is approximate for morphs/old builds.

## Replay versions tested

The named licensed fixture was not mounted. An auxiliary local replay with base build `94137` was decoded using compatible lower protocol module `93333`; exact/compatible protocol selection and unsupported-build handling are unit-tested.

## Next sensible improvements

1. Run the supplied licensed replay fixture end to end and record its actual base build, decoded stream counts, map, and broad sanity checks here.
2. Add a small versioned unit-cost/resource dataset with explicit patch provenance and use it to improve fallback army valuation.
3. Add a build-specific attribute name table and optional summary-stream adapter for APM and richer end-state values.

## Decisions not to casually reopen

- Game loops are the canonical stored timestamp. Game-clock seconds are loops/16; real elapsed seconds are loops/(16 × speed factor).
- `Faster` is the official metadata label. `Fastest` is accepted only as an input alias.
- Facts, derived facts, and coaching inferences remain separate and are linked with evidence IDs.
- Engagements require time and spatial proximity; losses per minute alone never define a fight.
- The earliest mistake is not automatically the decisive mistake; the report ranks negative state changes and evaluates later events as consequences when the evidence supports that sequence.
- A favorable trade in a winning game is not relabeled as a tactical error just because the reviewed player lost more unit objects. The current report emphasizes post-trade conversion: supply, injects, spending, and follow-up army production.
- Small harassment trades are classified separately: a local validation replay demonstrated that a small force killing a worker and a production/supply structure is favorable harassment. The replay records the deaths and killer attribution; an exact worker-pull interval is not a labeled replay field and remains a supported contextual interpretation rather than an invented fact.
- Raw Zerg Drone deaths are decomposed into worker-consuming structure starts plus remaining worker-loss events. The report no longer treats every Drone `UnitDied` event as combat damage; exact builder identity remains unavailable and is labeled as a heuristic.
- User-facing timestamps are real elapsed time only. Game loops remain canonical internal coordinates, but reports, reviews, timeline CSV, and inspect output do not expose alternate clock timestamps.
- `review.md` is relevance-gated: each candidate finding must materially affect the result, explain the primary diagnosis, or be actionable in at least two of those three dimensions. Compression limits it to 200–400 words, five spending-first sections, and one measurable next-game trigger; `evidence.md` retains the omitted detail.
- Every `review.md` includes a concise Macro benchmark/reality comparison: a replay-specific worker/saturation spending checkpoint versus the actual worker count, bank, and spending state.
- Macro benchmarks are time-aware: a late base does not retroactively raise the worker checkpoint for an earlier float episode. Reviews explicitly identify late expansion transitions that turn pressure into an unintended two-base commitment.
- Spending episodes are the primary coaching object. The report ranks float and conversion before supply, worker saturation, production/larva, reinforcement continuity, technology, and combat.
- External API payloads are supplemental evidence only. Until response fields are mapped and versioned, they remain in `sc2replaystats.json` and the evidence report rather than changing coaching conclusions.
- `evidence.md` is the canonical human-readable audit report. `report.md` is retained as a compatibility index so existing consumers can find the separated outputs without receiving the verbose evidence by default.
- The repository package excludes `.SC2Replay` files, output/cache/virtual-environment directories, and local `.agents`/`.codex` metadata. Replay locations are configured by the consumer in `config.toml` or per command with `--replay-dir`; no personal replay path is part of the shareable source.
- `s2protocol` remains authoritative; sc2reader must not silently become the internal data model.
- Sc2ReplayStats pull integration is optional and read-only during analysis. The explicit upload command reads `SC2REPLAYSTATS_AUTH` (or the configured environment-variable name), sends each content hash once to `POST /replay`, and stores queue state under `.cache/sc2replaystats/upload-state.json`. Analysis never uploads implicitly; upload failures are retryable and replay files are never deleted or moved.
