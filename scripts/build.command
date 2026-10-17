#!/usr/bin/env bash
set -euo pipefail
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ "$#" -lt 1 ]; then
  printf 'Usage: build.command /path/original.wsc [--variant qa09|chip-control|all]\n' >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3.11 or newer is required.\n' >&2
  exit 2
fi
exec python3 "$HERE/project.py" build --source "$@"
