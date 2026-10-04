# Generic pipeline v2: run and resume

This revision repairs plan-contract compatibility, adds bounded runtime source-value evidence, separates metric eligibility, and checks typed RDF date comparisons. It introduces no financial dataset mappings or benchmark-derived metric definitions. The grader is unchanged. An optional source-owned semantic catalog remains supported; these commands disable it.

The deterministic SQL compiler supports explicit entity-first grouped plans with independent metric populations, nested final-group arithmetic and exact final projection. Plans with upstream bindings or complex boolean trees fall back to the generator rather than silently losing those constraints. Model generation and validation still interpret ambiguous semantics; these changes do not guarantee a particular benchmark accuracy. No paid benchmark rerun was performed as part of this revision.

Start Fuseki in a separate terminal if the configured dataset is not already served:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
./tools/apache-jena-fuseki-6.1.0/fuseki-server \
  --localhost --port=3030 \
  --file="$PWD/data/kg/wealth_management_diverse_kg.ttl" /wealth
```

Run the raw pipeline, followed by the existing grader, in another terminal. The output folder and version distinguish this revision from the older v1 run:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
export PIPELINE_OUTPUT_DIR="$PWD/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v2_20261003"
export REPORT_FILE="$PIPELINE_OUTPUT_DIR/raw_pipeline.csv"
export RAW_REPORT_FILE="$REPORT_FILE"
export GRADED_REPORT_FILE="$PIPELINE_OUTPUT_DIR/graded_pipeline_tera.csv"
export SEMANTIC_CATALOG_FILE=""
export GPT_OSS_LLM_GRADER_PIPELINE_VERSION="generic-contract-grounding-v2-20261003"
export TEST_QUERY_LIMIT=1000 TEST_QUERY_OFFSET=0
export TEST_MAX_WORKERS=4 DAG_LEVEL_MAX_WORKERS=2
export REPORT_SAVE_EVERY=1 BENCHMARK_START_DELAY_SECONDS=0 DETERMINISTIC_EXPLAIN=1
mkdir -p "$PIPELINE_OUTPUT_DIR"
set -o pipefail
/usr/bin/python3 -u runners/train/run_pipeline.py \
  configs/experiments/openai_gpt_oss_120b_all_test1000.yaml \
  2>&1 | tee -a "$PIPELINE_OUTPUT_DIR/pipeline.log" && \
/usr/bin/python3 -u grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py \
  2>&1 | tee -a "$PIPELINE_OUTPUT_DIR/grader.log"
```

Existing credentials and configured source assets must be available. These commands make paid model calls. Repeating the same commands with the same folder and pipeline version resumes saved raw rows and graded rows. Raw CRASH/QUOTA_EXHAUSTED rows are retried; other saved failures are considered completed. In-flight work that was not saved may repeat. Use a new folder and version after subsequent code changes to avoid mixing revisions. Do not reuse the v1 reports for this revision.

To resume only grading after exporting the same variables:

```bash
/usr/bin/python3 -u grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py \
  2>&1 | tee -a "$PIPELINE_OUTPUT_DIR/grader.log"
```

Offline validation uses synthetic source data and fake clients, without benchmark answers:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/unit -q
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/regression -q
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/integration -q
```
