#!/usr/bin/env bash
# Evaluation setup only: unchanged v5 pipeline and existing grader.
set -euo pipefail
NEOWEALTH_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$NEOWEALTH_ROOT"
mode="${1:-all}"
case "$mode" in all|raw|grade) ;; *) echo 'Usage: bash runners/run_neowealth_test.sh [all|raw|grade]' >&2; exit 2 ;; esac
export PIPELINE_OUTPUT_DIR="$NEOWEALTH_ROOT/outputs/openai_gpt_oss_120b/all/test/neowealth_v5"
export REPORT_FILE="$PIPELINE_OUTPUT_DIR/raw_pipeline.csv"
export RAW_REPORT_FILE="$REPORT_FILE"
export GRADED_REPORT_FILE="$PIPELINE_OUTPUT_DIR/graded_pipeline_tera.csv"
export GPT_OSS_LLM_GRADER_PIPELINE_VERSION="generic-v5-neowealth-test"
export INPUT_SAMPLE_FILE="$NEOWEALTH_ROOT/data/benchmarks/neowealth_test.csv"
export INPUT_SAMPLE_SHEET="" GROUND_TRUTH_OVERRIDE_FILE="" SEMANTIC_CATALOG_FILE="" RDF_ALIAS_MAP_FILE=""
export TEST_QUERY_LIMIT=768 TEST_QUERY_OFFSET=0
export TEST_MAX_WORKERS="${TEST_MAX_WORKERS:-4}" DAG_LEVEL_MAX_WORKERS="${DAG_LEVEL_MAX_WORKERS:-2}"
export REPORT_SAVE_EVERY=1 BENCHMARK_START_DELAY_SECONDS=0 DETERMINISTIC_EXPLAIN=1
export SQLITE_DB_PATH="${NEOWEALTH_SQLITE_DB:-$NEOWEALTH_ROOT/data/sql/neowealth/neowealth.db}"
export SCHEMA_FILE="${NEOWEALTH_SCHEMA_FILE:-$NEOWEALTH_ROOT/data/kg/neowealth_schema.ttl}"
export INSTANCE_FILE="${NEOWEALTH_INSTANCE_FILE:-$NEOWEALTH_ROOT/data/kg/neowealth_kg.ttl}"
export FUSEKI_ENDPOINT="${NEOWEALTH_FUSEKI_ENDPOINT:-http://127.0.0.1:3031/neowealth/query}"
mkdir -p "$PIPELINE_OUTPUT_DIR"
if [[ "$mode" == all || "$mode" == raw ]]; then
    for source_file in "$SQLITE_DB_PATH" "$SCHEMA_FILE" "$INSTANCE_FILE"; do
        if [[ ! -f "$source_file" ]]; then
            echo "Missing NeoWealth source asset: $source_file" >&2
            echo 'Provide the matching NeoWealth SQLite database and RDF schema/instance; the workbook contains evaluation questions and answers only.' >&2
            exit 1
        fi
    done
    if [[ ! -f "$INPUT_SAMPLE_FILE" ]]; then
        /usr/bin/python3 runners/prepare_neowealth_test.py
    fi
    /usr/bin/python3 -u runners/train/run_pipeline.py \
        configs/experiments/openai_gpt_oss_120b_neowealth_test.yaml \
        2>&1 | tee -a "$PIPELINE_OUTPUT_DIR/pipeline.log"
fi
if [[ "$mode" == all || "$mode" == grade ]]; then
    if [[ ! -f "$RAW_REPORT_FILE" ]]; then
        echo "Missing raw test report: $RAW_REPORT_FILE" >&2
        exit 1
    fi
    /usr/bin/python3 -u grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py \
        2>&1 | tee -a "$PIPELINE_OUTPUT_DIR/grader.log"
fi
