from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .derive import derive_facts
from .engagements import detect_engagements
from .errors import ReplayReviewError
from .pipeline import analyze, inspect, load_or_extract, timeline_csv
from .player import resolve_player
from .schema import validate_extraction
from .serialization import write_json


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _path(value: str, replay_directory: Path | None = None) -> Path:
    requested = Path(value).expanduser()
    candidates = [requested]
    if replay_directory is not None and not requested.is_absolute():
        candidates.insert(0, replay_directory.expanduser() / requested)
    path = next((candidate.resolve() for candidate in candidates if candidate.exists()), candidates[0].resolve())
    if not path.exists():
        location_hint = f" (also checked configured replay directory: {replay_directory})" if replay_directory else ""
        raise ReplayReviewError(f"Replay path does not exist: {path}{location_hint}")
    if path.suffix.lower() != ".sc2replay":
        raise ReplayReviewError(f"Expected a .SC2Replay file: {path}")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sc2review", description="Causal StarCraft II replay review")
    sub = parser.add_subparsers(dest="command", required=True)
    bootstrap = sub.add_parser("bootstrap", help="Create or update the locked local environment")
    bootstrap.set_defaults(command="bootstrap")
    for command, help_text in {
        "analyze": "Extract, derive, and write the full review bundle",
        "inspect": "Show normalized replay metadata and event counts",
        "timeline": "Print the factual timeline as CSV",
        "engagements": "Print spatially clustered engagement facts as JSON",
        "validate": "Validate replay extraction and schema support",
    }.items():
        child = sub.add_parser(command, help=help_text)
        child.add_argument("replay", help="Path or filename of a .SC2Replay file; relative names use [replays].directory")
        if command in {"analyze", "timeline", "engagements"}:
            child.add_argument("--player", help="Exact replay participant name")
        child.add_argument("--config", type=Path, default=None, help="TOML config path (default: project config.toml)")
        child.add_argument("--replay-dir", type=Path, default=None, help="Override the configured replay directory")
        child.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "bootstrap":
        # The shell wrapper handles bootstrap before the venv exists. This path
        # is useful when called through `uv run sc2review bootstrap`.
        print("Run ./sc2review bootstrap from the project root.")
        return 0
    root = (args.root or _root()).resolve()
    config_path = (getattr(args, "config", None) or root / "config.toml").resolve()
    try:
        config = load_config(config_path)
        replay_path = _path(args.replay, args.replay_dir or config.replays.directory)
        if args.command == "inspect":
            result, _ = inspect(replay_path, root)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        extraction, cache_reused = load_or_extract(replay_path, root)
        validate_extraction(extraction)
        if args.command == "validate":
            print(json.dumps({"valid": True, "replay_hash": extraction["replay_hash"], "parser": extraction["parser"], "cached_extraction_reused": cache_reused}, indent=2, sort_keys=True))
            return 0
        derivation = derive_facts(extraction)
        engagements = detect_engagements(derivation)
        if args.command == "engagements":
            print(json.dumps({"replay_hash": extraction["replay_hash"], "engagements": engagements}, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "timeline":
            player = resolve_player(extraction, args.player, config.player.name)
            # Reuse the normal pipeline's timeline generation without writing
            # a second schema or parser implementation.
            from .pipeline import _timeline

            print(timeline_csv(_timeline(extraction, derivation, engagements, player["player_id"])), end="")
            return 0
        if args.command == "analyze":
            player = resolve_player(extraction, args.player, config.player.name)
            result = analyze(replay_path, root, player["player_id"], config)
            print(f"Analysis written to {result['output_dir']}")
            print(f"Replay hash: {result['replay_hash']}")
            print(f"Cached extraction reused: {result['cache_reused']}")
            return 0
    except ReplayReviewError as exc:
        print(f"sc2review: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as exc:
        print(f"sc2review: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
