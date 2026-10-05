#!/usr/bin/env bash
set -euo pipefail
ABLATION_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 -u "$ABLATION_ROOT/run_raw.py" "$@"
