from pathlib import Path

import pytest

from sc2_replay_reviewer.errors import InvalidExtraction, PlayerResolutionError
from sc2_replay_reviewer.pipeline import load_or_extract
from sc2_replay_reviewer.player import resolve_player
from sc2_replay_reviewer.schema import validate_extraction
from sc2_replay_reviewer.version import PARSER_VERSION


def _valid(hash_value="abc"):
    return {
        "schema_version": "1.0",
        "replay_hash": hash_value,
        "parser": {"name": "s2protocol", "version": PARSER_VERSION},
        "metadata": {},
        "players": [{"player_id": 1, "name": "Danny"}, {"player_id": 2, "name": "Other"}],
        "tracker_events": [],
        "game_events": [],
        "message_events": [],
        "attributes": {},
    }


def test_player_identification_is_exact():
    extraction = {"players": [{"player_id": 1, "name": "Danny"}, {"player_id": 2, "name": "Other"}]}
    assert resolve_player(extraction, "Danny", None)["player_id"] == 1
    with pytest.raises(PlayerResolutionError):
        resolve_player(extraction, "danny", None)


def test_schema_separates_parser_facts_from_invalid_shape():
    validate_extraction(_valid())
    invalid = _valid()
    invalid["parser"]["name"] = "sc2reader"
    with pytest.raises(InvalidExtraction):
        validate_extraction(invalid)


def test_cached_extraction_is_reused(tmp_path, monkeypatch):
    replay = tmp_path / "game.SC2Replay"
    replay.write_bytes(b"not a real MPQ; hash is still stable")
    extraction = _valid()

    def first_parse(path: Path):
        import hashlib

        extraction["replay_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
        return extraction

    monkeypatch.setattr("sc2_replay_reviewer.pipeline.extract_replay", first_parse)
    first, reused = load_or_extract(replay, tmp_path)
    assert not reused
    assert first["replay_hash"] == extraction["replay_hash"]

    def should_not_parse(path):
        raise AssertionError("cache was not reused")

    monkeypatch.setattr("sc2_replay_reviewer.pipeline.extract_replay", should_not_parse)
    second, reused = load_or_extract(replay, tmp_path)
    assert reused
    assert second == first
