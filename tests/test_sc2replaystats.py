import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sc2_replay_reviewer.config import Sc2ReplayStatsConfig
from sc2_replay_reviewer.sc2replaystats import Sc2ReplayStatsClient, Sc2ReplayStatsError, pull_for_replay, upload_folder


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


def test_post_replay_uses_multipart_upload_contract(tmp_path: Path):
    replay = tmp_path / "game.SC2Replay"
    replay.write_bytes(b"replay-bytes")
    seen = {}

    def opener(request, timeout):
        seen["method"] = request.get_method()
        seen["authorization"] = request.get_header("Authorization")
        seen["content_type"] = request.get_header("Content-type")
        seen["body"] = request.data
        return _Response({"replay_queue_id": 77})

    client = Sc2ReplayStatsClient("https://api.example.test", "hash;token;123", opener=opener)
    result = client.post_replay(replay)

    assert result["queue_id"] == 77
    assert seen["method"] == "POST"
    assert seen["authorization"] == "hash;token;123"
    assert "multipart/form-data; boundary=" in seen["content_type"]
    assert b'name="replay_file"' in seen["body"]
    assert b'filename="game.SC2Replay"' in seen["body"]
    assert b'name="upload_method"' in seen["body"]
    assert b"standalone" in seen["body"]
    assert b"replay-bytes" in seen["body"]


def test_upload_folder_records_hash_and_skips_duplicate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TEST_SC2_STATS_AUTH", "hash;token;123")
    replay = tmp_path / "game.SC2Replay"
    replay.write_bytes(b"same replay")
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        return _Response({"replay_queue_id": 88})

    config = Sc2ReplayStatsConfig(base_url="https://api.example.test", auth_env="TEST_SC2_STATS_AUTH")
    first = upload_folder(tmp_path, tmp_path / "project", config, opener=opener)
    second = upload_folder(tmp_path, tmp_path / "project", config, opener=lambda *args, **kwargs: pytest.fail("duplicate upload"))

    assert first["status"] == "completed"
    assert first["counts"] == {"found": 1, "uploaded": 1, "skipped": 0, "failed": 0}
    assert second["counts"] == {"found": 1, "uploaded": 0, "skipped": 1, "failed": 0}
    assert len(calls) == 1
