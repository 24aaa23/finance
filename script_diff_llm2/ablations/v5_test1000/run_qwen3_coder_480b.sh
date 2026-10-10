#!/usr/bin/env bash
set -euo pipefail
launcher_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
condition="${1:-without_context}"
run_tag="${2:-reliability_v6_01}"
exec bash "$launcher_dir/run_raw.sh" qwen3_coder_480b "$condition" \
  --run-tag "$run_tag" --workers 4
