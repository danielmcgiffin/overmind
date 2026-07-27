"""Diagnostic hierarchy: facts first, then explicitly labeled inferences."""

from __future__ import annotations

from typing import Any

from .derive import is_army
from .time import format_real_time


ARMORED_CORE_TYPES = {
    "SiegeTank", "SiegeTankSieged", "Thor", "Colossus", "Immortal", "Ultralisk",
}
HARASSMENT_STRUCTURE_TYPES = {"Pylon", "Gateway", "WarpGate", "Nexus", "Hatchery", "CommandCenter", "OrbitalCommand"}


def _engagement_assessment(engagement: dict[str, Any], player_id: int, opponents: list[int]) -> dict[str, Any]:
    """Classify the local trade without pretending to run the combat engine."""
    own = engagement.get("losses_by_player", {}).get(str(player_id), {})
    own_types = engagement.get("loss_types_by_player", {}).get(str(player_id), {})
    kills = engagement.get("kills_by_player", {}).get(str(player_id), {})
    own_value = own.get("known_minerals", 0) + own.get("known_gas", 0)
    enemy_value = sum(
        engagement.get("losses_by_player", {}).get(str(opponent), {}).get("known_minerals", 0)
        + engagement.get("losses_by_player", {}).get(str(opponent), {}).get("known_gas", 0)
        for opponent in opponents
    )
    enemy_units = sum(
        engagement.get("losses_by_player", {}).get(str(opponent), {}).get("units", 0)
        for opponent in opponents
    )
    enemy_army_units = sum(
        engagement.get("losses_by_player", {}).get(str(opponent), {}).get("army_units", 0)
        for opponent in opponents
    )
    core_kills = {unit_type: count for unit_type, count in kills.items() if unit_type in ARMORED_CORE_TYPES}
    harassment_structure_kills = {unit_type: count for unit_type, count in kills.items() if unit_type in HARASSMENT_STRUCTURE_TYPES}
    cheap_own_losses = sum(
        count for unit_type, count in own_types.items()
        if unit_type in {"Zergling", "Marine", "Zealot", "Drone", "SCV", "Probe"}
    )
    if core_kills and cheap_own_losses >= max(3, own.get("units", 0) // 2):
        return {
            "label": "favorable_core_kill",
            "summary": "The reviewed player removed the opposing armored core while most local losses were cheap units; this is not sufficient evidence of a tactical loss.",
            "core_kills": core_kills,
            "harassment_structure_kills": harassment_structure_kills,
            "own_known_loss": own_value,
            "enemy_known_loss": enemy_value,
        }
    if harassment_structure_kills and cheap_own_losses >= max(3, own.get("units", 0) // 2):
        return {
            "label": "favorable_harassment",
            "summary": "The reviewed player traded a small cheap force for an opposing production or supply structure and/or workers; the exchange is favorable harassment, not an automatic tactical loss.",
            "core_kills": core_kills,
            "harassment_structure_kills": harassment_structure_kills,
            "own_known_loss": own_value,
            "enemy_known_loss": enemy_value,
        }
    if own.get("units", 0) <= 3 and enemy_units >= max(2, own.get("units", 0) * 2) and (own.get("army_units", 0) or 0) <= 3:
        return {
            "label": "even_or_favorable",
            "summary": "The reviewed player lost only a small local force while the opposing cluster lost substantially more units; this is not sufficient evidence of a tactical loss.",
            "core_kills": core_kills,
            "own_known_loss": own_value,
            "enemy_known_loss": enemy_value,
        }
    if own_value or enemy_value:
        score = own_value - enemy_value
    else:
        score = (own.get("units", 0) - enemy_units) * 100
    negative_label = "minor_negative" if score > 0 and own.get("units", 0) <= 6 and own_value < 300 else "candidate_negative"
    return {
        "label": negative_label if score > 0 else "even_or_favorable",
        "summary": ("Observed local losses were higher than opposing losses, but the cluster is small and should be treated as a setback rather than a decisive game turn." if negative_label == "minor_negative" else "Observed local losses were materially higher than opposing losses by the available value estimate.") if score > 0 else "Observed losses were even or favorable by the available value estimate.",
        "core_kills": core_kills,
        "harassment_structure_kills": harassment_structure_kills,
        "own_known_loss": own_value,
        "enemy_known_loss": enemy_value,
        "score": score,
    }


def _name(extraction: dict[str, Any], player_id: int | None) -> str:
    for player in extraction.get("players", []):
        if player.get("player_id") == player_id:
            return player.get("name") or f"Player {player_id}"
    return f"Player {player_id}" if player_id is not None else "unknown player"


def _team(extraction: dict[str, Any], player_id: int | None) -> int | None:
    for player in extraction.get("players", []):
        if player.get("player_id") == player_id:
            return player.get("team_id")
    return None


def _opponents(extraction: dict[str, Any], player_id: int) -> list[int]:
    target_team = _team(extraction, player_id)
    return [player["player_id"] for player in extraction.get("players", []) if player.get("player_id") != player_id and player.get("team_id") != target_team]


def _engagement_score(engagement: dict[str, Any], player_id: int, opponents: list[int]) -> tuple[float, int, int]:
    own = engagement.get("losses_by_player", {}).get(str(player_id), {})
    own_value = own.get("known_minerals", 0) + own.get("known_gas", 0)
    enemy_value = sum(
        engagement.get("losses_by_player", {}).get(str(opponent), {}).get("known_minerals", 0)
        + engagement.get("losses_by_player", {}).get(str(opponent), {}).get("known_gas", 0)
        for opponent in opponents
    )
    own_units = own.get("units", 0)
    enemy_units = sum(engagement.get("losses_by_player", {}).get(str(opponent), {}).get("units", 0) for opponent in opponents)
    # Prefer resource value; fall back to unit differential where costs are unknown.
    score = float(own_value - enemy_value) if own_value or enemy_value else float(own_units - enemy_units) * 100.0
    return score, own_units, enemy_units


def _nearest_snapshot(snapshots: list[dict[str, Any]], player_id: int, loop: int, before: bool = True) -> dict[str, Any] | None:
    candidates = [item for item in snapshots if item.get("player_id") == player_id and ((item["game_loop"] <= loop) if before else (item["game_loop"] >= loop))]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item["game_loop"])[-1 if before else 0]


def build_diagnostic(extraction: dict[str, Any], derivation: dict[str, Any], engagements: list[dict[str, Any]], player_id: int) -> dict[str, Any]:
    speed = extraction["metadata"]["game_speed"]
    opponents = _opponents(extraction, player_id)
    facts: list[dict[str, Any]] = []
    inferences: list[dict[str, Any]] = []

    def fact(kind: str, statement: str, loop: int | None, evidence: list[str] | None, **extra: Any):
        facts.append({"fact_id": f"fact:{len(facts) + 1}", "kind": kind, "statement": statement, "game_loop": loop, "real_time": format_real_time(loop or 0, speed), "evidence": [item for item in (evidence or []) if item], **extra})

    def inference(category: str, statement: str, loop: int | None, evidence: list[str] | None, confidence: str = "medium", **extra: Any):
        inferences.append({"inference_id": f"inference:{len(inferences) + 1}", "category": category, "statement": statement, "game_loop": loop, "real_time": format_real_time(loop or 0, speed), "evidence": [item for item in (evidence or []) if item], "confidence": confidence, **extra})

    target = next((item for item in extraction.get("players", []) if item.get("player_id") == player_id), {})
    fact("match", f"{target.get('name', player_id)} played {target.get('race') or 'an unavailable race'} on {extraction['metadata'].get('map') or 'an unavailable map'} at {speed} speed.", 0, [], player_id=player_id)
    engagement_assessments: dict[str, dict[str, Any]] = {}
    for engagement in engagements:
        assessment = _engagement_assessment(engagement, player_id, opponents)
        engagement_assessments[engagement["engagement_id"]] = assessment
        losses = engagement.get("losses_by_player", {}).get(str(player_id), {})
        enemy_losses = sum(engagement.get("losses_by_player", {}).get(str(opponent), {}).get("units", 0) for opponent in opponents)
        fact(
            "engagement",
            f"{engagement['engagement_id']} clustered {engagement['death_count']} deaths near {engagement.get('centroid')}; {_name(extraction, player_id)} lost {losses.get('units', 0)} units and the opposing side lost {enemy_losses} units. Trade classification: {assessment['label']}.",
            engagement["start_loop"],
            engagement.get("evidence", []),
            engagement_id=engagement["engagement_id"],
            assessment=assessment,
        )
    own_worker_deaths = [death for death in derivation.get("losses", {}).get("worker_deaths", []) if death.get("owner_id") == player_id]
    if own_worker_deaths:
        killer_counts = {}
        for death in own_worker_deaths:
            killer_counts[death.get("killer_player_id")] = killer_counts.get(death.get("killer_player_id"), 0) + 1
        summary = derivation.get("losses", {}).get("worker_loss_summary_by_player", {}).get(str(player_id), {})
        fact("worker_losses", f"{_name(extraction, player_id)} generated {summary.get('raw_worker_death_events', len(own_worker_deaths))} raw worker-death events; the decomposition estimates {summary.get('estimated_construction_consumed', 0)} construction-consumed workers and {summary.get('estimated_worker_losses', len(own_worker_deaths))} actual worker-loss events. Killer attribution was available for {summary.get('killer_attributed_events', 0)}.", own_worker_deaths[0].get("game_loop"), [death.get("evidence_id") for death in own_worker_deaths], killer_counts=killer_counts, worker_loss_summary=summary)
    for block in derivation.get("economy", {}).get("candidate_supply_blocks", []):
        if block.get("player_id") == player_id:
            fact("supply_candidate", f"The stats snapshots show {block.get('supply_used')} used against {block.get('supply_available')} available across a snapshot interval; this is not proof of an unproductive block.", block.get("start_loop"), block.get("evidence"))
    for disruption in derivation.get("economy", {}).get("resource_collection_disruptions", []):
        if disruption.get("player_id") != player_id:
            fact(
                "economic_disruption",
                f"{_name(extraction, disruption.get('player_id'))}'s mineral collection rate fell from {disruption.get('minerals_collection_rate_before')} to {disruption.get('minerals_collection_rate_after')} across a snapshot interval. This supports an economic interruption but does not prove the exact cause.",
                disruption.get("start_loop"),
                disruption.get("evidence"),
                player_id=disruption.get("player_id"),
                disruption=disruption,
            )
    for upgrade in derivation.get("timing", {}).get("upgrades", []):
        if upgrade.get("player_id") == player_id:
            fact("upgrade", f"{_name(extraction, player_id)} completed {upgrade.get('upgrade')}.", upgrade.get("game_loop"), upgrade.get("evidence"))

    scored = sorted(
        ((_engagement_score(item, player_id, opponents), item) for item in engagements if player_id in item.get("participants", [])),
        key=lambda pair: pair[0][0],
        reverse=True,
    )
    negative_scored = [
        pair for pair in scored
        if engagement_assessments.get(pair[1]["engagement_id"], {}).get("label") == "candidate_negative"
    ]
    decisive = negative_scored[0][1] if negative_scored else None
    decisive_score = negative_scored[0][0] if negative_scored else None
    turning_candidates = [
        (
            sum(value.get("minerals", 0) + value.get("gas", 0) for killer, value in engagement.get("kill_value_by_player", {}).items() if int(killer) == player_id),
            engagement,
        )
        for engagement in engagements
        if player_id in engagement.get("participants", [])
    ]
    turning_candidates.sort(key=lambda pair: (pair[0], -pair[1].get("start_loop", 0)))
    turning = turning_candidates[-1][1] if turning_candidates else None
    causal_chain: list[dict[str, Any]] = []
    if decisive:
        own_loss = decisive.get("losses_by_player", {}).get(str(player_id), {})
        evidence = list(decisive.get("evidence", []))
        inference("tactical", f"The largest candidate negative state change was {decisive['engagement_id']} at {format_real_time(decisive['start_loop'], speed)} real: {_name(extraction, player_id)} lost {own_loss.get('units', 0)} units in a spatially clustered fight. This is a candidate decisive turning point, not a combat simulation result.", decisive["start_loop"], evidence, confidence="medium", decisive=True)
        causal_chain.append({"category": "turning_point", "statement": f"At {format_real_time(decisive['start_loop'], speed)} real, the player committed to a fight in which the tracked losses were materially worse than the opponent's.", "evidence": evidence})
        for wave in decisive.get("reinforcement_waves", []):
            if wave.get("player_id") == player_id and wave.get("unit_count", 0) >= 2:
                inference("reinforcement", f"A candidate reinforcement wave of {wave['unit_count']} units was observed near the engagement after it began. Sparse tracker positions cannot prove the player's camera, intent, or exact movement path, but the timing is consistent with continuing the commitment.", wave["start_loop"], wave.get("evidence", []), confidence="low")
                causal_chain.append({"category": "reinforcement", "statement": "Additional units appeared near the fight after it began, extending the losing commitment as an approximate observed pattern.", "evidence": wave.get("evidence", [])})

        prior_worker_deaths = [
            death
            for death in own_worker_deaths
            if death.get("game_loop", 0) < decisive["start_loop"]
            and death.get("killer_player_id") in opponents
        ]
        if prior_worker_deaths:
            killer_ids = {death.get("killer_player_id") for death in prior_worker_deaths}
            inference("opponent_damage", f"Before the candidate turning point, opponent-attributed worker damage was recorded: {len(prior_worker_deaths)} worker deaths. That damage reduced the economic state available for the later decision; the replay does not reveal intent or vision beyond the event evidence.", prior_worker_deaths[0]["game_loop"], [death.get("evidence_id") for death in prior_worker_deaths], confidence="high")
            causal_chain.insert(0, {"category": "opponent_damage", "statement": f"Before the fight, tracked harassment killed {len(prior_worker_deaths)} workers; this is opponent-created damage, not by itself proof of the player's response.", "evidence": [death.get("evidence_id") for death in prior_worker_deaths]})

        pre = _nearest_snapshot(derivation.get("player_snapshots", []), player_id, decisive["start_loop"], before=True)
        post = _nearest_snapshot(derivation.get("player_snapshots", []), player_id, decisive["end_loop"], before=False)
        if pre and post:
            worker_change = (post.get("workers_active_count") or 0) - (pre.get("workers_active_count") or 0)
            army_change = ((post.get("minerals_used_active_forces") or 0) + (post.get("vespene_used_active_forces") or 0)) - ((pre.get("minerals_used_active_forces") or 0) + (pre.get("vespene_used_active_forces") or 0))
            fact("state_change", f"Between the nearest tracked snapshots around {decisive['engagement_id']}, worker count changed by {worker_change} and active-force resource value changed by {army_change}.", decisive["end_loop"], [pre.get("evidence_id"), post.get("evidence_id")])
            if worker_change < 0:
                inference("economy", f"The tracked post-fight state had {abs(worker_change)} fewer workers than the pre-fight snapshot. This supports an economic collapse after the engagement, but the snapshot cadence cannot assign the exact cause of every change.", decisive["end_loop"], [pre.get("evidence_id"), post.get("evidence_id")], confidence="medium")
            if army_change < 0:
                causal_chain.append({"category": "state_change", "statement": f"The nearest post-fight snapshot was down {abs(army_change)} active-force resource points relative to the pre-fight snapshot.", "evidence": [pre.get("evidence_id"), post.get("evidence_id")]})

    if turning and not decisive:
        assessment = engagement_assessments[turning["engagement_id"]]
        kill_types = turning.get("kills_by_player", {}).get(str(player_id), {})
        fact(
            "turning_point",
            f"The strongest known local combat transition for {_name(extraction, player_id)} was {turning['engagement_id']}: the reviewed player was credited by the replay with these opposing unit deaths: {kill_types or 'none with player attribution'}.",
            turning["start_loop"],
            turning.get("evidence", []),
            engagement_id=turning["engagement_id"],
            assessment=assessment,
        )
        inference(
            "turning_point",
            f"The replay does not support calling {turning['engagement_id']} a tactical loss. It is the strongest favorable or even combat transition in the decoded data: {assessment['summary']}",
            turning["start_loop"],
            turning.get("evidence", []),
            confidence="medium",
            turning_point=True,
        )
        causal_chain.append({
            "category": "favorable_turn",
            "statement": f"At {format_real_time(turning['start_loop'], speed)} real, the opponent's locally observed army lost {kill_types or 'units with available killer attribution'}; the exchange should be coached as a conversion opportunity, not mislabeled as the player's loss.",
            "evidence": turning.get("evidence", []),
        })

    if not decisive and not turning:
        inference("availability", "No spatially supported multi-player engagement met the clustering threshold, so a decisive fight cannot be identified from the available tracker deaths.", None, [], confidence="high")

    effectively_lost_loop = None
    if decisive:
        post_states = decisive.get("state", {}).get("post", {})
        target_post = post_states.get(str(player_id))
        if target_post:
            target_value = target_post.get("army_value") or 0
            enemy_values = [state.get("army_value") or 0 for pid, state in post_states.items() if int(pid) in opponents]
            if enemy_values and target_value < max(enemy_values) * 0.5:
                effectively_lost_loop = decisive["end_loop"]
    if effectively_lost_loop is not None:
        inference("game_state", f"The game became effectively lost by the post-engagement snapshot at {format_real_time(effectively_lost_loop, speed)} real under the heuristic used here: the player's tracked army value was below half the strongest opposing value. This is a state heuristic, not a replay-native flag.", effectively_lost_loop, decisive.get("evidence", []) if decisive else [], confidence="low")

    categories = sorted({item["category"] for item in inferences})
    return {
        "schema_version": extraction.get("schema_version"),
        "facts": facts,
        "inferences": inferences,
        "causal_chain": causal_chain,
        "decisive_candidate": {
            "engagement_id": decisive.get("engagement_id") if decisive else None,
            "game_loop": decisive.get("start_loop") if decisive else None,
            "score": decisive_score[0] if decisive_score else None,
            "player_loss_units": decisive_score[1] if decisive_score else None,
            "opponent_loss_units": decisive_score[2] if decisive_score else None,
        },
        "turning_point_candidate": {
            "engagement_id": turning.get("engagement_id") if turning else None,
            "game_loop": turning.get("start_loop") if turning else None,
            "assessment": engagement_assessments.get(turning.get("engagement_id")) if turning else None,
        },
        "effectively_lost_loop": effectively_lost_loop,
        "diagnostic_categories": categories,
        "limitations": [
            "The replay does not expose vision, camera attention, control groups, intent, or full combat simulation state.",
            "Sparse position tracker events are approximate and are not interpolated.",
            "A candidate turning point is selected from observed state changes; the earliest imperfection is not automatically decisive.",
        ],
    }
