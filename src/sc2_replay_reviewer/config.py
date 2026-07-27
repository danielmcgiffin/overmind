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
class AppConfig:
    player: PlayerConfig = PlayerConfig()
    report: ReportConfig = ReportConfig()
    replays: ReplayConfig = ReplayConfig()


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
    )
