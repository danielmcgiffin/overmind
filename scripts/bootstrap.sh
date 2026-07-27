#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
mkdir -p "$project_dir/.cache/uv"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install uv or run this command in the project's Nix development shell." >&2
  exit 2
fi

if [[ -z "${UV_PYTHON:-}" ]]; then
  for candidate in /nix/store/*-python3-*/bin/python3; do
    if [[ -x "$candidate" ]]; then
      export UV_PYTHON="$candidate"
      break
    fi
  done
fi

export UV_PYTHON_DOWNLOADS="never"
export UV_LINK_MODE="copy"
export UV_CACHE_DIR="$project_dir/.cache/uv"
uv sync --locked
echo "Environment ready at $project_dir/.venv"
