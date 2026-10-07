# Improvement12 SQL dynamic DAG pipeline

This experiment runs from `improvement12sqldynamic`, using the local
`run_pipeline_v3_sql _dynamic/run.py`. No improvement8 or improvement10 pipeline
folder is required. The workbook contains **1,000 questions across eight types**;
the JSON supplies **216 full-answer overrides**. The legacy `resume_442.py`
filename is retained, but it counts actual local inputs and has no 442-row limit.

## Paths

All paths below are relative to this experiment folder.

| Purpose | Location |
|---|---|
| Credentials | `.env` |
| SQLite | `wealth_management_diverse.db` |
| Schema/knowledge YAML | `table_medatada/` |
| Domain | `domain_intro_latest.prompt` |
| Business rules | `business_rules_addendum.md` |
| Workbook | `datatset/wealth_management_1000_test_set_questions.xlsx` |
| Full-answer overrides | `datatset/216_questions_full_results.json` |
| Combined run | `outputs/full_run/` |
| Eight independent runs | `outputs/question_types/<type>/` |
| Direct CLI default | `outputs/direct_run/raw_pipeline.csv` |

The existing spellings `datatset`, `table_medatada`, and the space in the pipeline
folder are intentional. CLI input options override stale data paths in `.env`.
The pipeline uses AWS Bedrock GPT-OSS 120B; the separate grader defaults to
`gpt-5-mini`. The rates in `metrics_config.json` are assumptions, not a verified bill.

Start CMD here:

```cmd
cd /d "C:\Users\AMAN KUMAR SINGH\Desktop\financial\improvement12sqldynamic"
```

## Offline validation

```cmd
python -u -B run_all.py --check
python -B -m unittest discover -s tests
python -B -m unittest discover -s "run_pipeline_v3_sql _dynamic\tests"
```

These commands make no model requests. `--check` archives all inputs in
`outputs/full_run` and validates local documents/schema/database. It does not
compile LLM knowledge. Preparation rejects changes to an existing input archive.

## Combined run

```cmd
python -u -B run_all.py --prepare-knowledge
python -u -B run_all.py
```

These use `outputs/full_run/knowledge_cache`. Outputs include `raw_pipeline.csv`,
`raw_pipeline_debug.csv`, and JSONL sidecars. Pipeline logs/timing summaries are
under `outputs/full_run/runtime/logs`. `_telemetry` holds per-run events, summaries,
call CSVs and question CSVs; `model_calls.csv` aggregates calls without duplicate
records from repeated saves. Knowledge compiler logs use the cache parent's `logs`
folder. Preparation and pipeline execution make model calls.

Use a separate folder for a small smoke run:

```cmd
python -u -B run_all.py --output-dir outputs\smoke --limit 3
```

Resume only crashes/service failures and unattempted questions:

```cmd
python -u -B run_all.py --resume-crashes-and-pending
```

Retry all saved execution errors, including calculation and final-spec errors:

```cmd
python -u -B run_all.py --retry-errors-in-place
```

Explicit recovery modes back up reports, preserve other results and record source/
configuration provenance. They require unchanged original questions and database.
Stop other writers for that report first. An ordinary run rejects an incompatible
existing report identity; use explicit recovery or a fresh output folder.

## Eight terminals

Prepare category manifests offline, then optionally prepare their shared cache once:

```cmd
python -B "run_pipeline_v3_sql _dynamic\scripts\run_question_types_v2.py" --prepare-only
python -u -B "run_pipeline_v3_sql _dynamic\run.py" --env-file .env --prepare-knowledge
```

Each category writes `outputs/question_types/<type>/raw_pipeline_v9.csv`, its debug
CSV/JSONL sidecars, `model_calls.csv` and `_telemetry`. Category runs share
`.runtime/knowledge_v3`; logs default to `.runtime/logs`.

Use one command in each terminal, after changing to this experiment folder:

**Terminal 1**
```cmd
python -u -B "run_pipeline_v3_sql _dynamic\scripts\run_question_types_v2.py" --type "Benchmark" --query-delay 0
```

**Terminal 2**
```cmd
python -u -B "run_pipeline_v3_sql _dynamic\scripts\run_question_types_v2.py" --type "At-Risk Critical" --query-delay 0
```

**Terminal 3**
```cmd
python -u -B "run_pipeline_v3_sql _dynamic\scripts\run_question_types_v2.py" --type "Batch Status" --query-delay 0
```

**Terminal 4**
```cmd
python -u -B "run_pipeline_v3_sql _dynamic\scripts\run_question_types_v2.py" --type "Enrichment Context" --query-delay 0
```

**Terminal 5**
```cmd
python -u -B "run_pipeline_v3_sql _dynamic\scripts\run_question_types_v2.py" --type "Multi-Step Comparative" --query-delay 0
```

**Terminal 6**
```cmd
python -u -B "run_pipeline_v3_sql _dynamic\scripts\run_question_types_v2.py" --type "Reference Compliance" --query-delay 0
```

**Terminal 7**
```cmd
python -u -B "run_pipeline_v3_sql _dynamic\scripts\run_question_types_v2.py" --type "Scoring Quantitative" --query-delay 0
```

**Terminal 8**
```cmd
python -u -B "run_pipeline_v3_sql _dynamic\scripts\run_question_types_v2.py" --type "Temporal Transaction" --query-delay 0
```

The script's `v2` suffix is historical; it launches this local dynamic pipeline.
Eight terminals share provider limits. A 429 saves a retryable failure and stops
the affected run; a knowledge cache hit does not remove per-question planning calls.

For category reports that already exist, preview or resume crashes/missing questions:

```cmd
python -B "run_pipeline_v3_sql _dynamic\scripts\resume_442.py" --dry-run
python -u -B "run_pipeline_v3_sql _dynamic\scripts\resume_442.py" --type benchmark
```

Recovery uses slugs: `benchmark`, `at_risk_critical`, `batch_status`,
`enrichment_context`, `multi_step_comparative`, `reference_compliance`,
`scoring_quantitative`, `temporal_transaction`. Omit `--type` to resume all eight
sequentially. This reads the local JSONL manifests, preserves non-crash errors,
and skips completed types. It is not a first-run launcher.

Retry all saved execution failures for a category:

```cmd
python -B "run_pipeline_v3_sql _dynamic\scripts\retry_failed_in_place.py" --status
python -u -B "run_pipeline_v3_sql _dynamic\scripts\retry_failed_in_place.py" --type scoring_quantitative
```

## Grading and metrics

Combined run:

```cmd
python -u -B grade_results.py
python -B compute_metrics.py
```

Grading makes model requests and requires `OPENAI_API_KEY` in the local `.env`.
Metrics are offline and prefer `graded_pipeline.csv` when available. Accuracy is
unavailable before grading. Add `--allow-partial` for incomplete reports. Use a new
graded output filename after changing answers or the grader model.

Category example:

```cmd
python -u -B grade_results.py --input outputs\question_types\benchmark\raw_pipeline_v9.csv --output outputs\question_types\benchmark\graded_pipeline.csv
python -B compute_metrics.py --output-dir outputs\question_types\benchmark --input outputs\question_types\benchmark\graded_pipeline.csv
```

## DAG and repair behavior

Three upfront candidates are validated and selected by reward/cost, with up to
three planning rounds and an explicit fixed-DAG fallback. Processing has three
total attempts. The calculation phase has four total attempts, including the
upfront execution; only failures invoke the existing Final_Spec repair mechanism.
Successful execution needs no second final-planning call. Repair can change
calculation dependencies and reuses processed branch data; missing source fields
retain the existing upstream repair routing.

Version: `aop-improvement12-v3-dynamic`. `PIPELINE_SUCCESS` confirms execution,
not answer correctness. See [pipeline notes](run_pipeline_v3_sql%20_dynamic/RUN.md)
and [YAML schema notes](run_pipeline_v3_sql%20_dynamic/YAML_SCHEMA.md).
