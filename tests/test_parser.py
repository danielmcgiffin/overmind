import pytest

from sc2_replay_reviewer.errors import UnsupportedReplayBuild
from sc2_replay_reviewer.parser import _event_short, _normalize_attribute_data, _normalize_players, _normalize_tracker_event, _protocol_for_build


def test_protocol_event_names_are_normalized():
    assert _event_short("NNet.Replay.Tracker.SUnitBornEvent") == "UnitBorn"
    assert _event_short("NNet.Game.SCmdEvent") == "Cmd"


def test_attribute_normalization_preserves_raw_and_decodes_speed():
    result = _normalize_attribute_data({"scopes": {16: {3000: [{"value": b"Fasr"}]}}})
    assert result["known"]["Game Speed"] == "Faster"
    assert result["records"][0]["raw_value"] == "Fasr"
    assert result["records"][0]["value"] == "Faster"


def test_player_metadata_parsing_and_mmr():
    details = {"m_playerList": [{"m_name": b"Danny", "m_race": {"m_race": b"Zerg"}, "m_teamId": 1, "m_result": 2, "m_toon": {"m_id": 3, "m_region": 1}}]}
    init = {"m_userInitialData": [{"m_name": b"Danny", "m_scaledRating": 4200}]}
    players = _normalize_players(details, init)
    assert players[0]["name"] == "Danny"
    assert players[0]["race"] == "Zerg"
    assert players[0]["mmr"] == 4200
    assert players[0]["result"] == "Loss"


def test_player_stats_supports_protocol_dict_shape():
    event = _normalize_tracker_event(
        {
            "_event": "NNet.Replay.Tracker.SPlayerStatsEvent",
            "_gameloop": 160,
            "m_playerId": 1,
            "m_stats": {
                "m_scoreValueWorkersActiveCount": 17,
                "m_scoreValueFoodUsed": 49152,
                "m_scoreValueFoodMade": 61440,
            },
        },
        0,
    )
    assert event["event_type"] == "PlayerStats"
    assert event["stats"]["workers_active_count"] == 17
    assert event["stats"]["food_used"] == 12
    assert event["stats"]["food_made"] == 15


def test_unsupported_build_is_explicit():
    with pytest.raises(UnsupportedReplayBuild):
        _protocol_for_build(999999)
