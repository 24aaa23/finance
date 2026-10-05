#!/usr/bin/env bash
# Explicit opt-in launcher; the generic v5 launcher retains its defaults.
set -euo pipefail
PIPELINE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PIPELINE_ROOT"
mode="${1:-all}"
case "$mode" in prepare|all|raw|grade) ;; *) echo 'Usage: bash runners/run_domain_context_v5.sh [prepare|all|raw|grade]' >&2; exit 2 ;; esac
export DOMAIN_INTRO_FILE="${DOMAIN_INTRO_FILE-$PIPELINE_ROOT/domain_intro.prompt}"
export BUSINESS_RULES_FILE="${BUSINESS_RULES_FILE-$PIPELINE_ROOT/phase0_business_rules.md}"
export DOMAIN_CONTEXT_REQUIRED=1
export V5_OUTPUT_DIR="${V5_OUTPUT_DIR:-$PIPELINE_ROOT/outputs/openai_gpt_oss_120b/all/test1000/generic_domain_context_v1}"
if [[ "$mode" == prepare ]]; then
    export DOMAIN_CONTEXT_PREPARE_ONLY=1
    exec bash runners/run_generic_v5.sh raw
fi
unset DOMAIN_CONTEXT_PREPARE_ONLY
if [[ "$mode" == all || "$mode" == raw ]]; then
    /usr/bin/python3 runners/check_domain_context_run.py "$V5_OUTPUT_DIR"
fi
exec bash runners/run_generic_v5.sh "$mode"
