"""Low-level replay extraction using Blizzard's s2protocol."""

from __future__ import annotations

import importlib
import importlib.metadata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import mpyq

from .compat import install_s2protocol_compat
from .errors import ReplayReviewError, UnsupportedReplayBuild
from .serialization import json_safe, sha256_file
from .time import SPEED_FACTORS, canonical_speed, loops_to_real_seconds
from .version import PARSER_VERSION, SCHEMA_VERSION

install_s2protocol_compat()

from s2protocol import versions  # noqa: E402


STAT_FIELDS = [
    "minerals_current",
    "vespene_current",
    "minerals_collection_rate",
    "vespene_collection_rate",
    "workers_active_count",
    "minerals_used_in_progress_army",
    "minerals_used_in_progress_economy",
    "minerals_used_in_progress_technology",
    "vespene_used_in_progress_army",
    "vespene_used_in_progress_economy",
    "vespene_used_in_progress_technology",
    "minerals_used_current_army",
    "minerals_used_current_economy",
    "minerals_used_current_technology",
    "vespene_used_current_army",
    "vespene_used_current_economy",
    "vespene_used_current_technology",
    "minerals_lost_army",
    "minerals_lost_economy",
    "minerals_lost_technology",
    "vespene_lost_army",
    "vespene_lost_economy",
    "vespene_lost_technology",
    "minerals_killed_army",
    "minerals_killed_economy",
    "minerals_killed_technology",
    "vespene_killed_army",
    "vespene_killed_economy",
    "vespene_killed_technology",
    "food_used_raw",
    "food_made_raw",
    "minerals_used_active_forces",
    "vespene_used_active_forces",
    "minerals_friendly_fire_army",
    "minerals_friendly_fire_economy",
    "minerals_friendly_fire_technology",
    "vespene_friendly_fire_army",
    "vespene_friendly_fire_economy",
    "vespene_friendly_fire_technology",
]

STAT_PROTOCOL_FIELDS = [
    "m_scoreValueMineralsCurrent",
    "m_scoreValueVespeneCurrent",
    "m_scoreValueMineralsCollectionRate",
    "m_scoreValueVespeneCollectionRate",
    "m_scoreValueWorkersActiveCount",
    "m_scoreValueMineralsUsedInProgressArmy",
    "m_scoreValueMineralsUsedInProgressEconomy",
    "m_scoreValueMineralsUsedInProgressTechnology",
    "m_scoreValueVespeneUsedInProgressArmy",
    "m_scoreValueVespeneUsedInProgressEconomy",
    "m_scoreValueVespeneUsedInProgressTechnology",
    "m_scoreValueMineralsUsedCurrentArmy",
    "m_scoreValueMineralsUsedCurrentEconomy",
    "m_scoreValueMineralsUsedCurrentTechnology",
    "m_scoreValueVespeneUsedCurrentArmy",
    "m_scoreValueVespeneUsedCurrentEconomy",
    "m_scoreValueVespeneUsedCurrentTechnology",
    "m_scoreValueMineralsLostArmy",
    "m_scoreValueMineralsLostEconomy",
    "m_scoreValueMineralsLostTechnology",
    "m_scoreValueVespeneLostArmy",
    "m_scoreValueVespeneLostEconomy",
    "m_scoreValueVespeneLostTechnology",
    "m_scoreValueMineralsKilledArmy",
    "m_scoreValueMineralsKilledEconomy",
    "m_scoreValueMineralsKilledTechnology",
    "m_scoreValueVespeneKilledArmy",
    "m_scoreValueVespeneKilledEconomy",
    "m_scoreValueVespeneKilledTechnology",
    "m_scoreValueFoodUsed",
    "m_scoreValueFoodMade",
    "m_scoreValueMineralsUsedActiveForces",
    "m_scoreValueVespeneUsedActiveForces",
    "m_scoreValueMineralsFriendlyFireArmy",
    "m_scoreValueMineralsFriendlyFireEconomy",
    "m_scoreValueMineralsFriendlyFireTechnology",
    "m_scoreValueVespeneFriendlyFireArmy",
    "m_scoreValueVespeneFriendlyFireEconomy",
    "m_scoreValueVespeneFriendlyFireTechnology",
]

ATTR_NAMES = {
    0x0BB8: "Game Speed",
    0x07D0: "Teams",
    0x07D1: "Teams Detail",
    0x0BC1: "Game Mode",
}
ATTR_VALUES = {
    "Game Speed": {
        "Fasr": "Faster",
        "Fast": "Fast",
        "Norm": "Normal",
        "Slor": "Slower",
        "Slow": "Slow",
    },
    "Teams": {
        "1v1": "1v1",
        "2v2": "2v2",
        "3v3": "3v3",
        "4v4": "4v4",
        "FFA": "FFA",
    },
}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = json_safe(value)
    if isinstance(value, dict) and set(value) == {"encoding", "value"}:
        return str(value["value"])
    return str(value)


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and len(value) == 1:
        return next(iter(value.values()))
    return value


def _int(value: Any) -> int | None:
    value = _unwrap(value)
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _tag(index: Any, recycle: Any) -> int | None:
    index_value, recycle_value = _int(index), _int(recycle)
    if index_value is None or recycle_value is None:
        return None
    return (index_value << 18) | recycle_value


def _event_short(name: str | None) -> str:
    short = (name or "Unknown").rsplit(".", 1)[-1].removesuffix("Event")
    return short.removeprefix("S")


def _protocol_for_build(base_build: int):
    module_name = f"protocol{base_build:05d}"
    available = {name.removesuffix(".py") for name in versions.list_all()}
    if module_name not in available:
        lower = sorted(
            (int(name.removeprefix("protocol")) for name in available),
            reverse=True,
        )
        compatible = next((item for item in lower if item <= base_build), None)
        if compatible is None or base_build > max(lower):
            nearest = ", ".join(str(item) for item in lower[:8])
            raise UnsupportedReplayBuild(
                f"Replay base build {base_build} is not supported by bundled s2protocol "
                f"{PARSER_VERSION}. Supported recent protocol builds: {nearest}. "
                "Install a newer pinned s2protocol release and update PROJECT_STATE.md."
            )
        module_name = f"protocol{compatible:05d}"
        return (
            importlib.import_module(f"s2protocol.versions.{module_name}"),
            module_name,
            f"compatible-lower-protocol:{compatible}",
        )
    return importlib.import_module(f"s2protocol.versions.{module_name}"), module_name, "exact"


def _bootstrap_header(content: bytes) -> dict[str, Any]:
    """Decode the MPQ user-data header before the exact build is known."""

    # The SHeader layout has been stable in the generated protocol modules. Try
    # s2protocol first; sc2reader is only a compatibility fallback for old
    # header encodings and is never used for event extraction.
    candidates = []
    try:
        candidates.append(versions.latest())
    except Exception:
        pass
    for protocol in candidates:
        try:
            header = protocol.decode_replay_header(content)
            if isinstance(header, dict) and isinstance(header.get("m_version"), dict):
                return header
        except Exception:
            continue

    try:
        from sc2reader.decoders import BitPackedDecoder

        decoded = BitPackedDecoder(content).read_struct()
        version_values = list(decoded[1].values())
        return {
            "m_version": {
                "m_major": version_values[0],
                "m_minor": version_values[1],
                "m_revision": version_values[2],
                "m_build": version_values[3],
                "m_baseBuild": version_values[4],
            },
            "m_elapsedGameLoops": decoded[3],
            "_header_decoder": "sc2reader compatibility fallback",
        }
    except Exception as exc:
        raise ReplayReviewError(f"Unable to decode replay header: {exc}") from exc


def _read_optional(archive: mpyq.MPQArchive, names: Iterable[str]) -> bytes | None:
    for name in names:
        try:
            return archive.read_file(name)
        except Exception:
            continue
    return None


def _decode_optional(protocol, archive: mpyq.MPQArchive, names: list[str], decoder_name: str, warnings: list[str]):
    content = _read_optional(archive, names)
    if content is None:
        warnings.append(f"Missing replay stream: {names[0]}")
        return None
    try:
        decoder = getattr(protocol, decoder_name)
        result = decoder(content)
        return result if isinstance(result, dict) else list(result)
    except Exception as exc:
        warnings.append(f"Could not decode {names[0]}: {type(exc).__name__}: {exc}")
        return None


def _normalize_attribute_data(attributes: dict[str, Any] | None) -> dict[str, Any]:
    result: list[dict[str, Any]] = []
    known: dict[str, Any] = {}
    if not attributes:
        return {"records": result, "known": known}
    for scope, scoped in attributes.get("scopes", {}).items():
        for attr_id, values in scoped.items():
            name = ATTR_NAMES.get(int(attr_id), f"attr_{attr_id}")
            for occurrence, value in enumerate(values):
                raw_value = _text(value.get("value"))
                decoded_value = ATTR_VALUES.get(name, {}).get(raw_value, raw_value)
                record = {
                    "scope": int(scope),
                    "attribute_id": int(attr_id),
                    "name": name,
                    "raw_value": raw_value,
                    "value": decoded_value,
                    "occurrence": occurrence,
                }
                result.append(record)
                if int(scope) == 16:
                    known[name] = decoded_value
    return {"records": result, "known": known, "source": json_safe(attributes)}


def _normalize_players(details: dict[str, Any] | None, initdata: dict[str, Any] | None) -> list[dict[str, Any]]:
    details_players = (details or {}).get("m_playerList") or []
    initial_players = (initdata or {}).get("m_userInitialData") or []
    initial_by_name = {_text(item.get("m_name")): item for item in initial_players}
    players: list[dict[str, Any]] = []
    for index, item in enumerate(details_players, start=1):
        name = _text(item.get("m_name")) or f"Player {index}"
        race = _unwrap(item.get("m_race"))
        toon = item.get("m_toon") or {}
        init = initial_by_name.get(name, {})
        scaled_rating = _int(init.get("m_scaledRating"))
        result_value = _int(item.get("m_result"))
        players.append(
            {
                "player_id": index,
                "name": name,
                "race": _text(race),
                "team_id": _int(item.get("m_teamId")),
                "result_raw": result_value,
                "result": {1: "Win", 2: "Loss"}.get(result_value),
                "user_id": _int(toon.get("m_id")),
                "region": _int(toon.get("m_region")),
                "mmr": scaled_rating,
                "apm": None,
                "data_availability": {
                    "mmr": "lobby scaled rating" if scaled_rating is not None else "unavailable",
                    "apm": "unavailable in decoded replay streams",
                },
            }
        )
    return players


def _normalize_tracker_event(event: dict[str, Any], index: int) -> dict[str, Any]:
    event_type = _event_short(_text(event.get("_event")))
    payload = {key: json_safe(value) for key, value in event.items() if not key.startswith("_")}
    loop = _int(event.get("_gameloop")) or 0
    player_id = None
    unit_tag = _tag(event.get("m_unitTagIndex"), event.get("m_unitTagRecycle"))
    if event_type in {"PlayerStats", "Upgrade"}:
        player_id = _int(event.get("m_playerId"))
    elif event_type in {"UnitBorn", "UnitInit"}:
        player_id = _int(event.get("m_upkeepPlayerId"))
    elif event_type == "UnitOwnerChange":
        player_id = _int(event.get("m_upkeepPlayerId"))
    elif event_type == "PlayerSetup":
        player_id = _int(event.get("m_playerId"))
    normalized: dict[str, Any] = {
        "evidence_id": f"tracker:{index}",
        "source": "s2protocol.tracker",
        "event_type": event_type,
        "event_name": _text(event.get("_event")),
        "game_loop": loop,
        "player_id": player_id,
        "unit_tag": unit_tag,
        "payload": payload,
    }
    if event_type in {"UnitBorn", "UnitInit"}:
        normalized.update(
            {
                "unit_type": _text(event.get("m_unitTypeName")),
                "owner_id": _int(event.get("m_upkeepPlayerId")),
                "control_id": _int(event.get("m_controlPlayerId")),
                "position": [_int(event.get("m_x")), _int(event.get("m_y"))],
                "creator_ability": _text(event.get("m_creatorAbilityName")),
            }
        )
    elif event_type == "UnitDied":
        normalized.update(
            {
                "killer_player_id": _int(event.get("m_killerPlayerId")),
                "killer_unit_tag": _tag(event.get("m_killerUnitTagIndex"), event.get("m_killerUnitTagRecycle")),
                "position": [_int(event.get("m_x")), _int(event.get("m_y"))],
            }
        )
    elif event_type == "UnitOwnerChange":
        normalized.update(
            {
                "owner_id": _int(event.get("m_upkeepPlayerId")),
                "control_id": _int(event.get("m_controlPlayerId")),
            }
        )
    elif event_type == "UnitTypeChange":
        normalized["unit_type"] = _text(event.get("m_unitTypeName"))
    elif event_type == "Upgrade":
        normalized.update(
            {"upgrade": _text(event.get("m_upgradeTypeName")), "count": _int(event.get("m_count"))}
        )
    elif event_type == "PlayerStats":
        values = event.get("m_stats") or []
        if isinstance(values, dict):
            values = [values.get(name) for name in STAT_PROTOCOL_FIELDS]
        stats = {
            name: (float(value) / 4096.0 if name in {"food_used_raw", "food_made_raw"} else _int(value))
            for name, value in zip(STAT_FIELDS, values)
        }
        stats["food_used"] = stats.pop("food_used_raw", None)
        stats["food_made"] = stats.pop("food_made_raw", None)
        normalized["stats"] = stats
    elif event_type == "UnitPositions":
        items = event.get("m_items") or []
        first = _int(event.get("m_firstUnitIndex")) or 0
        positions = []
        unit_index = first
        for offset in range(0, len(items) - 2, 3):
            unit_index += _int(items[offset]) or 0
            positions.append(
                {
                    "unit_index": unit_index,
                    "position": [_int(items[offset + 1]), _int(items[offset + 2])],
                }
            )
        normalized["positions"] = positions
    return normalized


def _normalize_game_event(event: dict[str, Any], index: int, stream: str) -> dict[str, Any]:
    event_type = _event_short(_text(event.get("_event")))
    payload = {key: json_safe(value) for key, value in event.items() if not key.startswith("_")}
    result = {
        "evidence_id": f"{stream}:{index}",
        "source": f"s2protocol.{stream}",
        "event_type": event_type,
        "event_name": _text(event.get("_event")),
        "game_loop": _int(event.get("_gameloop")) or 0,
        "actor_user_id": _int(event.get("_userid")),
        "payload": payload,
    }
    if event_type == "Cmd":
        ability = event.get("m_abil") or {}
        result["ability"] = {
            "link": _int(ability.get("m_abilLink")),
            "command_index": _int(ability.get("m_abilCmdIndex")),
        }
        result["target"] = json_safe(event.get("m_data"))
    return result


def _timestamp(value: Any) -> datetime | None:
    number = _int(value)
    if number is None:
        return None
    if number > 10**15:  # Windows FILETIME, as used by replay.details
        seconds = (number - 116444736000000000) / 10**7
    else:
        seconds = number
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def extract_replay(path: Path) -> dict[str, Any]:
    replay_hash = sha256_file(path)
    warnings: list[str] = []
    try:
        archive = mpyq.MPQArchive(path, listfile=False)
    except Exception as exc:
        raise ReplayReviewError(f"Unable to open replay MPQ: {exc}") from exc

    header_content = archive.header.get("user_data_header", {}).get("content")
    if not header_content:
        raise ReplayReviewError("Replay has no MPQ user-data header")
    header = _bootstrap_header(header_content)
    version = header.get("m_version") or {}
    base_build = _int(version.get("m_baseBuild"))
    if base_build is None:
        raise ReplayReviewError("Replay header has no base build")
    protocol, protocol_module, protocol_selection = _protocol_for_build(base_build)

    details = _decode_optional(protocol, archive, ["replay.details", "replay.details.backup"], "decode_replay_details", warnings)
    initdata = _decode_optional(protocol, archive, ["replay.initData", "replay.initData.backup"], "decode_replay_initdata", warnings)
    attributes = _decode_optional(protocol, archive, ["replay.attributes.events"], "decode_replay_attributes_events", warnings)
    tracker = _decode_optional(protocol, archive, ["replay.tracker.events"], "decode_replay_tracker_events", warnings) or []
    game = _decode_optional(protocol, archive, ["replay.game.events"], "decode_replay_game_events", warnings) or []
    messages = _decode_optional(protocol, archive, ["replay.message.events"], "decode_replay_message_events", warnings) or []

    normalized_attributes = _normalize_attribute_data(attributes)
    speed = normalized_attributes["known"].get("Game Speed")
    if speed not in SPEED_FACTORS:
        # m_gameSpeed is a fallback enum from initData. Its canonical labels
        # are not reliable across all old builds, so preserve the ambiguity.
        warnings.append("Game speed attribute unavailable; defaulted to Faster")
        speed = "Faster"
    speed = canonical_speed(speed)
    duration_loops = _int(header.get("m_elapsedGameLoops")) or 0
    end_time = _timestamp((details or {}).get("m_timeUTC"))
    start_time = None
    if end_time is not None:
        start_time = end_time - timedelta(seconds=loops_to_real_seconds(duration_loops, speed))
    players = _normalize_players(details, initdata)
    normalized_tracker = [_normalize_tracker_event(event, index) for index, event in enumerate(tracker)]
    normalized_game = [_normalize_game_event(event, index, "game") for index, event in enumerate(game)]
    normalized_messages = [_normalize_game_event(event, index, "message") for index, event in enumerate(messages)]

    map_name = _text((details or {}).get("m_title")) or _text((details or {}).get("m_mapFileName"))
    metadata = {
        "base_build": base_build,
        "build": _int(version.get("m_build")),
        "release": ".".join(str(_int(version.get(key)) or 0) for key in ("m_major", "m_minor", "m_revision", "m_build")),
        "protocol_module": protocol_module,
        "protocol_selection": protocol_selection,
        "map": map_name,
        "game_speed": speed,
        "game_mode": normalized_attributes["known"].get("Game Mode"),
        "teams": normalized_attributes["known"].get("Teams"),
        "duration_loops": duration_loops,
        "duration_game_seconds": duration_loops / 16.0,
        "duration_real_seconds": loops_to_real_seconds(duration_loops, speed),
        "start_time_utc": start_time.isoformat() if start_time else None,
        "end_time_utc": end_time.isoformat() if end_time else None,
        "time_semantics": "canonical loop coordinates are retained internally; user-facing timestamps use real elapsed seconds from the replay speed factor",
    }
    extraction = {
        "schema_version": SCHEMA_VERSION,
        "replay_hash": replay_hash,
        "parser": {
            "name": "s2protocol",
            "version": PARSER_VERSION,
            "protocol_module": protocol_module,
            "s2protocol_version": importlib.metadata.version("s2protocol"),
            "sc2reader_version": importlib.metadata.version("sc2reader"),
            "header_fallback": header.get("_header_decoder"),
        },
        "metadata": metadata,
        "players": players,
        "attributes": normalized_attributes,
        "tracker_events": normalized_tracker,
        "game_events": normalized_game,
        "message_events": normalized_messages,
        "warnings": warnings,
        "availability": {
            "mmr": any(player.get("mmr") is not None for player in players),
            "apm": False,
            "player_stats": any(event["event_type"] == "PlayerStats" for event in normalized_tracker),
            "tracker_events": bool(normalized_tracker),
            "positions": any(event["event_type"] == "UnitPositions" for event in normalized_tracker),
            "full_combat_simulation": False,
        },
    }
    return extraction
