from __future__ import annotations

from typing import Any

from .errors import PlayerResolutionError


def resolve_player(extraction: dict[str, Any], requested: str | None, configured: str | None) -> dict[str, Any]:
    players = extraction.get("players", [])
    names = [player.get("name") for player in players]
    target = requested if requested is not None else configured
    if target:
        matches = [player for player in players if player.get("name") == target]
        if len(matches) == 1:
            return matches[0]
        participants = ", ".join(name or "<unnamed>" for name in names) or "<none decoded>"
        if requested is not None:
            raise PlayerResolutionError(
                f"Player {requested!r} did not match exactly. Replay participants: {participants}"
            )
        # A default config name is not allowed to silently select the opponent.
        if len(players) == 1:
            return players[0]
        raise PlayerResolutionError(
            f"Configured player {target!r} did not match exactly. Replay participants: {participants}. "
            "Pass --player with an exact replay name or update config.toml."
        )
    if len(players) == 1:
        return players[0]
    participants = ", ".join(names) or "<none decoded>"
    raise PlayerResolutionError(
        f"Player is ambiguous. Replay participants: {participants}. Pass --player with an exact name."
    )
