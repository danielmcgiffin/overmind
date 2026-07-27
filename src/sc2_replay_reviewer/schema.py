from __future__ import annotations

from typing import Any

from .errors import InvalidExtraction
from .version import PARSER_VERSION, SCHEMA_VERSION


REQUIRED_EXTRACTION_KEYS = {
    "schema_version",
    "parser",
    "replay_hash",
    "metadata",
    "players",
    "tracker_events",
    "game_events",
    "message_events",
    "attributes",
}


def validate_extraction(extraction: dict[str, Any]) -> None:
    missing = REQUIRED_EXTRACTION_KEYS - set(extraction)
    if missing:
        raise InvalidExtraction(f"Extraction is missing keys: {sorted(missing)}")
    if extraction.get("schema_version") != SCHEMA_VERSION:
        raise InvalidExtraction(
            f"Unsupported extraction schema: {extraction.get('schema_version')!r}"
        )
    parser = extraction.get("parser", {})
    if parser.get("name") != "s2protocol":
        raise InvalidExtraction("Extraction does not identify s2protocol as decoder")
    if not extraction.get("replay_hash"):
        raise InvalidExtraction("Extraction has no replay content hash")
    if not isinstance(extraction.get("players"), list):
        raise InvalidExtraction("Extraction players must be a list")


def cache_is_usable(extraction: dict[str, Any], replay_hash: str) -> bool:
    try:
        validate_extraction(extraction)
    except InvalidExtraction:
        return False
    return (
        extraction.get("replay_hash") == replay_hash
        and extraction.get("parser", {}).get("version") == PARSER_VERSION
    )
