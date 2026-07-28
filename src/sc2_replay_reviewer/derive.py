"""Repeatable analytical facts derived from normalized replay events."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .time import loops_to_game_seconds
from .version import FACTS_VERSION

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
PRODUCTION_STRUCTURE_NAMES = {
    "Hatchery", "Lair", "Hive", "Barracks", "Factory", "Starport", "Gateway", "WarpGate",
    "RoboticsFacility", "Stargate",
}

CONSTRAINT_PRIORITY = (
    "supply_blocked",
    "insufficient_production",
    "insufficient_larva",
    "production_idle",
    "tech_transition_bank",
    "overdroning",
    "attention_diversion",
    "gas_imbalance",
    "mineral_imbalance",
    "intentional_reserve",
    "unknown",
)

# Costs include the requirements needed to avoid describing an impossible
# purchase.  These are used for bounded illustrations, not combat simulation.
PURCHASE_COSTS = {
    "Roach": {"minerals": 75, "gas": 25, "supply": 2, "larva": 1, "tech": "RoachWarren"},
    "Zergling": {"minerals": 25, "gas": 0, "supply": 0.5, "larva": 1, "tech": "SpawningPool"},
}

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
    larva_observed_by_player = {
        unit.get("owner_id")
        for unit in units.values()
        if unit.get("unit_type") == "Larva" and unit.get("owner_id") is not None
    }
    for snapshot in snapshots:
        player_id = snapshot.get("player_id")
        composition = Counter()
        structures = Counter()
        production_structures = Counter()
        available_larva = 0
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
            if unit_type == "Larva":
                available_larva += 1
            elif is_structure(unit_type):
                structures[unit_type] += 1
                if unit_type in PRODUCTION_STRUCTURE_NAMES:
                    production_structures[unit_type] += 1
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
                "production_structures": dict(sorted(production_structures.items())),
                "available_production_capacity": sum(production_structures.values()),
                "production_observation_reliable": bool(structures),
                "available_larva": available_larva if player_id in larva_observed_by_player else None,
                "larva_observation_reliable": player_id in larva_observed_by_player,
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


def _float_constraints(
    episode: dict[str, Any],
    supply_blocks: list[dict[str, Any]],
    player_race: str | None,
) -> list[str]:
    constraints: list[str] = []
    supply = episode.get("supply_at_peak") or {}
    peak_supply_room = None
    if supply.get("used") is not None and supply.get("available") is not None:
        peak_supply_room = float(supply["available"]) - float(supply["used"])
    supply_near_peak = any(
        item.get("start_loop", 0) <= episode.get("peak_loop", 0) + 160
        and item.get("end_loop", 0) >= episode.get("peak_loop", 0) - 160
        for item in supply_blocks
    )
    if (peak_supply_room is not None and peak_supply_room <= 2) or supply_near_peak:
        constraints.append("supply_blocked")
    if episode.get("peak_minerals", 0) >= 1000 and episode.get("production_observation_reliable") and episode.get("available_production_capacity") == 0:
        constraints.append("insufficient_production")
    if player_race == "Zerg" and episode.get("larva_observation_reliable") and episode.get("available_larva") == 0:
        constraints.append("insufficient_larva")
    tech_resources = episode.get("technology_resources_in_progress", {})
    if any(value for value in tech_resources.values()):
        constraints.append("tech_transition_bank")
    if episode.get("peak_minerals", 0) >= 1000 and episode.get("peak_gas", 0) < 200:
        constraints.append("gas_imbalance")
    if episode.get("peak_gas", 0) >= 500 and episode.get("peak_minerals", 0) < 500:
        constraints.append("mineral_imbalance")
    if episode.get("available_production_capacity", 0) > 0 and episode.get("peak_minerals", 0) >= 1000:
        constraints.append("production_idle")
    if not constraints:
        constraints.append("unknown")
    return sorted(set(constraints), key=lambda item: CONSTRAINT_PRIORITY.index(item) if item in CONSTRAINT_PRIORITY else len(CONSTRAINT_PRIORITY))


def _purchasing_power(episode: dict[str, Any], player_race: str | None, composition: dict[str, Any]) -> dict[str, Any]:
    """Return bounded resource-equivalent purchases for an episode peak.

    The replay exposes a bank and some state snapshots, but not complete queue
    state.  Therefore the result distinguishes resource bounds from an
    immediate upper bound that is also limited by known supply, larva, and tech.
    """
    if player_race != "Zerg":
        return {}
    minerals = max(0, int(episode.get("peak_minerals") or 0))
    gas = max(0, int(episode.get("peak_gas") or 0))
    supply = episode.get("supply_at_peak") or {}
    supply_room = None
    if supply.get("used") is not None and supply.get("available") is not None:
        supply_room = max(0.0, float(supply["available"]) - float(supply["used"]))
    larva = episode.get("available_larva") if episode.get("larva_observation_reliable") else None
    structures = composition.get("structures", {})
    production_capacity = composition.get("available_production_capacity")
    result: dict[str, Any] = {}
    for unit_type in ("Roach", "Zergling"):
        cost = PURCHASE_COSTS[unit_type]
        resource_bound = min(
            minerals // cost["minerals"],
            gas // cost["gas"] if cost["gas"] else minerals // cost["minerals"],
        )
        supply_bound = int(supply_room // cost["supply"]) if supply_room is not None else None
        larva_bound = int(larva // cost["larva"]) if larva is not None else None
        tech_known = any(count > 0 for name, count in structures.items() if cost["tech"] in name)
        tech_available: bool | None = tech_known if composition.get("structures") else None
        bounds = [resource_bound]
        if supply_bound is not None:
            bounds.append(supply_bound)
        if larva_bound is not None:
            bounds.append(larva_bound)
        immediate_upper_bound = min(bounds) if tech_available is True else (0 if tech_available is False else None)
        result[unit_type] = {
            "cost": {"minerals": cost["minerals"], "gas": cost["gas"], "supply": cost["supply"], "larva": cost["larva"]},
            "resource_bound": int(resource_bound),
            "supply_bound": supply_bound,
            "larva_bound": larva_bound,
            "tech_required": cost["tech"],
            "tech_available": tech_available,
            "production_capacity_observed": production_capacity,
            "immediate_upper_bound": immediate_upper_bound,
            "interpretation_status": "resource equivalent; queue timing and exact larva reservation remain unavailable",
        }
    return result


def _float_episodes(
    snapshots: list[dict[str, Any]],
    compositions: list[dict[str, Any]],
    timing: dict[str, Any],
    deaths: list[dict[str, Any]],
    players: list[dict[str, Any]],
    supply_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group sustained resource banks into auditable episodes.

    A threshold crossing is a candidate float, not proof of an execution error.
    The episode retains the nearest stats/composition evidence and explicitly
    marks queue/attention claims as unavailable when the replay cannot prove them.
    """
    player_races = {int(player["player_id"]): player.get("race") for player in players if player.get("player_id") is not None}
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    comp_by_key = {(item.get("player_id"), item.get("game_loop")): item for item in compositions}
    for snapshot in snapshots:
        if snapshot.get("player_id") is not None:
            by_player[int(snapshot["player_id"])].append(snapshot)
    all_episodes: list[dict[str, Any]] = []
    for player_id, items in by_player.items():
        items.sort(key=lambda item: item["game_loop"])
        index = 0
        while index < len(items):
            snapshot = items[index]
            is_float = (snapshot.get("minerals_current") or 0) >= 800 or (snapshot.get("vespene_current") or 0) >= 500
            if not is_float:
                index += 1
                continue
            start_index = index
            qualified: list[dict[str, Any]] = []
            while index < len(items):
                current = items[index]
                if (current.get("minerals_current") or 0) < 800 and (current.get("vespene_current") or 0) < 500:
                    break
                qualified.append(current)
                index += 1
            last_qualified = qualified[-1]
            boundary = items[index] if index < len(items) else None
            peak = max(qualified, key=lambda item: (item.get("minerals_current") or 0) + (item.get("vespene_current") or 0))
            peak_loop = peak["game_loop"]
            composition = comp_by_key.get((player_id, peak_loop))
            if composition is None:
                same_player = [item for item in compositions if item.get("player_id") == player_id]
                composition = min(same_player, key=lambda item: abs(item.get("game_loop", 0) - peak_loop), default={})
            completed_towns = [
                item for item in timing.get("completed_structures", [])
                if item.get("player_id") == player_id and item.get("is_town_hall") and item.get("game_loop", 0) <= peak_loop
            ]
            tech_resources = {
                "minerals": peak.get("minerals_used_in_progress_technology") or 0,
                "gas": peak.get("vespene_used_in_progress_technology") or 0,
            }
            active_deaths = [
                item for item in deaths
                if item.get("game_loop", 0) >= qualified[0]["game_loop"]
                and item.get("game_loop", 0) <= (boundary or last_qualified).get("game_loop", 0)
                and (item.get("owner_id") == player_id or item.get("killer_player_id") == player_id)
            ]
            next_snapshot = boundary
            bank_before = (last_qualified.get("minerals_current") or 0) + (last_qualified.get("vespene_current") or 0)
            bank_after = ((next_snapshot or {}).get("minerals_current") or 0) + ((next_snapshot or {}).get("vespene_current") or 0)
            bank_spent_after_active_fighting = bool(active_deaths and next_snapshot and bank_after <= bank_before - 300)
            episode = {
                "player_id": player_id,
                "start_loop": qualified[0]["game_loop"],
                "end_loop": (boundary or last_qualified)["game_loop"],
                "duration_loops": (boundary or last_qualified)["game_loop"] - qualified[0]["game_loop"],
                "peak_loop": peak_loop,
                "start_minerals": qualified[0].get("minerals_current") or 0,
                "start_gas": qualified[0].get("vespene_current") or 0,
                "peak_minerals": peak.get("minerals_current") or 0,
                "peak_gas": peak.get("vespene_current") or 0,
                "worker_count_at_start": qualified[0].get("workers_active_count"),
                "worker_count_at_peak": peak.get("workers_active_count"),
                "base_count_at_peak": len(completed_towns),
                "supply_at_start": {"used": qualified[0].get("food_used"), "available": qualified[0].get("food_made")},
                "supply_at_peak": {"used": peak.get("food_used"), "available": peak.get("food_made")},
                "available_production_capacity": composition.get("available_production_capacity"),
                "production_structures": composition.get("production_structures", {}),
                "available_larva": composition.get("available_larva") if player_races.get(player_id) == "Zerg" else None,
                "production_observation_reliable": composition.get("production_observation_reliable", False),
                "larva_observation_reliable": composition.get("larva_observation_reliable", False),
                "structures_at_peak": composition.get("structures", {}),
                "technology_resources_in_progress": tech_resources,
                "completed_upgrades_at_peak": [
                    item.get("upgrade") for item in timing.get("upgrades", [])
                    if item.get("player_id") == player_id and item.get("game_loop", 0) <= peak_loop
                ],
                "actively_fighting": bool(active_deaths),
                "active_fighting_event_count": len(active_deaths),
                "bank_spent_after_active_fighting": bank_spent_after_active_fighting,
                "bank_after_episode": bank_after if next_snapshot else None,
                "evidence": [item.get("evidence_id") for item in qualified if item.get("evidence_id")],
                "snapshot_evidence": [item.get("evidence_id") for item in qualified if item.get("evidence_id")],
                "interpretation_status": "candidate sustained resource float; queue state and intent are not fully observable",
            }
            episode["constraints"] = _float_constraints(episode, [item for item in supply_blocks if item.get("player_id") == player_id], player_races.get(player_id))
            episode["primary_constraint"] = episode["constraints"][0] if episode["constraints"] else "unknown"
            peak_supply = episode.get("supply_at_peak") or {}
            if (
                episode["primary_constraint"] == "supply_blocked"
                and "production_idle" in episode["constraints"]
                and peak_supply.get("used") is not None
                and peak_supply.get("available") is not None
                and float(peak_supply["available"]) - float(peak_supply["used"]) > 2
            ):
                episode["primary_constraint"] = "production_idle"
            episode["purchasing_power"] = _purchasing_power(episode, player_races.get(player_id), composition)
            episode["meaningful"] = bool(episode["duration_loops"] >= 160 or episode["peak_minerals"] >= 1200 or episode["peak_gas"] >= 800)
            episode["importance_reasons"] = [
                reason for reason, condition in (
                    ("large", episode["peak_minerals"] >= 1200 or episode["peak_gas"] >= 800),
                    ("sustained", episode["duration_loops"] >= 160),
                    ("repeated_snapshots", len(qualified) >= 2),
                    ("after_active_fighting", bool(active_deaths)),
                    ("after_worker_benchmark", bool(episode.get("worker_count_at_peak") and episode.get("base_count_at_peak") and episode["worker_count_at_peak"] >= episode["base_count_at_peak"] * 15)),
                ) if condition
            ]
            all_episodes.append(episode)
    return sorted(all_episodes, key=lambda item: (item["player_id"], item["start_loop"]))


def _economic_flags(snapshots: list[dict[str, Any]], compositions: list[dict[str, Any]], timing: dict[str, Any], deaths: list[dict[str, Any]], players: list[dict[str, Any]]) -> dict[str, Any]:
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
    return {
        "candidate_supply_blocks": supply_blocks,
        "candidate_resource_floats": floats,
        "float_episodes": _float_episodes(snapshots, compositions, timing, deaths, players, supply_blocks),
        "worker_count_plateaus": plateaus,
    }


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
    composition_snapshots = _composition_snapshots(snapshots, units, players)
    derivation = {
        "schema_version": extraction.get("schema_version"),
        "facts_version": FACTS_VERSION,
        "player_snapshots": snapshots,
        "worker_differentials": _worker_differentials(snapshots, players),
        "units": sorted(units.values(), key=lambda item: (item.get("init_loop") or item.get("birth_loop") or 0, item.get("unit_tag") or 0)),
        "deaths": deaths,
        "losses": _loss_aggregates(deaths, tracker_events, players),
        "composition_snapshots": composition_snapshots,
        "timing": timing,
        "economy": {
            **_economic_flags(snapshots, composition_snapshots, timing, deaths, players),
            "resource_collection_disruptions": _resource_collection_disruptions(snapshots),
        },
        "production": {
            "capacity_is_approximate": True,
            "note": "Production capacity is counted from active production structures in tracker state; queues and worker assignment are not fully observable.",
        },
        "evidence_policy": "Every item points to normalized tracker or snapshot evidence IDs; sparse positions are never interpolated.",
    }
    return derivation
