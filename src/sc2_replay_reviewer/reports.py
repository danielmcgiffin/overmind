"""Markdown report and short coaching review renderers."""

from __future__ import annotations

from typing import Any

from .config import AppConfig
from .time import format_real_time


def _name(extraction: dict[str, Any], player_id: int | None) -> str:
    for player in extraction.get("players", []):
        if player.get("player_id") == player_id:
            return player.get("name") or f"Player {player_id}"
    return f"Player {player_id}" if player_id is not None else "Unknown"


def _player(extraction: dict[str, Any], player_id: int) -> dict[str, Any]:
    return next((item for item in extraction.get("players", []) if item.get("player_id") == player_id), {})


def _evidence(items: list[str] | None) -> str:
    refs = [str(item) for item in (items or []) if item]
    return f" Evidence: `{', '.join(refs)}`." if refs else " Evidence: unavailable."


def _state_line(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return "No nearby player-stat snapshot was available."
    return (
        f"workers {snapshot.get('workers_active_count', 'n/a')}, supply "
        f"{snapshot.get('food_used', 'n/a')}/{snapshot.get('food_made', 'n/a')}, "
        f"active-force value {snapshot.get('minerals_used_active_forces', 0) + snapshot.get('vespene_used_active_forces', 0)}"
    )


def _macro_snapshot_rows(snapshots: list[dict[str, Any]], speed: str) -> list[dict[str, Any]]:
    """Choose a stable, human-sized set of snapshots for coaching benchmarks."""
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for target_loop in (2880, 4800, 6720, 8640, 9600, 10560, 11520, 12480, 13000):
        candidates = [item for item in snapshots if abs(item.get("game_loop", 0) - target_loop) <= 240]
        if not candidates:
            continue
        snapshot = min(candidates, key=lambda item: abs(item.get("game_loop", 0) - target_loop))
        if snapshot.get("game_loop") in seen:
            continue
        seen.add(snapshot["game_loop"])
        rows.append(snapshot)
    return rows


def _bank(snapshot: dict[str, Any]) -> str:
    minerals = snapshot.get("minerals_current")
    gas = snapshot.get("vespene_current")
    return f"{minerals if minerals is not None else 'n/a'}m / {gas if gas is not None else 'n/a'}g"


def _macro_guidance(derivation: dict[str, Any], player_id: int, speed: str) -> list[str]:
    snapshots = [item for item in derivation.get("player_snapshots", []) if item.get("player_id") == player_id]
    if not snapshots:
        return ["No player-stat snapshots were available, so macro benchmarks cannot be established from this replay."]
    peak = max(snapshots, key=lambda item: item.get("workers_active_count") or 0)
    expansions = [item for item in derivation.get("timing", {}).get("expansions", []) if item.get("player_id") == player_id]
    town_halls = len(expansions) + 1
    worker_path = []
    for snapshot in _macro_snapshot_rows(snapshots, speed):
        worker_path.append(f"{snapshot.get('workers_active_count', 'n/a')} at {format_real_time(snapshot['game_loop'], speed)} real")
    worker_path_text = ", ".join(worker_path)
    lines = [
        f"- **Worker benchmark:** the reviewed player reached {peak.get('workers_active_count', 'n/a')} active workers by {format_real_time(peak['game_loop'], speed)} real and finished near {snapshots[-1].get('workers_active_count', 'n/a')}. With {town_halls} tracked town halls, use the observed path as the benchmark rather than importing a generic 65-worker target.",
    ]
    blocks = [item for item in derivation.get("economy", {}).get("candidate_supply_blocks", []) if item.get("player_id") == player_id]
    if blocks:
        times = ", ".join(f"{format_real_time(item['start_loop'], speed)} real" for item in blocks)
        lines.append(f"- **Supply benchmark:** candidate cap pressure appeared at {times}. Queue the next Overlord before those caps—roughly 15–20 real seconds ahead—then verify the actual queue in the replay because stats alone do not prove a production pause.")
    floats = [item for item in derivation.get("economy", {}).get("candidate_resource_floats", []) if item.get("player_id") == player_id]
    large_floats = [item for item in floats if (item.get("minerals") or 0) >= 1000 or (item.get("vespene") or 0) >= 500]
    if large_floats:
        worst = max(large_floats, key=lambda item: (item.get("minerals") or 0) + (item.get("vespene") or 0))
        lines.append(f"- **Spend benchmark:** the bank reached {worst.get('minerals', 'n/a')} minerals / {worst.get('vespene', 'n/a')} gas at {format_real_time(worst['game_loop'], speed)} real. With about {peak.get('workers_active_count', 'n/a')} workers and {town_halls} tracked town halls, a bank of 1,000+ minerals is the moment to inject, add production, start tech/upgrades, or queue the next army wave—not a reason to make more workers automatically.")
    if worker_path_text:
        lines.append(f"- **Personal checkpoint path:** {worker_path_text}. These are this replay's benchmarks, not universal build-order laws.")
    lines.append("- **After a successful fight:** immediately convert the advantage into a new wave, tech, or map-control action while keeping injects and supply ahead. A favorable engagement is wasted if the bank later rises while the army count stalls.")
    return lines


def render_evidence(extraction: dict[str, Any], derivation: dict[str, Any], engagements: list[dict[str, Any]], diagnosis: dict[str, Any], timeline: list[dict[str, Any]], player_id: int, config: AppConfig) -> str:
    metadata = extraction["metadata"]
    player = _player(extraction, player_id)
    decisive = diagnosis.get("decisive_candidate", {})
    turning = diagnosis.get("turning_point_candidate", {})
    speed = metadata["game_speed"]
    decisive_loop = decisive.get("game_loop")
    lines = [
        "# Replay Review Report",
        "",
        "## 1. Match summary",
        "",
        f"- Player reviewed: **{player.get('name', player_id)}** ({player.get('race') or 'race unavailable'}), result: {player.get('result') or 'unavailable'}.",
        f"- Map: {metadata.get('map') or 'unavailable'}; game mode: {metadata.get('game_mode') or metadata.get('teams') or 'unavailable'}; speed: **{speed}**.",
        f"- Duration: {format_real_time(metadata.get('duration_loops', 0), speed)} real. All report timestamps use real elapsed time only; game loops remain internal evidence coordinates.",
        f"- Replay hash: `{extraction['replay_hash']}`; parser: `{extraction['parser']['version']}`.",
        "",
        "## 2. Executive diagnosis",
        "",
    ]
    if decisive_loop is not None:
        if player.get("result") == "Win":
            lines.append(f"The game was a win, but the largest avoidable danger was **{decisive.get('engagement_id')} at {format_real_time(decisive_loop, speed)} real**. The strongest supported coaching diagnosis is a tactical commitment problem; later reinforcement continuation is treated as a consequence unless earlier evidence shows otherwise.")
        else:
            lines.append(f"The candidate turning point was **{decisive.get('engagement_id')} at {format_real_time(decisive_loop, speed)} real**. The strongest supported diagnosis is a tactical commitment problem, with later state loss and any reinforcement continuation treated as consequences unless earlier evidence shows otherwise.")
    elif turning.get("game_loop") is not None:
        assessment = turning.get("assessment") or {}
        turn = turning.get("engagement_id")
        lines.append(f"The replay does not support calling the central combat sequence a tactical loss. The material favorable turn was **{turn} at {format_real_time(turning['game_loop'], speed)} real**. {assessment.get('summary', '')}")
    else:
        lines.append("The replay did not provide enough spatially supported death data to identify a candidate decisive engagement. The report below separates what is known from what remains unavailable.")
    lines += ["", "## 3. Decisive turning point", ""]
    if decisive_loop is not None or turning.get("game_loop") is not None:
        selected_id = decisive.get("engagement_id") if decisive_loop is not None else turning.get("engagement_id")
        target = next((item for item in engagements if item.get("engagement_id") == selected_id), None)
        if target:
            own = target.get("losses_by_player", {}).get(str(player_id), {})
            enemy_units = sum(value.get("units", 0) for pid, value in target.get("losses_by_player", {}).items() if int(pid) != player_id)
            kills = target.get("kills_by_player", {}).get(str(player_id), {})
            own_types = target.get("loss_types_by_player", {}).get(str(player_id), {})
            assessment = (turning.get("assessment") or {}) if decisive_loop is None else {}
            label = assessment.get("label", "candidate_negative")
            lines.append(f"- **{target['engagement_id']}**: {format_real_time(target['start_loop'], speed)} to {format_real_time(target['end_loop'], speed)} real near `{target.get('centroid')}`; {own.get('units', 0)} of the reviewed player's units were lost versus {enemy_units} opposing units in the cluster. Trade classification: **{label}**.{_evidence(target.get('evidence'))}")
            if own_types:
                lines.append(f"- Reviewed-player losses by type: {', '.join(f'{count} {unit_type}' for unit_type, count in sorted(own_types.items()))}.")
            if kills:
                lines.append(f"- Killer-attributed opposing losses in this cluster: {', '.join(f'{count} {unit_type}' for unit_type, count in sorted(kills.items()))}. This is the evidence that prevents the reviewed player's local loss count from being mislabeled as an automatic tactical failure.")
            lines.append(f"- Pre-fight/post-fight state: {_state_line(target.get('state', {}).get('pre', {}).get(str(player_id)))} → {_state_line(target.get('state', {}).get('post', {}).get(str(player_id)))}.")
    else:
        lines.append("- No engagement met the minimum requirement of at least two players, at least two deaths, and spatially compatible positions.")
    lines += ["", "## 4. Timeline of meaningful events", ""]
    for row in timeline:
        lines.append(f"- **{row['real_time']} real — {row['event_kind']}**: {row['factual_statement']}" + (f" Evidence: `{row['evidence_refs']}`." if row["evidence_refs"] else ""))
    lines += ["", "## 5. Economy", ""]
    snapshots = [item for item in derivation.get("player_snapshots", []) if item.get("player_id") == player_id]
    if snapshots:
        first, last = snapshots[0], snapshots[-1]
        lines.append(f"- Tracked worker count moved from {first.get('workers_active_count', 'n/a')} at {format_real_time(first['game_loop'], speed)} real to {last.get('workers_active_count', 'n/a')} at {format_real_time(last['game_loop'], speed)} real.")
        lines.append(f"- Final available resources in the last snapshot: {last.get('minerals_current', 'n/a')} minerals and {last.get('vespene_current', 'n/a')} gas; collection rates were {last.get('minerals_collection_rate', 'n/a')} and {last.get('vespene_collection_rate', 'n/a')}.")
    else:
        lines.append("- Player-stat snapshots were unavailable; worker and resource trends cannot be audited from this replay.")
    worker_deaths = [item for item in derivation.get("losses", {}).get("worker_deaths", []) if item.get("owner_id") == player_id]
    if worker_deaths:
        worker_summary = derivation.get("losses", {}).get("worker_loss_summary_by_player", {}).get(str(player_id), {})
        lines.append(f"- {worker_summary.get('raw_worker_death_events', len(worker_deaths))} raw worker-death events were tracked for {_name(extraction, player_id)}; the heuristic decomposition estimates {worker_summary.get('estimated_construction_consumed', 0)} construction-consumed workers and {worker_summary.get('estimated_worker_losses', len(worker_deaths))} actual worker-loss events. Exact builder identity is unavailable.")
    opponent_disruptions = [item for item in derivation.get("economy", {}).get("resource_collection_disruptions", []) if item.get("player_id") != player_id]
    for disruption in opponent_disruptions:
        lines.append(f"- Candidate economic disruption to {_name(extraction, disruption.get('player_id'))}: mineral collection rate fell from {disruption.get('minerals_collection_rate_before')} to {disruption.get('minerals_collection_rate_after')} between {format_real_time(disruption['start_loop'], speed)} and {format_real_time(disruption['end_loop'], speed)} real. This supports a worker pull or mining interruption, but does not prove the exact cause.{_evidence(disruption.get('evidence'))}")
    for flag in derivation.get("economy", {}).get("candidate_supply_blocks", []):
        if flag.get("player_id") == player_id:
            lines.append(f"- Candidate supply pressure at {format_real_time(flag['start_loop'], speed)} real: {flag['supply_used']} used / {flag['supply_available']} available across the next stats interval. This is not automatically an error.{_evidence(flag.get('evidence'))}")
    float_episodes = [item for item in derivation.get("economy", {}).get("float_episodes", []) if item.get("player_id") == player_id]
    lines += ["", "### Meaningful resource-float episodes", ""]
    if float_episodes:
        for episode in float_episodes:
            purchase = episode.get("purchasing_power") or {}
            purchase_text = "; ".join(
                f"{unit_type}: resource bound {details.get('resource_bound')}, immediate upper bound {details.get('immediate_upper_bound')}, supply bound {details.get('supply_bound')}, larva bound {details.get('larva_bound')}, tech {details.get('tech_available')}"
                for unit_type, details in sorted(purchase.items())
            ) or "no bounded unit equivalent"
            lines.append(
                f"- {format_real_time(episode['start_loop'], speed)}–{format_real_time(episode['end_loop'], speed)} real ({format_real_time(episode.get('duration_loops', 0), speed)}): peak {episode.get('peak_minerals')} minerals / {episode.get('peak_gas')} gas at {format_real_time(episode['peak_loop'], speed)}; workers {episode.get('worker_count_at_start', 'n/a')}→{episode.get('worker_count_at_peak', 'n/a')}, bases {episode.get('base_count_at_peak', 'n/a')}, supply {_supply_text(episode.get('supply_at_peak'))}, tracked production capacity {episode.get('available_production_capacity', 'n/a')}, tracked larva {episode.get('available_larva', 'n/a')}; constraints {', '.join(episode.get('constraints') or ['unknown'])}; active fighting {episode.get('actively_fighting')}; bank spent after fighting {episode.get('bank_spent_after_active_fighting')}."
            )
            lines.append(f"  - Purchasing power: {purchase_text}. Upgrades already completed: {', '.join(episode.get('completed_upgrades_at_peak') or ['none decoded'])}. {_evidence(episode.get('evidence'))}")
    else:
        lines.append("- No meaningful float episode was detected; isolated threshold snapshots remain in structured economy facts.")
    lines.append("")
    lines.append("### Macro benchmarks and next-game targets")
    lines.append("")
    lines.append("All timestamps below are real elapsed time.")
    macro_rows = _macro_snapshot_rows(snapshots, speed)
    if macro_rows:
        lines.append("| Time | Workers | Supply | Bank | Active-force value |")
        lines.append("|---|---:|---:|---:|---:|")
        for snapshot in macro_rows:
            active_value = (snapshot.get("minerals_used_active_forces") or 0) + (snapshot.get("vespene_used_active_forces") or 0)
            lines.append(f"| {format_real_time(snapshot['game_loop'], speed)} real | {snapshot.get('workers_active_count', 'n/a')} | {snapshot.get('food_used', 'n/a')}/{snapshot.get('food_made', 'n/a')} | {_bank(snapshot)} | {active_value} |")
    lines.extend(_macro_guidance(derivation, player_id, speed))
    lines += ["", "## 6. Production and technology", ""]
    structures = [item for item in derivation.get("timing", {}).get("completed_structures", []) if item.get("player_id") == player_id]
    if structures:
        lines.append(f"- {len(structures)} structure completions were normalized; production capacity is approximate because the replay does not expose complete queues or worker assignment.")
        for expansion in derivation.get("timing", {}).get("expansions", []):
            if expansion.get("player_id") == player_id:
                lines.append(f"- Expansion #{expansion.get('expansion_number')} ({expansion.get('unit_type')}) completed at {format_real_time(expansion['game_loop'], speed)} real.{_evidence(expansion.get('evidence'))}")
    else:
        lines.append("- No completed structures were decoded for this player.")
    upgrades = [item for item in derivation.get("timing", {}).get("upgrades", []) if item.get("player_id") == player_id]
    if upgrades:
        for upgrade in upgrades:
            lines.append(f"- Upgrade completed: {upgrade.get('upgrade')} at {format_real_time(upgrade['game_loop'], speed)} real.{_evidence(upgrade.get('evidence'))}")
    else:
        lines.append("- No upgrade completion events were decoded for this player.")
    lines += ["", "## 7. Army composition", ""]
    compositions = [item for item in derivation.get("composition_snapshots", []) if item.get("player_id") == player_id]
    if compositions:
        for item in compositions[-3:]:
            lines.append(f"- {format_real_time(item['game_loop'], speed)} real: {item.get('composition') or 'no known army units'}; army value {item.get('army_value')} ({item.get('army_value_source')}).")
    else:
        lines.append("- Army composition snapshots were unavailable.")
    lines += ["", "## 8. Engagement analysis", ""]
    if engagements:
        for engagement in engagements:
            own = engagement.get("losses_by_player", {}).get(str(player_id), {})
            kills = engagement.get("kills_by_player", {}).get(str(player_id), {})
            kill_text = f" Killer-attributed kills: {', '.join(f'{count} {unit_type}' for unit_type, count in sorted(kills.items()))}." if kills else ""
            lines.append(f"- {engagement['engagement_id']} at {format_real_time(engagement['start_loop'], speed)} real: {engagement['death_count']} deaths, local losses for {_name(extraction, player_id)} = {own.get('units', 0)}; cluster position = {engagement.get('centroid')}. Reinforcement observations: {len(engagement.get('reinforcement_waves', []))}.{kill_text}{_evidence(engagement.get('evidence'))}")
    else:
        lines.append("- No spatially supported engagements detected.")
    lines += ["", "## 9. Opponent-created damage", ""]
    opponent_worker_deaths = [item for item in worker_deaths if item.get("killer_player_id") is not None and item.get("killer_player_id") != player_id]
    if opponent_worker_deaths:
        lines.append(f"- Opponent-attributed worker losses: {len(opponent_worker_deaths)}, beginning at {format_real_time(min(item['game_loop'] for item in opponent_worker_deaths), speed)} real.{_evidence([item.get('evidence_id') for item in opponent_worker_deaths])}")
    else:
        lines.append("- No opponent-attributed worker damage was available before the end of the decoded stream.")
    lines += ["", "## 10. Self-inflicted damage", ""]
    self_damage = [item for item in diagnosis.get("inferences", []) if item.get("category") in {"tactical", "reinforcement", "economy"}]
    if self_damage:
        for item in self_damage:
            lines.append(f"- **{item['category']} inference** at {item.get('real_time', format_real_time(item.get('game_loop') or 0, speed))} real: {item['statement']}{_evidence(item.get('evidence'))}")
    else:
        lines.append("- No self-inflicted causal inference cleared the evidence threshold.")
    lines += ["", "## 11. What was still recoverable", ""]
    if decisive_loop is not None:
        lines.append(f"- Until the candidate engagement at {format_real_time(decisive_loop, speed)} real, the replay should be treated as potentially recoverable unless an earlier unobserved state existed. The data supports a turning-point hypothesis, not certainty about player intent.")
    elif turning.get("game_loop") is not None:
        lines.append(f"- The reviewed player was still in a recoverable and ultimately winning state through the favorable combat transition at {format_real_time(turning['game_loop'], speed)} real. The main remaining risk was failing to convert that advantage into sustained production and map control.")
    else:
        lines.append("- No reliable turning point was available, so recoverability cannot be separated from missing evidence.")
    lines += ["", "## 12. When the game became effectively lost", ""]
    if diagnosis.get("effectively_lost_loop") is not None:
        lines.append(f"- Heuristic effective-loss point: {format_real_time(diagnosis['effectively_lost_loop'], speed)} real. This means the tracked army value was below half the strongest opponent's value in the available post-fight snapshot; it is not a replay-native result.")
    else:
        lines.append("- Not established. The report will not call the game lost merely because an early mistake occurred.")
    lines += ["", "## 13. Two highest-leverage corrections", ""]
    corrections = []
    if decisive_loop is not None:
        corrections.append(f"At {format_real_time(decisive_loop, speed)} real, set a disengagement trigger for the first materially losing local fight; do not feed the next wave into the same position without a documented state improvement.")
    if opponent_worker_deaths:
        corrections.append(f"After the first tracked worker harassment at {format_real_time(min(item['game_loop'] for item in opponent_worker_deaths), speed)} real, protect the recovery plan: keep worker production and the committed army plan explicit instead of allowing the response to become an unmeasured all-in.")
    if not corrections:
        macro_corrections = _macro_guidance(derivation, player_id, speed)
        corrections.extend(macro_corrections[1:3] if len(macro_corrections) >= 3 else macro_corrections[:2])
    for correction in corrections[:2]:
        lines.append(correction if correction.startswith("- ") else f"- {correction}")
    lines += ["", "## 14. Evidence appendix", ""]
    lines.append("Facts are normalized observations from replay events or snapshots. Inferences are diagnostic conclusions that cite those facts. `replay.json` preserves the normalized event payloads for audit.")
    lines.append("")
    for item in diagnosis.get("facts", []):
        lines.append(f"- **FACT `{item['fact_id']}`** {item['statement']}{_evidence(item.get('evidence'))}")
    for item in diagnosis.get("inferences", []):
        lines.append(f"- **INFERENCE `{item['inference_id']}` ({item['confidence']})** {item['statement']}{_evidence(item.get('evidence'))}")
    lines += [
        "",
        "### Evidence methodology and limitations",
        "",
        f"- Normalized stream counts: {len(extraction.get('tracker_events', []))} tracker events, {len(extraction.get('game_events', []))} game events, and {len(extraction.get('message_events', []))} messages. The parser is `{extraction.get('parser', {}).get('name', 'unavailable')}` `{extraction.get('parser', {}).get('version', 'unavailable')}`.",
        "- Engagements are clustered using temporal proximity plus compatible sparse map positions. Deaths on opposite sides of the map are not merged merely because they occur in the same minute.",
        "- Unit positions are approximate tracker observations. The project does not interpolate movement, infer camera attention, invent intent, or simulate missing combat state.",
        "- Worker-death adjustments, army values, supply pressure, resource floats, and income disruptions are derived facts or heuristics and retain their source snapshot/event references.",
        "- Confidence belongs to inferences, not raw facts. The structured `findings.json` preserves each fact, inference, causal-chain entry, confidence label, and evidence reference.",
        "- All displayed timestamps use real elapsed time calculated by the dedicated time module from canonical replay loops and the replay speed factor. Raw loops remain available in structured evidence.",
    ]
    if extraction.get("warnings"):
        lines += ["", "Parser warnings:"]
        lines.extend(f"- {warning}" for warning in extraction["warnings"])
    return "\n".join(lines) + "\n"


def _supply_provider(race: str | None) -> str:
    return {"Zerg": "Overlord", "Protoss": "Pylon", "Terran": "Supply Depot"}.get(race or "", "supply provider")


def _macro_benchmark_reality(derivation: dict[str, Any], player_id: int, extraction: dict[str, Any], speed: str) -> str:
    snapshots = [item for item in derivation.get("player_snapshots", []) if item.get("player_id") == player_id]
    if not snapshots:
        return "**Macro benchmark/reality:** player-stat snapshots were unavailable, so worker and spending reality cannot be compared from this replay."
    expansions = [item for item in derivation.get("timing", {}).get("expansions", []) if item.get("player_id") == player_id]
    town_halls = len(expansions) + 1
    benchmark_workers = town_halls * 15
    peak = max(snapshots, key=lambda item: item.get("workers_active_count") or 0)
    latest = snapshots[-1]
    latest_bank = f"{latest.get('minerals_current', 'n/a')} minerals / {latest.get('vespene_current', 'n/a')} gas"
    return (
        f"**Macro benchmark/reality:** with {town_halls} tracked town halls, use roughly {benchmark_workers} workers as this replay's spending checkpoint. "
        f"Reality was {peak.get('workers_active_count', 'n/a')} workers by {format_real_time(peak['game_loop'], speed)} and {latest.get('workers_active_count', 'n/a')} at {format_real_time(latest['game_loop'], speed)}, with a final bank of {latest_bank}; "
        f"the economy was {'sufficient and spending was the bottleneck' if (latest.get('workers_active_count') or 0) >= benchmark_workers else 'below the replay benchmark and still needed worker growth'}."
    )


def _float_episode(derivation: dict[str, Any], player_id: int) -> dict[str, Any] | None:
    episodes = [
        item for item in derivation.get("economy", {}).get("float_episodes", [])
        if item.get("player_id") == player_id and item.get("meaningful")
    ]
    return max(episodes, key=lambda item: ((item.get("peak_minerals") or 0) + (item.get("peak_gas") or 0), item.get("duration_loops") or 0), default=None)


def _supply_text(supply: dict[str, Any] | None) -> str:
    supply = supply or {}
    used, available = supply.get("used"), supply.get("available")
    if used is None or available is None:
        return "supply unavailable"
    room = max(0, float(available) - float(used))
    room_text = str(int(room)) if room.is_integer() else f"{room:g}"
    return f"{used}/{available} used, {room_text} free"


def _float_constraint_text(episode: dict[str, Any]) -> str:
    labels = episode.get("constraints") or ["unknown"]
    explanations = {
        "supply_blocked": "candidate supply pressure overlapped the episode",
        "insufficient_production": "no tracked production structure was available at the peak",
        "insufficient_larva": "the tracked larva pool was empty at the peak",
        "production_idle": "candidate unused production capacity existed, although queue state is unavailable",
        "tech_transition_bank": "resources were visibly committed to technology",
        "overdroning": "the bank coexisted with worker growth beyond the spending checkpoint",
        "attention_diversion": "attention diversion is not established by this replay",
        "gas_imbalance": "the mineral bank was large while gas was comparatively scarce",
        "mineral_imbalance": "gas accumulated while minerals were comparatively scarce",
        "intentional_reserve": "a named reserve could be supported by the available evidence",
        "unknown": "the replay cannot expose a single binding spending constraint",
    }
    supply = episode.get("supply_at_peak") or {}
    if "supply_blocked" in labels and supply.get("used") is not None and supply.get("available") is not None:
        if float(supply["available"]) - float(supply["used"]) > 2:
            explanations["supply_blocked"] = "late candidate supply pressure appeared near the conversion window, but did not explain the whole earlier bank"
    return "; ".join(f"{label}: {explanations.get(label, 'constraint classification unavailable')}" for label in labels)


def _purchase_sentence(episode: dict[str, Any], player: dict[str, Any]) -> str:
    purchases = episode.get("purchasing_power") or {}
    if not purchases:
        return "No bounded unit-equivalent purchase was available from the decoded race and state data."
    phrases = []
    plural = {"Roach": "Roaches", "Zergling": "Zerglings"}
    for unit_type in ("Roach", "Zergling"):
        purchase = purchases.get(unit_type)
        if not purchase:
            continue
        resource_bound = purchase.get("resource_bound")
        immediate = purchase.get("immediate_upper_bound")
        if resource_bound is None:
            continue
        if immediate is None:
            phrases.append(f"resources alone represented about {resource_bound} {plural[unit_type]}, but the immediate bound is unknown")
        elif immediate == 0 and purchase.get("supply_bound") == 0:
            phrases.append(f"resources alone represented about {resource_bound} {plural[unit_type]}, but the peak had no supply room")
        else:
            phrases.append(f"the bounded immediate upper limit was {immediate} {plural[unit_type]} (resource-only bound {resource_bound})")
    if not phrases:
        return "The bank could not be converted into a bounded unit equivalent without inventing missing tech or queue state."
    return " and ".join(phrases) + "."


def render_review(extraction: dict[str, Any], derivation: dict[str, Any], engagements: list[dict[str, Any]], diagnosis: dict[str, Any], player_id: int, config: AppConfig) -> str:
    """Render the compressed, spending-first player-facing review."""
    speed = extraction["metadata"]["game_speed"]
    player = _player(extraction, player_id)
    player_name = _name(extraction, player_id)
    macro_benchmark = _macro_benchmark_reality(derivation, player_id, extraction, speed)
    episode = _float_episode(derivation, player_id)
    blocks = [item for item in derivation.get("economy", {}).get("candidate_supply_blocks", []) if item.get("player_id") == player_id]
    lines = ["# Coaching Review", "", "Timestamps use real elapsed time.", ""]

    lines += ["## Spending verdict", ""]
    if episode:
        worker_count = episode.get("worker_count_at_peak")
        starting_workers = episode.get("worker_count_at_start", worker_count)
        base_count = episode.get("base_count_at_peak")
        benchmark = base_count * 15 if base_count else None
        if worker_count is not None and benchmark is not None and worker_count >= benchmark:
            timing_phrase = "after" if starting_workers >= benchmark else "before, then remained present after"
            lines.append(f"This was not an income problem for {player_name}. The bank became meaningful {timing_phrase} the replay's {benchmark}-worker checkpoint, so the recurring lesson is resource conversion: turn income into supply, production, and army before adding more economy.")
        else:
            lines.append(f"{player_name} had a meaningful spending problem, but the bank appeared before a clean worker-saturation checkpoint. The next correction is to stabilize production and supply while growing workers toward the replay's base count, instead of letting the bank become idle resources.")
    else:
        lines.append(f"No sustained meaningful float episode was decoded for {player_name}; this replay does not support blaming a large unspent bank. The review should focus on the next highest-ranked constraint in the evidence layer.")
    lines.append(macro_benchmark)

    lines += ["", "## Float timeline", ""]
    if episode:
        lines.append(
            f"The main episode ran from {format_real_time(episode['start_loop'], speed)} to {format_real_time(episode['end_loop'], speed)} real ({format_real_time(episode.get('duration_loops', 0), speed)}), peaking at {episode.get('peak_minerals')} minerals / {episode.get('peak_gas')} gas at {format_real_time(episode['peak_loop'], speed)}. "
            f"At the peak: {episode.get('worker_count_at_start', 'n/a')}→{episode.get('worker_count_at_peak', 'n/a')} workers, {episode.get('base_count_at_peak', 'n/a')} bases, {_supply_text(episode.get('supply_at_peak'))}, {episode.get('available_production_capacity', 'n/a')} tracked production capacity, and {episode.get('available_larva', 'n/a')} tracked larva."
        )
    else:
        lines.append("No meaningful episode met the analyzer's sustained-or-large threshold; isolated high-bank snapshots remain in evidence.md.")

    lines += ["", "## Why the bank accumulated", ""]
    if episode:
        cause = _float_constraint_text(episode)
        lines.append(f"Primary constraint: **{episode.get('primary_constraint', 'unknown')}**. {cause}. This is a candidate diagnosis: complete queue state and player attention are not replay-visible.")
        if episode.get("actively_fighting"):
            spent = "did" if episode.get("bank_spent_after_active_fighting") else "did not"
            post_fight = "the next snapshot shows a substantial bank conversion" if spent == "did" else "no later snapshot proves a substantial bank conversion"
            lines.append(f"The episode overlaps {episode.get('active_fighting_event_count')} tracked deaths; {post_fight} after that fighting window.")
    elif blocks:
        lines.append("Supply pressure was detected, but no sustained bank episode was large enough to explain the result by itself.")
    else:
        lines.append("The replay does not expose enough sustained resource or queue evidence to classify a spending constraint.")

    lines += ["", "## What the bank should have become", ""]
    if episode:
        lines.append(f"{_purchase_sentence(episode, player)} The actionable conversion was a named purchase sequence, not a generic command to macro: clear supply first when capped, then spend the bank through the observed tech/larva/production limits."
        )
    else:
        lines.append("Use the next verified bank threshold as the conversion point: spend on the next production, tech, or army purchase before taking another worker or moving the army.")

    lines += ["", "## Next-game trigger", ""]
    if episode and episode.get("primary_constraint") == "supply_blocked":
        trigger = f"After reaching the replay's worker checkpoint, when the bank hits 800 minerals, queue the next {_supply_provider(player.get('race'))} if fewer than two supply slots remain; otherwise spend the bank before adding another worker."
    elif episode:
        trigger = "When the bank reaches 800 minerals after the replay's worker checkpoint, add or use production immediately; after a fight ends, spend before watching the army move."
    else:
        trigger = "At 800 minerals, name the purchase you are saving for; otherwise spend it immediately on production, tech, or the next army wave."
    lines.append(f"1. {trigger}")
    return "\n".join(lines) + "\n"


def render_report(extraction: dict[str, Any], derivation: dict[str, Any], engagements: list[dict[str, Any]], diagnosis: dict[str, Any], timeline: list[dict[str, Any]], player_id: int, config: AppConfig) -> str:
    """Keep the old filename useful without duplicating the evidence report."""
    return "\n".join([
        "# Replay analysis outputs",
        "",
        "This bundle separates player coaching from audit evidence. Timestamps use real elapsed time.",
        "",
        "- [Concise coaching review](review.md)",
        "- [Detailed evidence report](evidence.md)",
        "- [Normalized extraction](replay.json)",
        "- [Timeline CSV](timeline.csv)",
        "- [Engagements JSON](engagements.json)",
        "- [Findings JSON](findings.json)",
        "",
    ])
