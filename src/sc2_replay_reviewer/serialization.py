"""JSON-safe conversion for s2protocol values and deterministic output."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return {"encoding": "hex", "value": value.hex()}
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    ).encode("utf-8") + b"\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
