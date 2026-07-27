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


def _passes_relevance_gate(*, material: bool, explains: bool, actionable: bool) -> bool:
    """Keep a coaching finding only when at least two relevance questions pass."""
    return sum((material, explains, actionable)) >= 2


def _compact_kills(kills: dict[str, int]) -> str:
    return ", ".join(f"{count} {unit_type}" for unit_type, count in sorted(kills.items())) or "the opposing units tracked in the cluster"


def _supply_provider(race: str | None) -> str:
    return {"Zerg": "Overlord", "Protoss": "Pylon", "Terran": "Supply Depot"}.get(race or "", "supply provider")


def _earlier_harassment(engagements: list[dict[str, Any]], turning_loop: int, player_id: int, speed: str) -> tuple[int, str] | None:
    earlier = sorted((item for item in engagements if item.get("start_loop", 0) < turning_loop), key=lambda item: item.get("start_loop", 0), reverse=True)
    for engagement in earlier:
        kills = engagement.get("kills_by_player", {}).get(str(player_id), {})
        if kills:
            own = engagement.get("losses_by_player", {}).get(str(player_id), {})
            return engagement["start_loop"], f"At {format_real_time(engagement['start_loop'], speed)}, a small run cost {own.get('units', 0)} tracked units and killed {_compact_kills(kills)}."
    return None


def render_review(extraction: dict[str, Any], derivation: dict[str, Any], engagements: list[dict[str, Any]], diagnosis: dict[str, Any], player_id: int, config: AppConfig) -> str:
    """Render the player-facing review after relevance filtering and compression."""
    speed = extraction["metadata"]["game_speed"]
    player = _player(extraction, player_id)
    player_name = _name(extraction, player_id)
    decisive = diagnosis.get("decisive_candidate", {})
    turning = diagnosis.get("turning_point_candidate", {})
    decisive_engagement = next((item for item in engagements if item.get("engagement_id") == decisive.get("engagement_id")), None)
    turning_engagement = next((item for item in engagements if item.get("engagement_id") == turning.get("engagement_id")), None)
    opponent_disruptions = [item for item in derivation.get("economy", {}).get("resource_collection_disruptions", []) if item.get("player_id") != player_id]
    blocks = [item for item in derivation.get("economy", {}).get("candidate_supply_blocks", []) if item.get("player_id") == player_id]
    snapshots = [item for item in derivation.get("player_snapshots", []) if item.get("player_id") == player_id]
    floats = [item for item in derivation.get("economy", {}).get("candidate_resource_floats", []) if item.get("player_id") == player_id]
    large_floats = [item for item in floats if (item.get("minerals") or 0) >= 1000 or (item.get("vespene") or 0) >= 500]
    earlier_harassment = _earlier_harassment(engagements, (turning_engagement or {}).get("start_loop", 0), player_id, speed) if turning_engagement else None
    supporting_contexts: list[tuple[int, str]] = []
    for disruption in sorted(opponent_disruptions, key=lambda item: item.get("start_loop", 0)):
        supporting_contexts.append((
            disruption.get("start_loop", 0),
            f"Between {format_real_time(disruption['start_loop'], speed)} and {format_real_time(disruption['end_loop'], speed)}, the opponent's mineral collection rate fell from {disruption.get('minerals_collection_rate_before')} to {disruption.get('minerals_collection_rate_after')}.",
        ))
    if earlier_harassment:
        supporting_contexts.append(earlier_harassment)
    supporting_context = " ".join(text for _, text in sorted(supporting_contexts)) if supporting_contexts else "No earlier spatially supported harassment or income disruption was available."

    lines = ["# Coaching Review", "", "Timestamps use real elapsed time.", ""]
    if player.get("result") == "Win" and turning_engagement:
        kills = turning_engagement.get("kills_by_player", {}).get(str(player_id), {})
        own = turning_engagement.get("losses_by_player", {}).get(str(player_id), {})
        lines += [
            "## Verdict",
            "",
            f"{player_name} won. The primary lesson is conversion: the important fights were favorable, but the advantage was not closed as efficiently as it could have been. The correction is not to stop applying pressure; it is to make the next spending decision automatic once the opposing army is sufficiently damaged, without inventing a new build.",
            "",
            "## Decisive sequence",
            "",
            f"At {format_real_time(turning_engagement['start_loop'], speed)}, the main engagement cost {own.get('units', 0)} of {player_name}'s units while the opposing cluster lost {_compact_kills(kills)}. {supporting_context} These are supporting tempo facts; the main engagement was not a failed army fight.",
            "",
            "## What mattered",
            "",
        ]
        findings = [
            ("That exchange produced a favorable army transition and should be treated as a winning close, not a disaster. The fight produced the advantage you wanted, so the next decision should be spending immediately, not re-evaluating the fight.", True, True, True),
            (f"By {format_real_time(large_floats[-1]['game_loop'], speed) if large_floats else 'the finish'}, the bank reached {large_floats[-1].get('minerals', 'n/a')} minerals and {large_floats[-1].get('vespene', 'n/a')} gas with roughly {snapshots[-1].get('workers_active_count', 'n/a') if snapshots else 'enough'} workers. The unused bank, not worker count, was the main macro leak.", bool(large_floats), True, True),
            (f"Repeated cap pressure from {format_real_time(blocks[0]['start_loop'], speed)} to {format_real_time(blocks[-1]['start_loop'], speed)} made the follow-up less clean.", bool(blocks), True, True),
        ]
        selected = [text for text, material, explains, actionable in findings if _passes_relevance_gate(material=material, explains=explains, actionable=actionable)]
        lines.extend(f"- {text}" for text in selected[:3])
        lines += [
            "",
            "## Next-game rules",
            "",
            f"1. Queue the next {_supply_provider(player.get('race'))} about 15–20 real seconds before your repeated cap checkpoints; do not let supply friction interrupt the next wave.",
            "2. After a favorable fight, spend immediately on the next army wave, production, or tech. At 1,000+ minerals, the bank is an alarm—not permission to add more workers.",
        ]
    elif decisive_engagement:
        own = decisive_engagement.get("losses_by_player", {}).get(str(player_id), {})
        kills = decisive_engagement.get("kills_by_player", {}).get(str(player_id), {})
        lines += [
            "## Verdict",
            "",
            f"The primary diagnosis is a tactical commitment failure at {format_real_time(decisive_engagement['start_loop'], speed)}: the game turned when the local fight became materially worse and continued to consume the army.",
            "",
            "## Decisive sequence",
            "",
            f"{decisive_engagement['engagement_id']} cost {own.get('units', 0)} tracked units while the opponent lost {_compact_kills(kills)}. The first losing position is the decision to correct; later reinforcements are consequences unless they independently improve the state.",
            "",
            "## What mattered",
            "",
        ]
        candidates = []
        if opponent_disruptions:
            disruption = min(opponent_disruptions, key=lambda item: item.get("start_loop", 0))
            candidates.append((f"Opponent pressure preceded the fight: collection changed from {disruption.get('minerals_collection_rate_before')} to {disruption.get('minerals_collection_rate_after')} between {format_real_time(disruption['start_loop'], speed)} and {format_real_time(disruption['end_loop'], speed)}.", True, True, True))
        candidates.append(("The actionable error was allowing the commitment to continue after the local exchange stopped improving.", True, True, True))
        lines.extend(f"- {text}" for text, material, explains, actionable in candidates if _passes_relevance_gate(material=material, explains=explains, actionable=actionable))
        lines += ["", "## Next-game rules", "", f"1. At {format_real_time(decisive_engagement['start_loop'], speed)}, use a disengagement trigger: if the fight is not improving, stop feeding it and rebuild.", "2. Protect the economy after harassment; make the recovery plan explicit before committing the next army wave."]
    else:
        lines += [
            "## Verdict",
            "",
            f"The replay does not contain enough spatially supported evidence for a confident decisive-failure diagnosis for {player_name}.",
            "",
            "## What mattered",
            "",
            "The available facts should be treated as incomplete rather than converted into invented intent or generic advice.",
            "",
            "## Next-game rules",
            "",
            "1. Review the first position-supported engagement before changing the build.",
        ]
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
