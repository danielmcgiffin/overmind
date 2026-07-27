"""Cache, derivation, timeline, and output orchestration."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig
from .derive import derive_facts
from .engagements import detect_engagements
from .parser import extract_replay
from .reports import render_evidence, render_report, render_review
from .review import build_diagnostic
from .schema import cache_is_usable, validate_extraction
from .serialization import read_json, sha256_file, write_json
from .time import format_real_time
from .version import ANALYSIS_RULE_VERSION, TOOL_VERSION


def _cache_path(root: Path, replay_hash: str) -> Path:
    return root / ".cache" / "sc2review" / replay_hash / "replay.json"


def load_or_extract(path: Path, root: Path) -> tuple[dict[str, Any], bool]:
    replay_hash = sha256_file(path)
    cache_path = _cache_path(root, replay_hash)
    if cache_path.exists():
        try:
            cached = read_json(cache_path)
            if cache_is_usable(cached, replay_hash):
                return cached, True
        except (OSError, ValueError):
            pass
    extraction = extract_replay(path)
    validate_extraction(extraction)
    write_json(cache_path, extraction)
    return extraction, False


def _player_name(extraction: dict[str, Any], player_id: int | None) -> str:
    for player in extraction.get("players", []):
        if player.get("player_id") == player_id:
            return player.get("name") or f"Player {player_id}"
    return f"Player {player_id}" if player_id is not None else "Unknown player"


def _timeline(extraction: dict[str, Any], derivation: dict[str, Any], engagements: list[dict[str, Any]], player_id: int) -> list[dict[str, Any]]:
    speed = extraction["metadata"]["game_speed"]
    rows: list[dict[str, Any]] = []

    def add(loop: int, kind: str, statement: str, evidence: list[str] | None = None, subject: int | None = None):
        rows.append(
            {
                "game_loop": loop,
                "real_time": format_real_time(loop, speed),
                "event_kind": kind,
                "player": _player_name(extraction, subject) if subject is not None else "",
                "factual_statement": statement,
                "evidence_refs": ";".join(str(item) for item in (evidence or []) if item),
            }
        )

    add(0, "game_start", "The replay begins. All timestamps use real elapsed time.")
    for expansion in derivation.get("timing", {}).get("expansions", []):
        add(expansion["game_loop"], "expansion", f"{_player_name(extraction, expansion.get('player_id'))} completed {expansion.get('unit_type')} (expansion #{expansion.get('expansion_number')}).", expansion.get("evidence"), expansion.get("player_id"))
    for upgrade in derivation.get("timing", {}).get("upgrades", []):
        add(upgrade["game_loop"], "upgrade", f"{_player_name(extraction, upgrade.get('player_id'))} completed {upgrade.get('upgrade')}.", upgrade.get("evidence"), upgrade.get("player_id"))
    high_value_units = {"SiegeTank", "SiegeTankSieged", "Thor", "Colossus", "Immortal", "Ultralisk"}
    for death in derivation.get("deaths", []):
        if death.get("killer_player_id") == player_id and death.get("unit_type") in high_value_units:
            add(
                death["game_loop"],
                "high_value_kill",
                f"{_player_name(extraction, player_id)} was credited with killing an opposing {death.get('unit_type')}.",
                [death.get("evidence_id")],
                player_id,
            )
    for death in derivation.get("losses", {}).get("worker_deaths", []):
        if death.get("owner_id") == player_id or death.get("killer_player_id") == player_id:
            add(death["game_loop"], "worker_event", f"{_player_name(extraction, death.get('owner_id'))} produced a raw worker-death event ({death.get('unit_type')}); builder-consumption classification is reported separately. Killer attribution: {_player_name(extraction, death.get('killer_player_id')) if death.get('killer_player_id') is not None else 'unavailable'}.", [death.get("evidence_id")], death.get("owner_id"))
    for block in derivation.get("economy", {}).get("candidate_supply_blocks", []):
        if block.get("player_id") == player_id:
            add(block["start_loop"], "supply_candidate", f"{_player_name(extraction, player_id)} was at or within 0.5 supply of the tracked cap until the next stats snapshot; this is a candidate supply block, not proof of a production pause.", block.get("evidence"), player_id)
    for engagement in engagements:
        if player_id in engagement.get("participants", []):
            losses = engagement.get("losses_by_player", {}).get(str(player_id), {})
            add(engagement["start_loop"], "engagement", f"Candidate engagement {engagement['engagement_id']} clustered {engagement['death_count']} deaths at map position {engagement.get('centroid')}; {_player_name(extraction, player_id)} losses: {losses.get('units', 0)} units.", engagement.get("evidence"), player_id)
    if extraction["metadata"].get("duration_loops"):
        add(extraction["metadata"]["duration_loops"], "game_end", "The replay ends.")
    return sorted(rows, key=lambda row: (row["game_loop"], row["event_kind"], row["factual_statement"]))


def timeline_csv(rows: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    fields = ["game_loop", "real_time", "event_kind", "player", "factual_statement", "evidence_refs"]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def analyze(path: Path, root: Path, player_id: int, config: AppConfig) -> dict[str, Any]:
    extraction, cache_reused = load_or_extract(path, root)
    derivation = derive_facts(extraction)
    engagements = detect_engagements(derivation)
    diagnosis = build_diagnostic(extraction, derivation, engagements, player_id)
    timeline = _timeline(extraction, derivation, engagements, player_id)
    replay_hash = extraction["replay_hash"]
    output_dir = root / "output" / replay_hash
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "replay.json", extraction)
    (output_dir / "timeline.csv").write_text(timeline_csv(timeline), encoding="utf-8")
    write_json(output_dir / "engagements.json", {"schema_version": extraction["schema_version"], "engagements": engagements})
    write_json(output_dir / "findings.json", diagnosis)
    (output_dir / "evidence.md").write_text(render_evidence(extraction, derivation, engagements, diagnosis, timeline, player_id, config), encoding="utf-8")
    (output_dir / "review.md").write_text(render_review(extraction, derivation, engagements, diagnosis, player_id, config), encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(extraction, derivation, engagements, diagnosis, timeline, player_id, config), encoding="utf-8")
    metadata = {
        "replay_hash": replay_hash,
        "tool_version": TOOL_VERSION,
        "schema_version": extraction["schema_version"],
        "parser_versions": extraction["parser"],
        "analysis_rule_version": ANALYSIS_RULE_VERSION,
        "date_analyzed": datetime.now(timezone.utc).isoformat(),
        "cached_extraction_reused": cache_reused,
        "primary_report_time": config.report.primary_time,
        "time_note": "All user-facing timestamps are real elapsed time calculated from game loops and the replay speed factor.",
    }
    write_json(output_dir / "run-metadata.json", metadata)
    return {
        "output_dir": output_dir,
        "replay_hash": replay_hash,
        "cache_reused": cache_reused,
        "extraction": extraction,
        "derivation": derivation,
        "engagements": engagements,
        "diagnosis": diagnosis,
        "timeline": timeline,
    }


def inspect(path: Path, root: Path) -> tuple[dict[str, Any], bool]:
    extraction, reused = load_or_extract(path, root)
    display_metadata = {
        key: value
        for key, value in extraction["metadata"].items()
        if key not in {"duration_game_seconds", "time_semantics"}
    }
    display_metadata["time_semantics"] = "user-facing timestamps use real elapsed seconds; canonical loop coordinates remain in raw extraction"
    return {
        "replay_hash": extraction["replay_hash"],
        "metadata": display_metadata,
        "players": extraction["players"],
        "event_counts": {
            "tracker": len(extraction.get("tracker_events", [])),
            "game": len(extraction.get("game_events", [])),
            "messages": len(extraction.get("message_events", [])),
        },
        "warnings": extraction.get("warnings", []),
        "cached_extraction_reused": reused,
    }, reused
