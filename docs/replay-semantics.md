# Replay semantics

This document records the semantics used by the project. Future agents should update it when a new build is verified rather than rediscovering the same fields.

## Streams and event types

The parser uses Blizzard's `s2protocol` decoder for the MPQ streams. It selects the exact generated protocol module when its filename matches the replay base build. If no exact module exists, it may select the nearest lower generated module and records `protocol_selection` as `compatible-lower-protocol:<build>`; this path is retained only after the streams decode successfully. A replay newer than the bundled maximum or older than the bundled minimum fails clearly.

- `replay.header`: build/version and elapsed game loops.
- `replay.details`: map title/file name, participant names, races, teams, result fields, toon identity, and replay time fields.
- `replay.initData`: lobby/user metadata, optional scaled rating, and game description.
- `replay.attributes.events`: compact lobby attributes. Scope `16` is the global scope used for game speed and mode attributes when their IDs are known.
- `replay.tracker.events`: `SPlayerStatsEvent`, `SUnitBornEvent`, `SUnitDiedEvent`, `SUnitOwnerChangeEvent`, `SUnitTypeChangeEvent`, `SUpgradeEvent`, `SUnitInitEvent`, `SUnitDoneEvent`, `SUnitPositionsEvent`, and `SPlayerSetupEvent`.
- `replay.game.events`: command/ability events and other player-issued game events. The normalized event keeps the actor user ID, event type, ability link/index when present, target payload, and the original JSON-safe payload.
- `replay.message.events`: chat, ping, and loading messages. They are preserved but not treated as evidence of intent.

## Unit semantics

- `UnitBorn` means a unit entered the game in a finished state, such as a trained Marine or Zergling. It gives a unit tag index/recycle pair, type, control/upkeep owner IDs, and an approximate position.
- `UnitInit` means a unit began unfinished, commonly a building or warp-in. The unit tag is used to connect later `UnitDone`, type, ownership, position, and death events.
- `UnitDone` marks completion of an initialized unit. It does not create a new unit.
- `UnitTypeChange` changes the type on the same unit tag. This covers building morphs and mode changes; it is not automatically a new unit.
- `UnitOwnerChange` changes control/upkeep ownership. The derivation layer updates the current owner while preserving the event evidence.
- `UnitDied` records the tag, killer player/unit when available, and death position. A death can also represent removal or morph/merge behavior; the report calls it a tracked loss, not an unqualified combat kill.
- Unit tags are normalized as `(unit_tag_index << 18) | unit_tag_recycle`.
- `UnitPositions` is sparse: it reports positions for units damaged in the previous interval, limited by the game's tracker behavior. The project maps an index to the latest known tag only when possible and never interpolates movement.

## Player-stat semantics

`SPlayerStatsEvent` is normalized into snapshots. It contains current minerals/gas, collection rates, active worker count, current/in-progress resource values, lost/killed resource values, supply used/available, and active-force values. Food values are divided by 4096, matching sc2reader's documented interpretation of the score fields.

For Zerg, a raw Drone death event is not automatically a killed worker. Drone events are decomposed into worker-consuming Zerg structure starts (`Hatchery`, `Extractor`, `SpawningPool`, tech structures, `Spire`, and crawler structures) plus remaining worker-loss events. The exact builder-to-structure tag relationship is unavailable, so this is an explicitly labeled estimate. Protoss Probe and Terran SCV worker events are not reduced by this construction-consumption rule.

Player-stat values are snapshots, not continuous telemetry. A change between two snapshots cannot assign a precise frame or cause to every worker, resource, or army change. APM is not available in the decoded streams currently used and is marked unavailable. Lobby scaled rating is retained as `mmr` with a source note; it is not asserted to be a post-game MMR value.

## Resource float, production, and purchase bounds

The derivation layer groups snapshots into candidate float episodes when minerals are at least 800 or gas is at least 500. The episode ends at the first later snapshot below both thresholds. “Meaningful” means sustained for at least 160 loops, at least 1,200 minerals, at least 800 gas, or supported by repeated state evidence. The episode keeps the qualifying snapshot IDs and the nearest composition snapshot so every report conclusion can be audited.

`available_production_capacity` is an observed count of known unit-producing structures: Zerg Hatchery/Lair/Hive, Terran Barracks/Factory/Starport, and Protoss Gateway/WarpGate/Robotics Facility/Stargate. Zerg tech structures such as Spawning Pool and Roach Warren are not counted as production capacity. This is infrastructure capacity, not proof that a queue was empty. Larva is reported only when at least one Larva was observed for that player in the normalized tracker stream; otherwise it is `null` and `insufficient_larva` is not emitted.

The current bounded purchase illustrations cover Zerg Roaches and Zerglings. They report resource-only bounds and an immediate upper bound constrained by gas, supply room, observed larva, required tech, and known structures. They do not simulate queue duration, injects, morphs, or hidden reservations. A large resource-only number must never be presented as an immediately purchasable army when one of those constraints is tighter.

`base_count_at_peak` counts completed town halls by the episode peak. Macro benchmark prose uses that time-local base count; later expansions are reported as a transition and do not retroactively turn an earlier two-base spending window into a four-base benchmark.

Float constraint labels are candidates: `supply_blocked`, `insufficient_production`, `insufficient_larva`, `production_idle`, `tech_transition_bank`, `overdroning`, `attention_diversion`, `gas_imbalance`, `mineral_imbalance`, `intentional_reserve`, and `unknown`. Combat overlap alone never proves attention diversion. A supply block is treated as relevant to the peak when it overlaps the peak snapshot or occurs within the nearby conversion window; a late cap is not automatically claimed to explain an entire earlier bank.

## Ownership and identity

Participant order in `m_playerList` is normalized to player IDs starting at 1. Tracker owner/upkeep player IDs are used for unit ownership. Game-event `_userid` is retained separately because it is a user identity, not necessarily the same field as a tracker player ID. Reports do not silently equate those IDs without an explicit normalized mapping.

## Time conversion

Game loops are the canonical stored timestamp. The displayed SC2 game clock is:

```text
game_seconds = game_loops / 16
```

The official speed factors are:

```text
Slower = 0.6, Slow = 0.8, Normal = 1.0, Fast = 1.2, Faster = 1.4
real_seconds = game_loops / (16 * speed_factor)
```

`Fastest` is accepted as a human input alias for `Faster` but is never written as replay metadata. Reports expose only real elapsed timestamps; game loops remain internal evidence coordinates. The code for these rules lives only in `sc2_replay_reviewer/time.py`.

## Engagement detection

Engagements are candidate local fights, not full combat simulations. The algorithm:

1. Select tracked unit deaths with a usable position and a known owner.
2. Sort by game loop.
3. Cluster adjacent deaths only when the gap is at most 128 loops (8 displayed game seconds) and the death is within 32 map units of an existing death or the cluster centroid.
4. Keep only clusters with at least two participants and two deaths.
5. Aggregate losses by owner, including workers, structures, army units, known fallback resource values, unknown units, and evidence IDs.

Opposite-map deaths therefore do not become one fight just because they happened in the same minute. A missing position prevents an event from supporting a spatial engagement. Reinforcement waves are approximate: they use sparse unit-position observations near the engagement after its start and explicitly do not claim movement path, camera attention, or intent.

## Army value and losses

For each player-stat snapshot, army value prefers `minerals_used_active_forces + vespene_used_active_forces`, because it is the replay's aggregate active-force score. If that score is absent/zero, derivation falls back to summing known common-unit mineral+gas costs from the transparent table in `derive.py`, while counting unknown unit types separately. The fallback is not a full patch-specific game-data model.

Unit losses are aggregated from `UnitDied` events using the owner's current lifecycle state. Known unit costs are summed by mineral and gas. Player-stat total resources lost remain preserved at every snapshot; they are not incorrectly redistributed to individual engagements. Local engagement losses therefore use event-level unit attribution and show unknown buckets when costs or owners are unavailable.

## Ambiguities and unavailable information

- Tracker death can mean removal/morph/merge as well as combat death.
- Position snapshots are sparse and damage-biased; they are not a full unit movement log.
- A worker-count plateau does not prove a worker-production pause. A high resource bank does not prove a macro error without strategic context.
- Commands show issued protocol events, not attention, intention, control-group contents, or why an order was chosen.
- Replay files do not provide complete vision history or full combat simulation state to this project.
- Result encoding and legacy attribute availability can vary by build; raw values remain in normalized metadata/event payloads when a friendly label is uncertain.
