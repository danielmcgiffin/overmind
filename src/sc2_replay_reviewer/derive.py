"""Repeatable analytical facts derived from normalized replay events."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .time import loops_to_game_seconds

WORKER_NAMES = {"Drone", "SCV", "Probe", "MULE"}
ZERG_WORKER_CONSUMING_STRUCTURES = {
    "Hatchery", "Extractor", "SpawningPool", "RoachWarren", "EvolutionChamber",
    "BanelingNest", "HydraliskDen", "LurkerDen", "InfestationPit", "UltraliskCavern",
    "Spire", "GreaterSpire", "NydusNetwork", "SpineCrawler", "SporeCrawler",
}
TOWN_HALL_MARKERS = ("Hatchery", "Lair", "Hive", "CommandCenter", "OrbitalCommand", "PlanetaryFortress", "Nexus")
STRUCTURE_MARKERS = (
    "Hatchery", "Lair", "Hive", "CommandCenter", "OrbitalCommand", "PlanetaryFortress", "Nexus",
    "Gateway", "WarpGate", "Barracks", "Factory", "Starport", "SpawningPool", "RoachWarren",
    "HydraliskDen", "LurkerDen", "BanelingNest", "InfestationPit", "UltraliskCavern", "Spire", "GreaterSpire", "Nydus",
    "EvolutionChamber", "Forge", "CyberneticsCore", "TwilightCouncil",
    "RoboticsFacility", "RoboticsBay", "Stargate", "TemplarArchive", "DarkShrine", "Bunker",
    "PhotonCannon", "ShieldBattery", "SpineCrawler", "SporeCrawler", "Extractor", "Refinery",
    "Assimilator", "Pylon", "TechLab", "Reactor", "CreepTumor", "Beacon",
)

# Used only when a snapshot's exact active-force score is unavailable. Values
# are standard resource costs for common LotV units and intentionally retain an
# unknown bucket for anything not in this small audit-friendly table.
UNIT_VALUES: dict[str, tuple[int, int]] = {
    "Marine": (50, 0), "Marauder": (100, 25), "Medivac": (100, 100),
    "Hellion": (100, 0), "WidowMine": (75, 25), "Cyclone": (125, 50),
    "SiegeTank": (150, 125), "SiegeTankSieged": (150, 125), "Thor": (300, 200), "Viking": (150, 75),
    "Liberator": (150, 125), "Banshee": (150, 100), "Raven": (100, 200),
    "Battlecruiser": (400, 300), "Zealot": (100, 0), "Stalker": (125, 50),
    "Sentry": (50, 100), "Adept": (100, 25), "Immortal": (275, 100),
    "Colossus": (300, 200), "Disruptor": (150, 150), "Observer": (25, 75),
    "WarpPrism": (200, 0), "Phoenix": (150, 100), "VoidRay": (250, 150),
    "Carrier": (350, 250), "Tempest": (250, 175), "Oracle": (150, 150),
    "Archon": (0, 0), "Zergling": (25, 0), "Baneling": (25, 25), "Overlord": (100, 0), "Overseer": (100, 0),
    "Drone": (50, 0), "SCV": (50, 0), "Probe": (50, 0), "MULE": (0, 0), "Pylon": (100, 0),
    "MissileTurret": (100, 0), "Bunker": (100, 0), "SpineCrawler": (100, 0), "SporeCrawler": (75, 0),
    "Roach": (75, 25), "Ravager": (100, 100), "Hydralisk": (100, 50),
    "Lurker": (100, 75), "Mutalisk": (100, 100), "Corruptor": (150, 100),
    "Viper": (100, 200), "Ultralisk": (300, 200), "BroodLord": (300, 250),
    "Queen": (150, 0),
}


def is_worker(unit_type: str | None) -> bool:
    return unit_type in WORKER_NAMES or any(name in (unit_type or "") for name in WORKER_NAMES)


def is_structure(unit_type: str | None) -> bool:
    value = unit_type or ""
    return any(marker in value for marker in STRUCTURE_MARKERS)


def is_army(unit_type: str | None) -> bool:
    return bool(unit_type) and not is_worker(unit_type) and not is_structure(unit_type) and unit_type not in {"Larva", "Egg", "OverlordCocoon"}


def unit_value(unit_type: str | None) -> dict[str, Any]:
    if unit_type in UNIT_VALUES:
        minerals, gas = UNIT_VALUES[unit_type]
        return {"minerals": minerals, "gas": gas, "total": minerals + gas, "known": True}
    return {"minerals": None, "gas": None, "total": None, "known": False}


def _position(event: dict[str, Any]) -> tuple[float, float] | None:
    position = event.get("position")
    if not isinstance(position, list) or len(position) != 2 or None in position:
        return None
    try:
        return float(position[0]), float(position[1])
    except (TypeError, ValueError):
        return None


def _unit_ledger(tracker_events: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    units: dict[str, dict[str, Any]] = {}
    unit_index_to_tag: dict[int, str] = {}
    deaths: list[dict[str, Any]] = []

    def get_unit(tag: int | None) -> dict[str, Any] | None:
        return units.get(str(tag)) if tag is not None else None

    for event in sorted(tracker_events, key=lambda item: (item.get("game_loop", 0), item.get("evidence_id", ""))):
        kind = event.get("event_type")
        loop = int(event.get("game_loop", 0))
        tag = event.get("unit_tag")
        if kind in {"UnitBorn", "UnitInit"} and tag is not None:
            unit = units.setdefault(
                str(tag),
                {
                    "unit_tag": tag,
                    "unit_index": tag >> 18,
                    "unit_type": event.get("unit_type"),
                    "owner_id": event.get("owner_id"),
                    "control_id": event.get("control_id"),
                    "init_loop": loop if kind == "UnitInit" else None,
                    "birth_loop": loop if kind == "UnitBorn" else None,
                    "completion_loop": loop if kind == "UnitBorn" else None,
                    "death_loop": None,
                    "positions": [],
                    "evidence": [event.get("evidence_id")],
                },
            )
            if event.get("unit_type"):
                unit["unit_type"] = event["unit_type"]
            if event.get("owner_id") is not None:
                unit["owner_id"] = event["owner_id"]
            unit["evidence"].append(event.get("evidence_id"))
            unit_index_to_tag[tag >> 18] = str(tag)
            pos = _position(event)
            if pos:
                unit["positions"].append({"game_loop": loop, "position": list(pos), "evidence_id": event.get("evidence_id"), "precision": "tracker event"})
        elif kind == "UnitDone":
            unit = get_unit(tag)
            if unit:
                unit["completion_loop"] = loop
                unit["evidence"].append(event.get("evidence_id"))
        elif kind == "UnitOwnerChange":
            unit = get_unit(tag)
            if unit:
                unit["owner_id"] = event.get("owner_id")
                unit["control_id"] = event.get("control_id")
                unit["evidence"].append(event.get("evidence_id"))
        elif kind == "UnitTypeChange":
            unit = get_unit(tag)
            if unit:
                unit["unit_type"] = event.get("unit_type")
                unit["evidence"].append(event.get("evidence_id"))
        elif kind == "UnitPositions":
            for observation in event.get("positions", []):
                mapped_tag = unit_index_to_tag.get(observation.get("unit_index"))
                if mapped_tag is None or mapped_tag not in units:
                    continue
                units[mapped_tag]["positions"].append(
                    {
                        "game_loop": loop,
                        "position": observation.get("position"),
                        "evidence_id": event.get("evidence_id"),
                        "precision": "sparse damaged-unit tracker snapshot",
                    }
                )
        elif kind == "UnitDied":
            unit = get_unit(tag)
            owner_id = unit.get("owner_id") if unit else None
            unit_type = unit.get("unit_type") if unit else None
            if unit:
                unit["death_loop"] = loop
                unit["death_position"] = event.get("position")
                unit["killer_player_id"] = event.get("killer_player_id")
                unit["killer_unit_tag"] = event.get("killer_unit_tag")
                unit["evidence"].append(event.get("evidence_id"))
            deaths.append(
                {
                    "evidence_id": event.get("evidence_id"),
                    "game_loop": loop,
                    "unit_tag": tag,
                    "unit_type": unit_type,
                    "owner_id": owner_id,
                    "killer_player_id": event.get("killer_player_id"),
                    "killer_unit_tag": event.get("killer_unit_tag"),
                    "position": event.get("position"),
                    "value": unit_value(unit_type),
                    "is_worker": is_worker(unit_type),
                    "is_structure": is_structure(unit_type),
                    "is_army": is_army(unit_type),
                }
            )
    return units, deaths


def _stats_snapshots(tracker_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots = []
    for event in tracker_events:
        if event.get("event_type") != "PlayerStats":
            continue
        snapshot = {
            "evidence_id": event.get("evidence_id"),
            "game_loop": event.get("game_loop", 0),
            "player_id": event.get("player_id"),
            **(event.get("stats") or {}),
        }
        snapshots.append(snapshot)
    return sorted(snapshots, key=lambda item: (item["game_loop"], item.get("player_id") or 0))


def _worker_differentials(snapshots: list[dict[str, Any]], players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        if snapshot.get("player_id") is not None:
            by_player[int(snapshot["player_id"])].append(snapshot)
    result = []
    for left_index, left in enumerate(players):
        for right in players[left_index + 1 :]:
            left_id, right_id = left["player_id"], right["player_id"]
            if left_id not in by_player or right_id not in by_player:
                continue
            right_items = by_player[right_id]
            for left_snapshot in by_player[left_id]:
                candidates = [item for item in right_items if item["game_loop"] <= left_snapshot["game_loop"]]
                if not candidates:
                    continue
                right_snapshot = candidates[-1]
                result.append(
                    {
                        "game_loop": left_snapshot["game_loop"],
                        "left_player_id": left_id,
                        "right_player_id": right_id,
                        "worker_diff": (left_snapshot.get("workers_active_count") or 0) - (right_snapshot.get("workers_active_count") or 0),
                        "supply_diff": (left_snapshot.get("food_used") or 0) - (right_snapshot.get("food_used") or 0),
                        "army_value_diff": ((left_snapshot.get("minerals_used_active_forces") or 0) + (left_snapshot.get("vespene_used_active_forces") or 0)) - ((right_snapshot.get("minerals_used_active_forces") or 0) + (right_snapshot.get("vespene_used_active_forces") or 0)),
                        "evidence": [left_snapshot.get("evidence_id"), right_snapshot.get("evidence_id")],
                    }
                )
    return result


def _composition_snapshots(snapshots: list[dict[str, Any]], units: dict[str, dict[str, Any]], players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for snapshot in snapshots:
        player_id = snapshot.get("player_id")
        composition = Counter()
        structures = Counter()
        unknown_army_units = 0
        army_value = 0
        value_known = True
        for unit in units.values():
            if unit.get("owner_id") != player_id or unit.get("death_loop") is not None and unit.get("death_loop") <= snapshot["game_loop"]:
                continue
            created = unit.get("birth_loop") or unit.get("init_loop") or 0
            if created > snapshot["game_loop"]:
                continue
            unit_type = unit.get("unit_type") or "Unknown"
            if is_structure(unit_type):
                structures[unit_type] += 1
            elif is_army(unit_type):
                composition[unit_type] += 1
                value = unit_value(unit_type)
                if value["known"]:
                    army_value += value["total"] or 0
                else:
                    unknown_army_units += 1
                    value_known = False
        stats_value = (snapshot.get("minerals_used_active_forces") or 0) + (snapshot.get("vespene_used_active_forces") or 0)
        result.append(
            {
                "evidence_id": snapshot.get("evidence_id"),
                "game_loop": snapshot.get("game_loop"),
                "player_id": player_id,
                "workers_active_count": snapshot.get("workers_active_count"),
                "food_used": snapshot.get("food_used"),
                "food_made": snapshot.get("food_made"),
                "minerals_used_active_forces": snapshot.get("minerals_used_active_forces"),
                "vespene_used_active_forces": snapshot.get("vespene_used_active_forces"),
                "composition": dict(sorted(composition.items())),
                "structures": dict(sorted(structures.items())),
                "army_value": stats_value if stats_value else army_value,
                "army_value_source": "player_stats.active_forces" if stats_value else "known_unit_cost_sum",
                "unknown_army_units": unknown_army_units,
                "unit_costs_complete": value_known,
            }
        )
    return result


def _worker_loss_summary(deaths: list[dict[str, Any]], tracker_events: list[dict[str, Any]], players: list[dict[str, Any]]) -> dict[str, Any]:
    player_races = {int(player["player_id"]): player.get("race") for player in players if player.get("player_id") is not None}
    structure_starts: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in tracker_events:
        if event.get("event_type") != "UnitInit" or event.get("owner_id") is None:
            continue
        unit_type = event.get("unit_type") or ""
        if player_races.get(int(event["owner_id"])) == "Zerg" and unit_type in ZERG_WORKER_CONSUMING_STRUCTURES:
            structure_starts[int(event["owner_id"])].append(
                {"game_loop": event.get("game_loop"), "unit_type": unit_type, "evidence_id": event.get("evidence_id")}
            )
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for death in deaths:
        if death.get("is_worker") and death.get("owner_id") is not None:
            by_player[int(death["owner_id"])].append(death)
    result: dict[str, Any] = {}
    for player_id, worker_events in by_player.items():
        attributed = [item for item in worker_events if item.get("killer_player_id") is not None]
        unattributed_count = len(worker_events) - len(attributed)
        starts = structure_starts.get(player_id, [])
        construction_consumed = min(unattributed_count, len(starts)) if player_races.get(player_id) == "Zerg" else 0
        result[str(player_id)] = {
            "raw_worker_death_events": len(worker_events),
            "killer_attributed_events": len(attributed),
            "zerg_structure_starts": len(starts),
            "estimated_construction_consumed": construction_consumed,
            "estimated_worker_losses": len(worker_events) - construction_consumed,
            "construction_evidence": [item["evidence_id"] for item in starts if item.get("evidence_id")],
            "classification": "heuristic: raw Zerg Drone deaths are decomposed into structure starts plus remaining worker-loss events; exact builder-to-structure identity is unavailable",
        }
    return result


def _loss_aggregates(deaths: list[dict[str, Any]], tracker_events: list[dict[str, Any]], players: list[dict[str, Any]]) -> dict[str, Any]:
    by_player: dict[str, Counter] = defaultdict(Counter)
    by_player_value: dict[str, dict[str, int | None]] = defaultdict(lambda: {"minerals": 0, "gas": 0, "known_units": 0, "unknown_units": 0})
    worker_deaths = []
    for death in deaths:
        owner = death.get("owner_id")
        if owner is None:
            continue
        by_player[str(owner)][death.get("unit_type") or "Unknown"] += 1
        value = by_player_value[str(owner)]
        if death["value"]["known"]:
            value["minerals"] += death["value"]["minerals"] or 0
            value["gas"] += death["value"]["gas"] or 0
            value["known_units"] += 1
        else:
            value["unknown_units"] += 1
        if death.get("is_worker"):
            worker_deaths.append(death)
    return {
        "unit_losses_by_player": {player: dict(sorted(counter.items())) for player, counter in sorted(by_player.items())},
        "known_unit_loss_value_by_player": dict(sorted(by_player_value.items())),
        "worker_deaths": worker_deaths,
        "worker_loss_summary_by_player": _worker_loss_summary(deaths, tracker_events, players),
    }


def _timing_facts(units: dict[str, dict[str, Any]], tracker_events: list[dict[str, Any]]) -> dict[str, Any]:
    upgrades = [
        {
            "game_loop": event.get("game_loop"),
            "player_id": event.get("player_id"),
            "upgrade": event.get("upgrade"),
            "count": event.get("count"),
            "evidence": [event.get("evidence_id")],
        }
        for event in tracker_events
        if event.get("event_type") == "Upgrade" and not str(event.get("upgrade") or "").startswith(("RewardDance", "Spray"))
    ]
    completed = []
    towns_by_player: dict[str, int] = defaultdict(int)
    for unit in units.values():
        unit_type = unit.get("unit_type") or ""
        if unit.get("completion_loop") is None:
            continue
        if is_structure(unit_type):
            completed.append(
                {
                    "game_loop": unit["completion_loop"],
                    "player_id": unit.get("owner_id"),
                    "unit_type": unit_type,
                    "unit_tag": unit.get("unit_tag"),
                    "is_town_hall": any(marker in unit_type for marker in TOWN_HALL_MARKERS),
                    "evidence": unit.get("evidence", []),
                }
            )
            if any(marker in unit_type for marker in TOWN_HALL_MARKERS):
                towns_by_player[str(unit.get("owner_id"))] += 1
    expansions = []
    seen_towns: dict[str, int] = defaultdict(int)
    for town in sorted((item for item in completed if item["is_town_hall"]), key=lambda item: item["game_loop"]):
        key = str(town.get("player_id"))
        seen_towns[key] += 1
        if seen_towns[key] > 1:
            expansions.append({**town, "expansion_number": seen_towns[key] - 1})
    return {
        "upgrades": upgrades,
        "completed_structures": sorted(completed, key=lambda item: item["game_loop"]),
        "expansions": expansions,
    }


def _economic_flags(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        if snapshot.get("player_id") is not None:
            by_player[int(snapshot["player_id"])].append(snapshot)
    supply_blocks = []
    floats = []
    plateaus = []
    for player_id, items in by_player.items():
        items.sort(key=lambda item: item["game_loop"])
        for index, snapshot in enumerate(items):
            food_used, food_made = snapshot.get("food_used"), snapshot.get("food_made")
            if food_used is not None and food_made is not None and food_made - food_used <= 0.5:
                next_item = items[index + 1] if index + 1 < len(items) else None
                if next_item and next_item["game_loop"] - snapshot["game_loop"] >= 80:
                    supply_blocks.append(
                        {
                            "player_id": player_id,
                            "start_loop": snapshot["game_loop"],
                            "end_loop": next_item["game_loop"],
                            "supply_used": food_used,
                            "supply_available": food_made,
                            "evidence": [snapshot.get("evidence_id"), next_item.get("evidence_id")],
                            "interpretation_status": "candidate; stats alone do not prove a production pause",
                        }
                    )
            if (snapshot.get("minerals_current") or 0) >= 800 or (snapshot.get("vespene_current") or 0) >= 500:
                floats.append(
                    {
                        "player_id": player_id,
                        "game_loop": snapshot["game_loop"],
                        "minerals": snapshot.get("minerals_current"),
                        "vespene": snapshot.get("vespene_current"),
                        "evidence": [snapshot.get("evidence_id")],
                        "interpretation_status": "candidate; resource float is not by itself proof of a mistake",
                    }
                )
        run_start = None
        previous = None
        for snapshot in items:
            if previous and snapshot.get("workers_active_count") == previous.get("workers_active_count") and snapshot["game_loop"] - previous["game_loop"] >= 240:
                run_start = run_start or previous
            elif run_start:
                plateaus.append(
                    {
                        "player_id": player_id,
                        "start_loop": run_start["game_loop"],
                        "end_loop": previous["game_loop"],
                        "worker_count": previous.get("workers_active_count"),
                        "evidence": [run_start.get("evidence_id"), previous.get("evidence_id")],
                        "interpretation_status": "observable plateau; not automatically an error",
                    }
                )
                run_start = None
            previous = snapshot
        if run_start and previous:
            plateaus.append(
                {
                    "player_id": player_id,
                    "start_loop": run_start["game_loop"],
                    "end_loop": previous["game_loop"],
                    "worker_count": previous.get("workers_active_count"),
                    "evidence": [run_start.get("evidence_id"), previous.get("evidence_id")],
                    "interpretation_status": "observable plateau; not automatically an error",
                }
            )
    return {"candidate_supply_blocks": supply_blocks, "candidate_resource_floats": floats, "worker_count_plateaus": plateaus}


def _resource_collection_disruptions(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find sharp snapshot-to-snapshot collection-rate drops.

    A drop is evidence of economic interruption, not proof of the exact cause.
    Worker pulls, deaths, transfers, saturation changes, and missing snapshots
    can all affect the rate.
    """
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        if snapshot.get("player_id") is not None:
            by_player[int(snapshot["player_id"])].append(snapshot)
    disruptions: list[dict[str, Any]] = []
    for player_id, items in by_player.items():
        items.sort(key=lambda item: item["game_loop"])
        for previous, current in zip(items, items[1:]):
            before = previous.get("minerals_collection_rate")
            after = current.get("minerals_collection_rate")
            if before is None or after is None or before < 500:
                continue
            absolute_drop = before - after
            relative_drop = absolute_drop / before if before else 0.0
            if absolute_drop < 300 or relative_drop < 0.35:
                continue
            disruptions.append(
                {
                    "player_id": player_id,
                    "start_loop": previous["game_loop"],
                    "end_loop": current["game_loop"],
                    "minerals_collection_rate_before": before,
                    "minerals_collection_rate_after": after,
                    "gas_collection_rate_before": previous.get("vespene_collection_rate"),
                    "gas_collection_rate_after": current.get("vespene_collection_rate"),
                    "absolute_mineral_rate_drop": absolute_drop,
                    "relative_mineral_rate_drop": round(relative_drop, 3),
                    "evidence": [previous.get("evidence_id"), current.get("evidence_id")],
                    "interpretation_status": "candidate economic interruption; supports worker pull or mining disruption but does not prove its exact cause",
                }
            )
    return disruptions


def derive_facts(extraction: dict[str, Any]) -> dict[str, Any]:
    tracker_events = extraction.get("tracker_events", [])
    players = extraction.get("players", [])
    units, deaths = _unit_ledger(tracker_events)
    snapshots = _stats_snapshots(tracker_events)
    timing = _timing_facts(units, tracker_events)
    derivation = {
        "schema_version": extraction.get("schema_version"),
        "facts_version": "1.0",
        "player_snapshots": snapshots,
        "worker_differentials": _worker_differentials(snapshots, players),
        "units": sorted(units.values(), key=lambda item: (item.get("init_loop") or item.get("birth_loop") or 0, item.get("unit_tag") or 0)),
        "deaths": deaths,
        "losses": _loss_aggregates(deaths, tracker_events, players),
        "composition_snapshots": _composition_snapshots(snapshots, units, players),
        "timing": timing,
        "economy": {
            **_economic_flags(snapshots),
            "resource_collection_disruptions": _resource_collection_disruptions(snapshots),
        },
        "production": {
            "capacity_is_approximate": True,
            "note": "Production capacity is counted from active production structures in tracker state; queues and worker assignment are not fully observable.",
        },
        "evidence_policy": "Every item points to normalized tracker or snapshot evidence IDs; sparse positions are never interpolated.",
    }
    return derivation
