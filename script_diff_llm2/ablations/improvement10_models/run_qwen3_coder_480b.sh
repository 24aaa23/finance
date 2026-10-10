#!/usr/bin/env bash
set -euo pipefail
launcher_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
run_tag="${1:-run_01}"
/usr/bin/python3 -u -B "$launcher_dir/run_raw.py" qwen3_coder_480b \
  --run-tag "$run_tag" --prepare-knowledge
exec /usr/bin/python3 -u -B "$launcher_dir/run_sharded.py" \
  --models qwen3_coder_480b --workers 4 --run-tag "$run_tag"
