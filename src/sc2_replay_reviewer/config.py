from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlayerConfig:
    name: str = ""
    preferred_race: str | None = None


@dataclass(frozen=True)
class ReportConfig:
    primary_time: str = "real"
    show_real_time: bool = False
    tone: str = "direct"


@dataclass(frozen=True)
class ReplayConfig:
    """User-local replay lookup settings; never populated with a bundled replay."""

    directory: Path | None = None


@dataclass(frozen=True)
class Sc2ReplayStatsConfig:
    """Optional read-only enrichment from the user's Sc2ReplayStats account."""

    enabled: bool = True
    base_url: str = "https://api.sc2replaystats.com"
    auth_env: str = "SC2REPLAYSTATS_AUTH"
    cache_ttl_seconds: int = 900


@dataclass(frozen=True)
class AppConfig:
    player: PlayerConfig = PlayerConfig()
    report: ReportConfig = ReportConfig()
    replays: ReplayConfig = ReplayConfig()
    sc2replaystats: Sc2ReplayStatsConfig = Sc2ReplayStatsConfig()


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        return AppConfig()
    try:
        import tomllib

        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unable to read config {path}: {exc}") from exc
    player = raw.get("player", {})
    report = raw.get("report", {})
    replays = raw.get("replays", {})
    sc2replaystats = raw.get("sc2replaystats", {})
    replay_directory = replays.get("directory")
    directory = None
    if replay_directory:
        directory = Path(str(replay_directory)).expanduser()
        if not directory.is_absolute():
            directory = (path.parent / directory).resolve()
    return AppConfig(
        player=PlayerConfig(
            name=str(player.get("name", "")),
            preferred_race=player.get("preferred_race"),
        ),
        report=ReportConfig(
            primary_time=str(report.get("primary_time", "real")),
            show_real_time=bool(report.get("show_real_time", False)),
            tone=str(report.get("tone", "direct")),
        ),
        replays=ReplayConfig(directory=directory),
        sc2replaystats=Sc2ReplayStatsConfig(
            enabled=bool(sc2replaystats.get("enabled", True)),
            base_url=str(sc2replaystats.get("base_url", "https://api.sc2replaystats.com")).rstrip("/"),
            auth_env=str(sc2replaystats.get("auth_env", "SC2REPLAYSTATS_AUTH")),
            cache_ttl_seconds=max(0, int(sc2replaystats.get("cache_ttl_seconds", 900))),
        ),
    )
