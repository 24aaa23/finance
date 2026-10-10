# V5 run guide: optional context, resume, and changing sources

This guide contains combined commands for the raw v5 pipeline and the unchanged
grader, followed by the exact environment variables to replace when changing
questions or backend data. All edits to a command happen before you execute it.
`$PWD` resolves to the absolute `script_diff_llm2` directory after its `cd` line.

For the paper-oriented architecture, decomposition methodology, and comparison
with Improvement 6, see [current pipeline methodology](docs/current_pipeline_methodology.md).

## Reliability improvements and fresh reruns

The current implementation includes the generic reliability v6 fixes. For new
model/context ablations and bounded parallel GPT-5 Mini grading, use
[README_RELIABILITY_V6.md](README_RELIABILITY_V6.md). Keep earlier reports for
comparison and use a fresh run tag; code/configuration changes cannot resume into
an existing ablation CSV. The original grader scoring logic remains unchanged.

## Before running

- Configure the normal pipeline model credentials and grader credentials.
- Start Fuseki with the graph matching the SQL database/RDF instance files. The
  current commands expect `http://127.0.0.1:3030/wealth/query`.
- Keep source data, question IDs, context settings and model settings unchanged
  when resuming. Use a fresh output directory when changing any of them.

These commands invoke the Python runner directly so your explicit source paths
are retained. The existing `run_generic_v5.sh` and `run_domain_context_v5.sh`
launchers restore the original 1,000-question experiment's source paths; do not
use those launchers to run a different backend via environment overrides.

## 1. Original v5 without business context: raw + grader

Copy and run the complete block. It resumes the existing `generic_no_rules_v5`
reports if present. To start a separate experiment, change `PIPELINE_OUTPUT_DIR`
to a new directory first.

```bash
bash -e <<'SH'
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2

export SQLITE_DB_PATH="$PWD/historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db"
export INPUT_SAMPLE_FILE="$PWD/wealth_management_1000_test_set_questions.xlsx"
export INPUT_SAMPLE_SHEET="ALL_BENCHMARK_SHEETS"
export GROUND_TRUTH_OVERRIDE_FILE="$PWD/216_questions_full_results.json"
export SCHEMA_FILE="$PWD/data/kg/wealth_management_diverse_schema.ttl"
export INSTANCE_FILE="$PWD/data/kg/wealth_management_diverse_kg.ttl"
export RDF_ALIAS_MAP_FILE="$PWD/data/kg/rdf_id_alias_map.json"
export FUSEKI_ENDPOINT="http://127.0.0.1:3030/wealth/query"

export DOMAIN_CONTEXT_REQUIRED=""
export DOMAIN_INTRO_FILE=""
export BUSINESS_RULES_FILE=""
export DOMAIN_CONTEXT_APPROVAL_FILE=""
export DOMAIN_CONTEXT_PREPARE_ONLY=""
export SEMANTIC_CATALOG_FILE=""

export PIPELINE_OUTPUT_DIR="$PWD/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5"
export REPORT_FILE="$PIPELINE_OUTPUT_DIR/raw_pipeline.csv"
export RAW_REPORT_FILE="$REPORT_FILE"
export GRADED_REPORT_FILE="$PIPELINE_OUTPUT_DIR/graded_pipeline_tera.csv"

export TEST_QUERY_LIMIT=1000 TEST_QUERY_OFFSET=0
export TEST_MAX_WORKERS=4 DAG_LEVEL_MAX_WORKERS=2
export REPORT_SAVE_EVERY=1 BENCHMARK_START_DELAY_SECONDS=0
export DETERMINISTIC_EXPLAIN=1
export GPT_OSS_LLM_GRADER_PIPELINE_VERSION="generic-contract-recovery-v5"

mkdir -p "$PIPELINE_OUTPUT_DIR"

/usr/bin/python3 -u runners/train/run_pipeline.py \
  "$PWD/configs/experiments/openai_gpt_oss_120b_all_test1000.yaml"

/usr/bin/python3 -u \
  "$PWD/grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py"
SH
```

The empty document variables explicitly disable the context feature. The
pipeline does not discover documents just because they exist in this folder.

## 2. V5 with optional context: preparation/cache + raw + grader

Use the same complete block for the first run and later resumptions. Preparation
runs automatically at startup if there is no matching cache. The command requires
active context and stops before benchmark execution if preparation fails or no
entries are active. A matching cache
skips the preparation LLM call; no separate preparation command is required.

```bash
bash -e <<'SH'
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2

export SQLITE_DB_PATH="$PWD/historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db"
export INPUT_SAMPLE_FILE="$PWD/wealth_management_1000_test_set_questions.xlsx"
export INPUT_SAMPLE_SHEET="ALL_BENCHMARK_SHEETS"
export GROUND_TRUTH_OVERRIDE_FILE="$PWD/216_questions_full_results.json"
export SCHEMA_FILE="$PWD/data/kg/wealth_management_diverse_schema.ttl"
export INSTANCE_FILE="$PWD/data/kg/wealth_management_diverse_kg.ttl"
export RDF_ALIAS_MAP_FILE="$PWD/data/kg/rdf_id_alias_map.json"
export FUSEKI_ENDPOINT="http://127.0.0.1:3030/wealth/query"

export DOMAIN_CONTEXT_REQUIRED=1
export DOMAIN_INTRO_FILE="$PWD/domain_intro.prompt"
export BUSINESS_RULES_FILE="$PWD/phase0_business_rules.md"
export DOMAIN_CONTEXT_CACHE_DIR="$PWD/outputs/domain_context"
export DOMAIN_CONTEXT_APPROVAL_FILE=""
export DOMAIN_CONTEXT_PREPARE_ONLY=""
export SEMANTIC_CATALOG_FILE=""

export PIPELINE_OUTPUT_DIR="$PWD/outputs/openai_gpt_oss_120b/all/test1000/context_v5_01"
export REPORT_FILE="$PIPELINE_OUTPUT_DIR/raw_pipeline.csv"
export RAW_REPORT_FILE="$REPORT_FILE"
export GRADED_REPORT_FILE="$PIPELINE_OUTPUT_DIR/graded_pipeline_tera.csv"

export TEST_QUERY_LIMIT=1000 TEST_QUERY_OFFSET=0
export TEST_MAX_WORKERS=4 DAG_LEVEL_MAX_WORKERS=2
export REPORT_SAVE_EVERY=1 BENCHMARK_START_DELAY_SECONDS=0
export DETERMINISTIC_EXPLAIN=1
export GPT_OSS_LLM_GRADER_PIPELINE_VERSION="generic-contract-recovery-v5"

mkdir -p "$PIPELINE_OUTPUT_DIR"

/usr/bin/python3 runners/check_domain_context_run.py "$PIPELINE_OUTPUT_DIR"

/usr/bin/python3 -u runners/train/run_pipeline.py \
  "$PWD/configs/experiments/openai_gpt_oss_120b_all_test1000.yaml"

/usr/bin/python3 -u \
  "$PWD/grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py"
SH
```

### What this context command activates

- Eligible, schema-grounded terminology can activate automatically.
- Formulas, defaults, constraints and advisory policies require independent
  review and hash-bound approval; the command above leaves approvals empty.
- The current `phase0_business_rules.md` is evaluation-scoped. Its contents are
  excluded from preparation and inference, and its exclusion is logged.
- Missing optional documents are ignored with a diagnostic. With
  `DOMAIN_CONTEXT_REQUIRED=1`, no usable active context stops the run. Without that
  flag, preparation failure falls back to the existing generic path.

Preparation handles reasoning blocks, Markdown and introductory text, and retries
an invalid response once. Failure response diagnostics are saved locally under
`DOMAIN_CONTEXT_CACHE_DIR` as `*.failure.json`; these can contain source metadata.

The preparation log prints a review JSON path under `outputs/domain_context`.
The cache is keyed by documents, runtime schema, preparation version and model.
For reviewing and activating independently confirmed rules, see
[the context guide](docs/domain_context.md). If using an approval file, replace:

```bash
export DOMAIN_CONTEXT_APPROVAL_FILE="/absolute/path/to/domain_context_approval.json"
```

Set this before the first benchmark run in that output directory. If you change
approvals after rows have been generated, use a fresh `PIPELINE_OUTPUT_DIR`.
Preparation validates structural grounding, not business-rule truth, and no
accuracy improvement is guaranteed.

## 3. Resume after stopping

Re-run the same complete command with the same output directory:

- The raw runner loads saved rows and skips completed question IDs. Some failed
  or stale-version rows are eligible for retry under its existing resume policy.
- The grader reuses completed eligible grades and retries unresolved grader errors.
- Work that was not saved before interruption can be repeated. Resume operates
  at saved question/grade boundaries, not halfway through an individual LLM call.
- The context command uses the preparation cache when its fingerprint matches.

Reports are saved in `PIPELINE_OUTPUT_DIR`:

| File | Purpose |
| --- | --- |
| `raw_pipeline.csv` | Raw pipeline results |
| `graded_pipeline_tera.csv` | Grader results |
| `domain_context_inputs.json` | Context document/approval inputs, for context runs |

The context input guard refuses to resume a nonempty raw report with changed or
untracked document/approval inputs. It does **not** detect changes to question
files, database contents, model settings or all runtime parameters. Always use a
fresh output directory for those changes.

## 4. Change only the query dataset; retain the SQL database and KG

Replace these lines in either combined command:

```bash
export INPUT_SAMPLE_FILE="/absolute/path/to/new_questions.csv"
export INPUT_SAMPLE_SHEET=""
export GROUND_TRUTH_OVERRIDE_FILE=""
export TEST_QUERY_LIMIT=1000  # Replace with the desired number of questions.
export PIPELINE_OUTPUT_DIR="$PWD/outputs/new_questions/v5_run_01"
```

For CSV, keep `INPUT_SAMPLE_SHEET` empty. For Excel, supply the appropriate sheet
name/settings. The straightforward CSV format is:

```csv
global_question_id,question,ground_truth_answer
```

Each question should have a stable, unique ID and a reference answer belonging
to the backend you are querying. Disable the old `216_questions_full_results.json`
override when switching question datasets. If the new dataset has its own
answer-override JSON, point `GROUND_TRUTH_OVERRIDE_FILE` to that file instead.
Reference answers are evaluation inputs, not inputs to the context agent.

Keep the SQL database, KG schema/instances, Fuseki endpoint, alias map and context
document paths unchanged. The existing prepared context can be reused when the
schema and document fingerprint remains the same.

## 5. Change the SQL database and KG files

First prepare the new question dataset and corresponding SQL/RDF data. Load the
new RDF graph into Fuseki. Apply the query-dataset/output changes from section 4,
then replace these source lines:

```bash
export SQLITE_DB_PATH="/absolute/path/to/new_database.db"
export SCHEMA_FILE="/absolute/path/to/new_schema.ttl"
export INSTANCE_FILE="/absolute/path/to/new_instances.ttl"
export FUSEKI_ENDPOINT="http://127.0.0.1:3030/new_database/query"
export RDF_ALIAS_MAP_FILE=""
```

Use the new database's verified alias-map path if needed; otherwise keep the map
empty. Do not reuse the old database's aliases. Updating `INSTANCE_FILE` does not
by itself populate Fuseki: the endpoint must serve the corresponding new graph.
The current implementation expects a SQLite database at `SQLITE_DB_PATH`.

For the business-context command, additionally replace:

```bash
export DOMAIN_INTRO_FILE="/absolute/path/to/new_domain_intro.prompt"
export BUSINESS_RULES_FILE="/absolute/path/to/new_business_rules.md"
export DOMAIN_CONTEXT_APPROVAL_FILE=""
```

Leave either document path empty if it is unavailable. Use independently authored
source metadata, not benchmark-derived corrections. New document/schema
fingerprints trigger preparation automatically. Old approvals do not carry over.
If database contents change but documents/schema do not, the preparation cache
may still match; use a fresh report directory regardless.

For the generic command, keep both document paths and the approval path empty.

The existing experiment YAML in the commands supplies the model settings; the
exported environment variables override its source paths and report destinations.
For a different model/experiment configuration, change the YAML argument too.

## 6. Report lines that stay unchanged

These lines derive the report paths from whichever output directory you select:

```bash
export REPORT_FILE="$PIPELINE_OUTPUT_DIR/raw_pipeline.csv"
export RAW_REPORT_FILE="$REPORT_FILE"
export GRADED_REPORT_FILE="$PIPELINE_OUTPUT_DIR/graded_pipeline_tera.csv"
```

Keep them after the `PIPELINE_OUTPUT_DIR` assignment. The combined command runs
the raw pipeline first and then the grader. `bash -e` stops the block if a command
returns a nonzero exit status.

## Preparation contract and glossary recovery

Each extracted entry must name one physical `source` as a string and list exact
unqualified column/property names in `fields`. Lists of sources and logical field
prefixes are rejected rather than guessed. Supporting quotes must match the source
text verbatim. Policies are not reclassified as terminology to activate them.

If candidate extraction produces no usable terminology or approved rule, a separate
glossary-only preparation pass requests source-supported field/entity meanings.
It validates its results and retries once with the rejection reasons if needed.
Valid glossary entries are cached alongside the original review candidates; later
runs with active cached context skip this preparation. New preparation versions
invalidate old caches and approvals. Strict mode still stops if nothing activates.

An agent-provided `terminology` label does not bypass approval: entries containing
numeric thresholds, formula markers or operational language in their definition
or quote are conservatively treated as definitions requiring independent review.
This can also hold back legitimate numeric descriptions; it preserves the approval
boundary instead of silently adopting a policy. Review JSON records the reclassification.
