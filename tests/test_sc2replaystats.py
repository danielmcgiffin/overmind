import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sc2_replay_reviewer.config import Sc2ReplayStatsConfig
from sc2_replay_reviewer.sc2replaystats import Sc2ReplayStatsClient, Sc2ReplayStatsError, pull_for_replay


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


def _extraction():
    return {
        "replay_hash": "abc123",
        "metadata": {"map": "Test Map"},
        "players": [{"name": "Danny"}, {"name": "Opponent"}],
    }


def test_client_sends_exact_authorization_header():
    seen = {}

    def opener(request, timeout):
        seen["authorization"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return _Response({"ok": True})

    client = Sc2ReplayStatsClient("https://api.example.test", "hash;token;123", opener=opener)

    assert client.get("/account/last-replay") == {"ok": True}
    assert seen == {"authorization": "hash;token;123", "timeout": 15.0}


def test_pull_caches_remote_payload_and_reuses_it(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TEST_SC2_STATS_AUTH", "hash;token;123")
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        if request.full_url.endswith("/account/last-replay"):
            return _Response({"id": 42, "map": "Test Map", "players": [{"name": "Danny"}, {"name": "Opponent"}]})
        return _Response({"id": 42, "spending_quotient": 111})

    config = Sc2ReplayStatsConfig(base_url="https://api.example.test", auth_env="TEST_SC2_STATS_AUTH", cache_ttl_seconds=900)
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    first = pull_for_replay(_extraction(), tmp_path, config, opener=opener, now=now)

    def should_not_call(*args, **kwargs):
        raise AssertionError("fresh external cache was not reused")

    second = pull_for_replay(_extraction(), tmp_path, config, opener=should_not_call, now=now)

    assert first["status"] == "matched_metadata"
    assert first["cache_reused"] is False
    assert second["cache_reused"] is True
    assert second["remote"]["replay"]["spending_quotient"] == 111
    assert len(calls) == 2


def test_missing_secret_is_non_fatal_and_does_not_call_network(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TEST_SC2_STATS_AUTH", raising=False)
    config = Sc2ReplayStatsConfig(auth_env="TEST_SC2_STATS_AUTH")

    result = pull_for_replay(_extraction(), tmp_path, config, opener=lambda *args, **kwargs: pytest.fail("network called"))

    assert result["status"] == "not_configured"
    assert "TEST_SC2_STATS_AUTH" in result["message"]


def test_invalid_authorization_shape_is_safe_error():
    with pytest.raises(Sc2ReplayStatsError, match="three semicolon-separated"):
        Sc2ReplayStatsClient("https://api.example.test", "not-a-token")
