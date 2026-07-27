"""Spatial-temporal clustering of tracker deaths into candidate engagements."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from .derive import is_army

MAX_TIME_GAP_LOOPS = 128  # 8 displayed game seconds
MAX_CLUSTER_DISTANCE = 32.0  # map units; deliberately conservative
REINFORCEMENT_WINDOW_LOOPS = 160


def _point(death: dict[str, Any]) -> tuple[float, float] | None:
    position = death.get("position")
    if not isinstance(position, list) or len(position) != 2 or None in position:
        return None
    try:
        return float(position[0]), float(position[1])
    except (TypeError, ValueError):
        return None


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _centroid(deaths: list[dict[str, Any]]) -> tuple[float, float] | None:
    points = [point for death in deaths if (point := _point(death))]
    if not points:
        return None
    return sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points)


def _near_cluster(death: dict[str, Any], cluster: list[dict[str, Any]]) -> bool:
    point = _point(death)
    if point is None:
        return False
    cluster_points = [item_point for item in cluster if (item_point := _point(item))]
    if not cluster_points:
        return False
    centroid = _centroid(cluster)
    return any(_distance(point, item_point) <= MAX_CLUSTER_DISTANCE for item_point in cluster_points) or (
        centroid is not None and _distance(point, centroid) <= MAX_CLUSTER_DISTANCE
    )


def _pre_post_state(engagement: dict[str, Any], composition_snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    participants = set(engagement["participants"])
    state: dict[str, Any] = {"pre": {}, "post": {}}
    for player_id in participants:
        items = [item for item in composition_snapshots if item.get("player_id") == player_id]
        before = [item for item in items if item["game_loop"] <= engagement["start_loop"]]
        after = [item for item in items if item["game_loop"] >= engagement["end_loop"]]
        if before:
            state["pre"][str(player_id)] = before[-1]
        if after:
            state["post"][str(player_id)] = after[0]
    return state


def _reinforcements(engagement: dict[str, Any], derivation: dict[str, Any]) -> list[dict[str, Any]]:
    centroid = tuple(engagement["centroid"]) if engagement.get("centroid") else None
    if centroid is None:
        return []
    observations: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for unit in derivation.get("units", []):
        if not unit.get("positions") or not is_army(unit.get("unit_type")) or unit.get("owner_id") not in engagement["participants"] or not unit.get("unit_tag"):
            continue
        for observation in unit["positions"]:
            if not observation.get("position") or len(observation["position"]) != 2:
                continue
            point = tuple(observation["position"])
            if _distance(point, centroid) <= MAX_CLUSTER_DISTANCE:
                loop = observation.get("game_loop", 0)
                if engagement["start_loop"] <= loop <= engagement["end_loop"] + REINFORCEMENT_WINDOW_LOOPS:
                    observations[int(unit["unit_tag"])].append(
                        {
                            "unit_tag": unit["unit_tag"],
                            "unit_type": unit.get("unit_type"),
                            "owner_id": unit.get("owner_id"),
                            "game_loop": loop,
                            "evidence": [observation.get("evidence_id")],
                        }
                    )
    waves: list[dict[str, Any]] = []
    new_units = [items[0] for items in observations.values() if items]
    new_units.sort(key=lambda item: item["game_loop"])
    for item in new_units:
        if item["game_loop"] <= engagement["start_loop"]:
            continue
        if waves and item["game_loop"] - waves[-1]["start_loop"] <= 64 and item["owner_id"] == waves[-1]["player_id"]:
            waves[-1]["units"].append(item)
            waves[-1]["end_loop"] = max(waves[-1]["end_loop"], item["game_loop"])
            waves[-1]["evidence"].extend(item["evidence"])
        else:
            waves.append(
                {
                    "player_id": item["owner_id"],
                    "start_loop": item["game_loop"],
                    "end_loop": item["game_loop"],
                    "units": [item],
                    "evidence": list(item["evidence"]),
                    "confidence": "approximate: sparse damaged-unit positions do not prove movement path or intent",
                }
            )
    for wave in waves:
        wave["unit_count"] = len(wave["units"])
    return waves


def detect_engagements(derivation: dict[str, Any]) -> list[dict[str, Any]]:
    deaths = [
        death
        for death in derivation.get("deaths", [])
        if _point(death) is not None
        and death.get("owner_id") is not None
        and (death.get("is_army") or death.get("is_worker") or death.get("is_structure"))
    ]
    deaths.sort(key=lambda item: (item.get("game_loop", 0), item.get("evidence_id", "")))
    clusters: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    last_loop = None
    for death in deaths:
        loop = death.get("game_loop", 0)
        if not current or (loop - (last_loop or loop) <= MAX_TIME_GAP_LOOPS and _near_cluster(death, current)):
            current.append(death)
        else:
            clusters.append(current)
            current = [death]
        last_loop = loop
    if current:
        clusters.append(current)

    engagements = []
    for index, cluster in enumerate(clusters, start=1):
        participants = sorted({death.get("owner_id") for death in cluster if death.get("owner_id") is not None})
        if len(participants) < 2 or len(cluster) < 2:
            continue
        centroid = _centroid(cluster)
        losses = defaultdict(lambda: {"units": 0, "known_minerals": 0, "known_gas": 0, "unknown_units": 0, "workers": 0, "army_units": 0, "structures": 0})
        loss_types: dict[int, Counter[str]] = defaultdict(Counter)
        kills: dict[int, Counter[str]] = defaultdict(Counter)
        kill_value: dict[int, dict[str, int]] = defaultdict(lambda: {"minerals": 0, "gas": 0, "known_units": 0, "unknown_units": 0})
        for death in cluster:
            entry = losses[death["owner_id"]]
            entry["units"] += 1
            loss_types[death["owner_id"]][death.get("unit_type") or "Unknown"] += 1
            entry["workers"] += int(bool(death.get("is_worker")))
            entry["army_units"] += int(bool(death.get("is_army")))
            entry["structures"] += int(bool(death.get("is_structure")))
            if death["value"].get("known"):
                entry["known_minerals"] += death["value"].get("minerals") or 0
                entry["known_gas"] += death["value"].get("gas") or 0
            else:
                entry["unknown_units"] += 1
            killer = death.get("killer_player_id")
            if killer is not None:
                kills[int(killer)][death.get("unit_type") or "Unknown"] += 1
                if death["value"].get("known"):
                    kill_value[int(killer)]["minerals"] += death["value"].get("minerals") or 0
                    kill_value[int(killer)]["gas"] += death["value"].get("gas") or 0
                    kill_value[int(killer)]["known_units"] += 1
                else:
                    kill_value[int(killer)]["unknown_units"] += 1
        engagement = {
            "engagement_id": f"engagement:{index}",
            "start_loop": min(death["game_loop"] for death in cluster),
            "end_loop": max(death["game_loop"] for death in cluster),
            "centroid": list(centroid) if centroid else None,
            "participants": participants,
            "death_count": len(cluster),
            "losses_by_player": {str(player): value for player, value in sorted(losses.items())},
            "loss_types_by_player": {str(player): dict(sorted(counter.items())) for player, counter in sorted(loss_types.items())},
            "kills_by_player": {str(player): dict(sorted(counter.items())) for player, counter in sorted(kills.items())},
            "kill_value_by_player": {str(player): value for player, value in sorted(kill_value.items())},
            "evidence": [death.get("evidence_id") for death in cluster],
            "cluster_policy": {
                "max_time_gap_loops": MAX_TIME_GAP_LOOPS,
                "max_spatial_distance": MAX_CLUSTER_DISTANCE,
                "position_required": True,
            },
            "state": _pre_post_state(
                {
                    "start_loop": min(death["game_loop"] for death in cluster),
                    "end_loop": max(death["game_loop"] for death in cluster),
                    "participants": participants,
                },
                derivation.get("composition_snapshots", []),
            ),
        }
        engagement["reinforcement_waves"] = _reinforcements(engagement, derivation)
        engagements.append(engagement)
    return engagements
