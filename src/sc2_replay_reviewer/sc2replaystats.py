"""Sc2ReplayStats pull and upload integration with secret-safe local caching.

The local s2protocol extraction remains authoritative. This module stores the
remote response as supplemental external data and never merges it into the
normalized replay facts or coaching inferences.
"""

from __future__ import annotations

import html
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import Sc2ReplayStatsConfig
from .serialization import read_json, sha256_file, write_json


EXTERNAL_SCHEMA_VERSION = "1.0"
SOURCE_NAME = "sc2replaystats"
UPLOAD_STATE_SCHEMA_VERSION = "1.0"
DEFAULT_LAST_REPLAY_PATH = "/account/last-replay"
DEFAULT_UPLOAD_PATH = "/replay"
DEFAULT_REPLAY_INCLUDES = ("players", "account", "players-replay-info", "map")


class Sc2ReplayStatsError(Exception):
    """A safe-to-display API error that never contains the authorization key."""


def _cache_path(root: Path, replay_hash: str) -> Path:
    return root / ".cache" / SOURCE_NAME / replay_hash / "sc2replaystats.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normal_text(value: Any) -> str:
    return " ".join(html.unescape(str(value)).replace("<sp/>", " ").split()).casefold()


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _first_identifier(value: Any) -> str | int | None:
    identifier_keys = {"id", "replay_id", "replays_id", "replayid"}
    for item in _walk(value):
        for key, candidate in item.items():
            if key.casefold() in identifier_keys and isinstance(candidate, (str, int)):
                return candidate
    return None


def _payload_text(value: Any) -> str:
    return _normal_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _match_local_replay(extraction: dict[str, Any], remote: Any) -> dict[str, Any]:
    """Classify how confidently the remote last replay matches this local file."""

    local_hash = _normal_text(extraction.get("replay_hash", ""))
    text = _payload_text(remote)
    hash_keys = {"hash", "replay_hash", "replayhash", "md5", "file_hash", "replay_md5"}
    remote_hashes = {
        _normal_text(candidate)
        for item in _walk(remote)
        for key, candidate in item.items()
        if key.casefold() in hash_keys and isinstance(candidate, (str, int))
    }
    if local_hash and local_hash in remote_hashes:
        return {"status": "matched_hash", "confidence": "high"}

    metadata = extraction.get("metadata", {})
    map_name = _normal_text(metadata.get("map", ""))
    map_match = bool(map_name and map_name in text)
    local_names = [
        _normal_text(player.get("name"))
        for player in extraction.get("players", [])
        if player.get("name")
    ]
    name_matches = sum(bool(name and name in text) for name in local_names)
    if map_match and name_matches == len(local_names) and local_names:
        return {"status": "matched_metadata", "confidence": "medium", "name_matches": name_matches}
    if map_match or name_matches:
        return {"status": "possible_metadata_match", "confidence": "low", "name_matches": name_matches}
    return {"status": "latest_remote_unverified", "confidence": "none", "name_matches": 0}


class Sc2ReplayStatsClient:
    """Small stdlib client for the documented Sc2ReplayStats JSON API."""

    def __init__(
        self,
        base_url: str,
        authorization: str,
        timeout_seconds: float = 15.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.authorization = authorization
        self.timeout_seconds = timeout_seconds
        self.opener = opener
        if not self.base_url.startswith("https://"):
            raise Sc2ReplayStatsError("Sc2ReplayStats base_url must use HTTPS")
        if len(self.authorization.split(";")) != 3:
            raise Sc2ReplayStatsError("Sc2ReplayStats authorization must contain three semicolon-separated fields")

    def get(self, path: str, params: dict[str, str] | None = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{self.base_url}/{path.lstrip('/')}{query}",
            headers={
                "Accept": "application/json",
                "Authorization": self.authorization,
                "User-Agent": "sc2-replay-reviewer/0.3.0",
            },
            method="GET",
        )
        return self._request_json(request)

    def _request_json(self, request: Request) -> Any:
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                body = response.read()
        except HTTPError as exc:
            raise Sc2ReplayStatsError(f"Sc2ReplayStats request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise Sc2ReplayStatsError("Sc2ReplayStats request could not reach the service") from exc
        except TimeoutError as exc:
            raise Sc2ReplayStatsError("Sc2ReplayStats request timed out") from exc
        try:
            decoded = body.decode("utf-8") if isinstance(body, bytes) else body
            return json.loads(decoded) if decoded else {}
        except (TypeError, ValueError) as exc:
            raise Sc2ReplayStatsError("Sc2ReplayStats returned a non-JSON response") from exc

    def post_replay(self, replay_path: Path, upload_method: str = "standalone") -> dict[str, Any]:
        """Upload one replay using the documented multipart `/replay` endpoint."""

        boundary = f"sc2review-{os.urandom(12).hex()}"
        filename = replay_path.name.replace('"', "'")
        replay_bytes = replay_path.read_bytes()
        chunks = [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="replay_file"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            replay_bytes,
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="upload_method"\r\n\r\n',
            upload_method.encode("utf-8"),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        request = Request(
            f"{self.base_url}{DEFAULT_UPLOAD_PATH}",
            data=b"".join(chunks),
            headers={
                "Accept": "application/json",
                "Authorization": self.authorization,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "sc2-replay-reviewer/0.3.0",
            },
            method="POST",
        )
        response = self._request_json(request)
        return {"response": response, "queue_id": _first_queue_identifier(response)}

    def pull_latest_replay(self) -> dict[str, Any]:
        latest = self.get(DEFAULT_LAST_REPLAY_PATH)
        replay_id = _first_identifier(latest)
        detail = None
        detail_error = None
        if replay_id is not None:
            try:
                detail = self.get(
                    f"/replay/{replay_id}",
                    {"include": json.dumps(list(DEFAULT_REPLAY_INCLUDES), separators=(",", ":"))},
                )
            except Sc2ReplayStatsError as exc:
                detail_error = str(exc)
        result: dict[str, Any] = {
            "last_replay": latest,
            "replay": detail,
            "replay_id": replay_id,
        }
        if detail_error:
            result["detail_error"] = detail_error
        return result


def _first_queue_identifier(value: Any) -> str | int | None:
    identifier_keys = {"replay_queue_id", "queue_id", "replayqueueid", "queueid"}
    for item in _walk(value):
        for key, candidate in item.items():
            if key.casefold() in identifier_keys and isinstance(candidate, (str, int)):
                return candidate
    return _first_identifier(value)


def _upload_state_path(root: Path) -> Path:
    return root / ".cache" / SOURCE_NAME / "upload-state.json"


def _load_upload_state(root: Path) -> dict[str, Any]:
    path = _upload_state_path(root)
    if path.exists():
        try:
            state = read_json(path)
            if state.get("schema_version") == UPLOAD_STATE_SCHEMA_VERSION and isinstance(state.get("files"), dict):
                return state
        except (OSError, ValueError, TypeError):
            pass
    return {"schema_version": UPLOAD_STATE_SCHEMA_VERSION, "files": {}}


def _upload_result(status: str, directory: Path, **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": UPLOAD_STATE_SCHEMA_VERSION,
        "source": SOURCE_NAME,
        "status": status,
        "directory": str(directory),
        "uploaded": [],
        "skipped": [],
        "failed": [],
        **extra,
    }


def upload_folder(
    directory: Path,
    root: Path,
    config: Sc2ReplayStatsConfig,
    *,
    opener: Callable[..., Any] = urlopen,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Upload every unsubmitted replay in a folder, keyed by content hash."""

    if not config.enabled or not config.upload_enabled:
        return _upload_result("disabled", directory)
    authorization = os.environ.get(config.auth_env, "").strip()
    if not authorization:
        return _upload_result("not_configured", directory, message=f"Set {config.auth_env} to enable replay uploads")
    if not directory.exists() or not directory.is_dir():
        return _upload_result("error", directory, message=f"Replay directory does not exist: {directory}")
    try:
        client = Sc2ReplayStatsClient(config.base_url, authorization, opener=opener)
    except Sc2ReplayStatsError as exc:
        return _upload_result("error", directory, message=str(exc))

    state = _load_upload_state(root)
    files_state = state["files"]
    current = now or _utc_now()
    result = _upload_result("completed", directory)
    replay_paths = sorted(
        (path for path in directory.iterdir() if path.is_file() and path.suffix.casefold() == ".sc2replay"),
        key=lambda path: path.name.casefold(),
    )
    for replay_path in replay_paths:
        try:
            replay_hash = sha256_file(replay_path)
            stat = replay_path.stat()
        except OSError as exc:
            result["failed"].append({"name": replay_path.name, "error": "could not read replay file"})
            continue
        previous = files_state.get(replay_hash, {})
        if previous.get("status") == "submitted":
            result["skipped"].append({"name": replay_path.name, "hash": replay_hash, "reason": "already_submitted"})
            continue
        try:
            upload = client.post_replay(replay_path, config.upload_method)
        except (OSError, Sc2ReplayStatsError) as exc:
            files_state[replay_hash] = {
                "name": replay_path.name,
                "size": stat.st_size,
                "status": "failed",
                "last_attempt_at": _iso(current),
                "error": str(exc),
            }
            result["failed"].append({"name": replay_path.name, "hash": replay_hash, "error": str(exc)})
            continue
        entry = {
            "name": replay_path.name,
            "size": stat.st_size,
            "status": "submitted",
            "submitted_at": _iso(current),
            "queue_id": upload.get("queue_id"),
        }
        files_state[replay_hash] = entry
        result["uploaded"].append({"name": replay_path.name, "hash": replay_hash, "queue_id": upload.get("queue_id")})
    write_json(_upload_state_path(root), state)
    result["counts"] = {
        "found": len(replay_paths),
        "uploaded": len(result["uploaded"]),
        "skipped": len(result["skipped"]),
        "failed": len(result["failed"]),
    }
    return result


def watch_upload_folder(
    directory: Path,
    root: Path,
    config: Sc2ReplayStatsConfig,
    *,
    on_scan: Callable[[dict[str, Any]], None] | None = None,
    opener: Callable[..., Any] = urlopen,
) -> None:
    """Keep scanning until interrupted, uploading each new content hash once."""

    while True:
        result = upload_folder(directory, root, config, opener=opener)
        if on_scan:
            on_scan(result)
        time.sleep(config.watch_poll_seconds)


def _empty_result(extraction: dict[str, Any], config: Sc2ReplayStatsConfig, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": EXTERNAL_SCHEMA_VERSION,
        "source": SOURCE_NAME,
        "status": status,
        "local_replay_hash": extraction.get("replay_hash"),
        "auth_env": config.auth_env,
        "base_url": config.base_url,
        "cache_reused": False,
        **extra,
    }


def pull_for_replay(
    extraction: dict[str, Any],
    root: Path,
    config: Sc2ReplayStatsConfig,
    *,
    force_refresh: bool = False,
    opener: Callable[..., Any] = urlopen,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Pull and cache the account's latest replay as supplemental data.

    A missing credential, API outage, or unmatched remote replay never blocks
    the local analysis. The returned status is written to the analysis bundle.
    """

    if not config.enabled:
        return _empty_result(extraction, config, "disabled")
    authorization = os.environ.get(config.auth_env, "").strip()
    if not authorization:
        return _empty_result(
            extraction,
            config,
            "not_configured",
            message=f"Set {config.auth_env} to enable the read-only Sc2ReplayStats pull",
        )
    replay_hash = str(extraction.get("replay_hash", ""))
    cache_path = _cache_path(root, replay_hash)
    current = now or _utc_now()
    if not force_refresh and cache_path.exists():
        try:
            cached = read_json(cache_path)
            fetched_at = _parse_iso(cached.get("fetched_at"))
            if fetched_at and current - fetched_at <= timedelta(seconds=config.cache_ttl_seconds):
                cached["cache_reused"] = True
                return cached
        except (OSError, ValueError, TypeError):
            pass
    try:
        client = Sc2ReplayStatsClient(config.base_url, authorization, opener=opener)
        remote = client.pull_latest_replay()
    except Sc2ReplayStatsError as exc:
        return _empty_result(extraction, config, "error", error=str(exc))
    match = _match_local_replay(extraction, remote)
    result = _empty_result(
        extraction,
        config,
        match["status"],
        match=match,
        replay_id=remote.get("replay_id"),
        fetched_at=_iso(current),
        remote=remote,
    )
    write_json(cache_path, result)
    return result
