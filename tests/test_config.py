from pathlib import Path

from sc2_replay_reviewer.cli import _path
from sc2_replay_reviewer.config import load_config


def test_configured_replay_directory_resolves_relative_filenames(tmp_path: Path):
    replay_dir = tmp_path / "Replays" / "Multiplayer"
    replay_dir.mkdir(parents=True)
    replay = replay_dir / "match.SC2Replay"
    replay.write_bytes(b"fixture")
    config_path = tmp_path / "config.toml"
    config_path.write_text('[replays]\ndirectory = "Replays/Multiplayer"\n', encoding="utf-8")

    config = load_config(config_path)

    assert config.replays.directory == replay_dir.resolve()
    assert _path("match.SC2Replay", config.replays.directory) == replay.resolve()


def test_explicit_replay_path_takes_precedence_over_configured_directory(tmp_path: Path):
    configured = tmp_path / "configured"
    explicit = tmp_path / "explicit.SC2Replay"
    configured.mkdir()
    explicit.write_bytes(b"fixture")

    assert _path(str(explicit), configured) == explicit.resolve()


def test_sc2replaystats_config_uses_environment_secret_name(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[sc2replaystats]\nenabled = true\nauth_env = \"MY_SC2_STATS_KEY\"\ncache_ttl_seconds = 60\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.sc2replaystats.enabled is True
    assert config.sc2replaystats.auth_env == "MY_SC2_STATS_KEY"
    assert config.sc2replaystats.cache_ttl_seconds == 60
