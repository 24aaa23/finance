#!/usr/bin/env bash
# Fresh generic v5 reports; existing grader is used without modification.
set -euo pipefail
PIPELINE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PIPELINE_ROOT"
mode="${1:-all}"
case "$mode" in all|raw|grade) ;; *) echo 'Usage: bash runners/run_generic_v5.sh [all|raw|grade]' >&2; exit 2 ;; esac

# Restore the original experiment's sources, even after the NeoWealth launcher
# or a manually configured test dataset was used in this shell.
unset INPUT_SAMPLE_FILE INPUT_SAMPLE_SHEET GROUND_TRUTH_OVERRIDE_FILE SQLITE_DB_PATH
unset SCHEMA_FILE INSTANCE_FILE FUSEKI_ENDPOINT RDF_ALIAS_MAP_FILE

export PIPELINE_OUTPUT_DIR="${V5_OUTPUT_DIR:-$PIPELINE_ROOT/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5}"
export REPORT_FILE="$PIPELINE_OUTPUT_DIR/raw_pipeline.csv"
export RAW_REPORT_FILE="$REPORT_FILE"
export GRADED_REPORT_FILE="$PIPELINE_OUTPUT_DIR/graded_pipeline_tera.csv"
export SEMANTIC_CATALOG_FILE=""
export GPT_OSS_LLM_GRADER_PIPELINE_VERSION="generic-contract-recovery-v5"
export TEST_QUERY_LIMIT=1000 TEST_QUERY_OFFSET=0
export TEST_MAX_WORKERS="${TEST_MAX_WORKERS:-4}" DAG_LEVEL_MAX_WORKERS="${DAG_LEVEL_MAX_WORKERS:-2}"
export REPORT_SAVE_EVERY=1 BENCHMARK_START_DELAY_SECONDS=0 DETERMINISTIC_EXPLAIN=1
mkdir -p "$PIPELINE_OUTPUT_DIR"

if [[ "$mode" == all || "$mode" == raw ]]; then
    /usr/bin/python3 -u runners/train/run_pipeline.py \
        configs/experiments/openai_gpt_oss_120b_all_test1000.yaml \
        2>&1 | tee -a "$PIPELINE_OUTPUT_DIR/pipeline.log"
fi
if [[ "$mode" == all || "$mode" == grade ]]; then
    if [[ ! -f "$RAW_REPORT_FILE" ]]; then
        echo "Raw report does not exist: $RAW_REPORT_FILE" >&2
        exit 1
    fi
    /usr/bin/python3 -u grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py \
        2>&1 | tee -a "$PIPELINE_OUTPUT_DIR/grader.log"
fi
