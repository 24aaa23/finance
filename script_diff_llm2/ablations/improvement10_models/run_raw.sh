#!/usr/bin/env bash
set -euo pipefail
LAUNCHER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 -u "$LAUNCHER_DIR/run_raw.py" "$@"
