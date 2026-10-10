#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
mode="${1:-raw}"
tag="${2:-run_01}"
workers="${3:-4}"
case "$mode" in raw|grade|all) ;; *) echo 'Usage: run.sh [raw|grade|all] [run_tag] [workers]' >&2; exit 2 ;; esac
if [[ ! "$tag" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ || ! "$workers" =~ ^[1-9][0-9]*$ ]]; then
  echo 'Invalid run tag or workers' >&2; exit 2
fi
if [[ "$mode" != grade ]]; then
  /usr/bin/python3 -u -B runners/prepare_neowealth_test.py
  /usr/bin/python3 -u -B ablations/neowealth_hybrid/run_raw.py --run-tag "$tag" --workers "$workers" --dag-workers 1
fi
if [[ "$mode" != raw ]]; then
  run_dir="$root/ablations/neowealth_hybrid/runs/gemini_3_8_flash/without_context/$tag"
  /usr/bin/python3 -u -B runners/grade_gpt_5_mini.py --raw "$run_dir/raw_pipeline.csv" --output "$run_dir/graded_pipeline_gpt_5_mini.csv" --workers 4 --save-every 1
fi
