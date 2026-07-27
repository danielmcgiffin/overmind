#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${1:-$repo_root/dist}"
archive="$destination/sc2-replay-reviewer-source.tar.gz"

mkdir -p "$destination"
rm -f "$archive"

tar -czf "$archive" \
  --exclude='./.git' \
  --exclude='./.venv' \
  --exclude='./.cache' \
  --exclude='./.pytest_cache' \
  --exclude='./.codex' \
  --exclude='./.agents' \
  --exclude='./output' \
  --exclude='./dist' \
  --exclude='*/__pycache__' \
  --exclude='*.py[cod]' \
  --exclude='*.SC2Replay' \
  --exclude='*.sc2replay' \
  -C "$repo_root" .

printf 'Created %s\n' "$archive"
