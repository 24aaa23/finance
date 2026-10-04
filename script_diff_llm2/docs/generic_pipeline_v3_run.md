# Generic pipeline v3: run and resume

This revision separates physical column operands from derived aliases, adds explicit aggregate predicates, repairs observed RDF datatype extraction, and prepares SQL against the read-only database before model validation. The grader and saved reports are unchanged. These commands disable the optional semantic catalog.

`operand_kind` is `physical` or `aliases`; it is independent of computation grain. Physical COUNT/SUM/AVG measures do not require a derived formula. Physical arithmetic uses `formula_stage: row`; formulas over final aggregate aliases use `source_class: derived`, `operand_kind: aliases` and `formula_stage: final_group`.

`population_filters` apply only to input rows. `aggregate_filters` apply after aggregation, reference the owning measure's alias and specify `stage: entity|final_group` and `scope: population|metric`. Population scope restricts eligible entities for all measures; metric scope restricts only that metric's contributors. Cleanup relocates legacy predicates that explicitly reference their owning derived alias from population_filters into aggregate_filters, updating indexed requirement references. It never guesses from benchmark identifiers or rewrites physical row thresholds based on reference answers.

Supported deterministic SQL plans implement entity predicates with HAVING and final-group predicates on the computed result. Unsupported stages/scopes fall back to generation. SQL and SPARQL generation/validation prompts now explicitly preserve aggregate-predicate scope. SQL prompts also require null-safe joins between nullable grouped dimensions and preserve NOT IN null semantics.

RDF datatype extraction now binds DATATYPE in the outer graph scope. An end-to-end synthetic test verifies metadata extraction and rejection of an untyped string date comparison. SQL preparation uses EXPLAIN on a read-only connection; it does not execute the query. Syntax/alias/HAVING errors become pre-scan repair feedback.

These changes are generic mechanics, not inferred business definitions. Ambiguous ownership, units, sign conventions and stored-versus-computed metric definitions still need explicit question wording or independently documented source metadata. There has been no paid benchmark rerun of this revision, so its accuracy is not yet measured.
Start Fuseki in a separate terminal if the configured dataset is not already served:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
./tools/apache-jena-fuseki-6.1.0/fuseki-server \
  --localhost --port=3030 \
  --file="$PWD/data/kg/wealth_management_diverse_kg.ttl" /wealth
```

Run the raw pipeline, followed by the existing grader, in another terminal. The output folder and version distinguish this revision from the older runs:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
export PIPELINE_OUTPUT_DIR="$PWD/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v3"
export REPORT_FILE="$PIPELINE_OUTPUT_DIR/raw_pipeline.csv"
export RAW_REPORT_FILE="$REPORT_FILE"
export GRADED_REPORT_FILE="$PIPELINE_OUTPUT_DIR/graded_pipeline_tera.csv"
export SEMANTIC_CATALOG_FILE=""
export GPT_OSS_LLM_GRADER_PIPELINE_VERSION="generic-stages-v3"
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

Existing credentials and configured source assets must be available. These commands make paid model calls. Repeating the same commands with the same folder and pipeline version resumes saved raw rows and graded rows. Raw CRASH/QUOTA_EXHAUSTED rows are retried; other saved failures are considered completed. In-flight work that was not saved may repeat. Use a new folder and version after subsequent code changes to avoid mixing revisions. Do not reuse the v1 or v2 reports for this revision.

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
