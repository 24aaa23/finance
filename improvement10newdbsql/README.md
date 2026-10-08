# NeoWealth SQL pipeline

Run from this folder:

```cmd
python -m pip install -r requirements.txt
python run_pipeline.py --workers 4
```

Install dependencies with the same `python` command used to launch the pipeline.

The launcher uses this experiment's `.env`, `newdb/neowealth.duckdb`, all 21
YAML files in `newdb/primitves_updated_final`, the main domain/rule book and
its `ALL_RULES_COMPILED` version. It loads the 757 tasks from the workbook's
`questions` sheet. Six truncated reference-answer cells are reconstructed
from the complete `gold_answers` sheet; reference answers stay out of agent inputs.

The implementation remains in `run_pipeline_v3_sql _`. Each question owns its
planner, executor and consultation session. A shared knowledge pack is compiled
once, cached in `.runtime/knowledge_neowealth`, then reused. The coordinator
alone writes checkpoints. The existing decomposition, fixed operator flow,
local calculation operators and repair loops are retained.

DuckDB scans open separate read-only connections with external access disabled.
Session null ordering and case-insensitive collation follow the supplied rules.
YAML identity IDs map to their documented physical table names. Dates/timestamps
are serialized as ISO text and decimal values as numeric JSON for local operators.

Outputs are in `outputs/full_run`: `raw_pipeline.csv`, `raw_pipeline_debug.csv`,
lossless JSONL reports and telemetry. Detailed logs are in `.runtime/logs`.
Repeat the same command to resume saved completed questions; keep the same inputs,
model, code and worker count. For a separate experiment use `--output-dir`.
`--limit N` selects a fixed input window; it is not an additional-N-pending option.
No answer grader runs automatically.

Run the same pipeline on AWS Bedrock DeepSeek V3.1 (685B):

```cmd
python run_pipeline.py --workers 4 --model deepseek-v3.1
```

The preset uses `deepseek.v3-v1:0` on the regional Bedrock Runtime endpoint
and the AWS credentials in this folder's `.env`. All model-backed agents,
including domain compilation and query understanding, use the selected model.
It does not edit `.env` or change the decomposition, DAG, operators or repairs.
Results are saved under `outputs/deepseek_v3_1` and knowledge is cached under
`.runtime/knowledge_neowealth_deepseek_v3_1`. Repeat the same command to resume
that experiment. The original command still uses `outputs/full_run`.
Knowledge compilation requests at most 8192 output tokens to respect V3.1's
Bedrock limit. Live model access is checked when you launch the run.
AWS model reference: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-deepseek-deepseek-v3-1.html

For DeepSeek V3.2 use:

```cmd
python run_pipeline.py --workers 4 --model deepseek-v3.2
```

This selects the Bedrock model ID `deepseek.v3.2`, with the same local AWS
credentials, inputs and pipeline. Its separate results folder is
`outputs/deepseek_v3_2`; its cache is `.runtime/knowledge_neowealth_deepseek_v3_2`.
V3.2 also uses the Bedrock 8192-token output limit for knowledge compilation.
AWS model reference: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-deepseek-deepseek-v3-2.html

Final-plan runtime fixes (v2) accept boolean literal/comparison spellings and
searched CASE expressions through the restricted expression interpreter, add
explicit text functions/cumulative totals, and support median/continuous
percentiles. Whole-column percentile expressions compile to one aggregate row.
Grouping checks follow projected formulas and explicit join-key equalities;
scalar denominator grains do not replace the answer's grouping. Missing fields,
unsupported code and genuinely different grouping still fail validation.

After the current run finishes, retry saved execution failures with the new code:

```cmd
python run_pipeline.py --workers 4 --model gpt-oss --retry-errors-in-place
```

For the DeepSeek V3.2 report use `--model deepseek-v3.2` instead. This existing
retry path backs up the raw report, debug report and manifest to a timestamped
`backup_before_retry_*` directory, retains successful rows, and records old/new
run identities for the mixed-version results. It retries all saved execution
failure statuses, including Final_Spec; it does not rerun successful answers.
Original edited code is under `.runtime/backups/before_final_spec_fixes`.
Offline replay diagnostics are under `.runtime/diagnostics`; those are execution
checks, not answer-accuracy measurements. No reference answers are used for fixes.

To restart an interrupted run, retry failures AND finish all unsaved questions:

```cmd
python run_pipeline.py --workers 4 --model gpt-oss --retry-errors-in-place --include-pending
python run_pipeline.py --workers 4 --model deepseek-v3.2 --retry-errors-in-place --include-pending
```

Run these in separate terminals. Each model keeps its existing CSV, backs it up
before changing rows, replaces failed rows by ID and appends newly completed
questions. Saved successful rows are retained. Input IDs and saved question/
reference text must match the unchanged full input manifest.

Offline validation and tests:

```cmd
python run_pipeline.py --workers 4 --check-inputs
python -B -m unittest discover -s tests
```

Original modified package files are backed up under
`.runtime/backups/before_neowealth_workers_20261008_175836`.
