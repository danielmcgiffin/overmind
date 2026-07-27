"""The single canonical SC2 game-loop/time conversion module."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

LOOPS_PER_GAME_SECOND = 16.0
SPEED_FACTORS: dict[str, float] = {
    "Slower": 0.6,
    "Slow": 0.8,
    "Normal": 1.0,
    "Fast": 1.2,
    "Faster": 1.4,
}
SPEED_ALIASES = {"Fastest": "Faster"}


def canonical_speed(label: str | None) -> str:
    """Return the official replay label, accepting common human aliases."""

    if not label:
        return "Faster"
    normalized = SPEED_ALIASES.get(label.strip(), label.strip())
    if normalized not in SPEED_FACTORS:
        raise ValueError(f"Unsupported SC2 game speed: {label!r}")
    return normalized


def loops_to_game_seconds(game_loops: float) -> float:
    """Convert game loops to the displayed SC2 game-clock seconds."""

    return float(game_loops) / LOOPS_PER_GAME_SECOND


def loops_to_real_seconds(game_loops: float, speed: str = "Faster") -> float:
    """Convert game loops to wall-clock seconds at the replay's speed."""

    factor = SPEED_FACTORS[canonical_speed(speed)]
    return float(game_loops) / (LOOPS_PER_GAME_SECOND * factor)


def game_seconds_to_real_seconds(game_seconds: float, speed: str = "Faster") -> float:
    return float(game_seconds) / SPEED_FACTORS[canonical_speed(speed)]


def _format_seconds(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    whole = int(seconds + 0.5)
    minutes, remainder = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remainder:02d}"
    return f"{minutes}:{remainder:02d}"


def format_game_time(game_loops: float) -> str:
    return _format_seconds(loops_to_game_seconds(game_loops))


def format_real_time(game_loops: float, speed: str = "Faster") -> str:
    return _format_seconds(loops_to_real_seconds(game_loops, speed))


def format_dual_time(game_loops: float, speed: str = "Faster") -> str:
    return f"{format_game_time(game_loops)} game / {format_real_time(game_loops, speed)} real"


def round_real_seconds(game_loops: float, speed: str = "Faster") -> float:
    """Stable, human-useful decimal for JSON summaries."""

    value = Decimal(str(loops_to_real_seconds(game_loops, speed)))
    return float(value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
