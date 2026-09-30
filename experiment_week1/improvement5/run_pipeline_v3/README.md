# Improvement5 Pipeline V3

Changes: [VERSION_CHANGES.md](VERSION_CHANGES.md). V2 code and results are unchanged.
New results go to `../pipeline_output_v3/`.

## Start Fuseki

In a separate CMD window:

```cmd
cd /d "C:\Users\AMAN KUMAR SINGH\Desktop\financial\experiment_week1\improvement5"
powershell -NoProfile -ExecutionPolicy Bypass -File run_pipeline_v3\scripts\start_jena_fuseki_v3.ps1
```

Leave the window running. Default endpoint: `http://127.0.0.1:3030/wealth/query`.
Do not start a second instance if the correct dataset is already served there.

## Run A Dataset

Open CMD in `improvement5`, or first run:

```cmd
cd /d "C:\Users\AMAN KUMAR SINGH\Desktop\financial\experiment_week1\improvement5"
```

### ARC
```cmd
python run_pipeline_v3\run.py ARC
```

### BSQ
```cmd
python run_pipeline_v3\run.py BSQ
```

### EC
```cmd
python run_pipeline_v3\run.py EC
```

### MC
```cmd
python run_pipeline_v3\run.py MC
```

### MC_diverse
```cmd
python run_pipeline_v3\run.py MC_diverse
```

### RC
```cmd
python run_pipeline_v3\run.py RC
```

### SQA
```cmd
python run_pipeline_v3\run.py SQA
```

### TT
```cmd
python run_pipeline_v3\run.py TT
```

### WM
```cmd
python run_pipeline_v3\run.py WM
```

Each command uses all rows and creates a new timestamped CSV, adjacent debug CSV
and manifest. It overrides stale input/output/version/pack settings.
For a small check: `python run_pipeline_v3\run.py MC --limit 3`.
Add `--dry-run` to check paths without loading clients, calling APIs or writing results.

Live runs still require the existing Python dependencies, credentials and `.env`.
Final review defaults on and increases model usage. An explicit terminal or `.env`
value `FINAL_SEMANTIC_REVIEW=0` disables it for direct Python runs; the PowerShell
category runners explicitly enable it.

No-argument `python run_pipeline_v3\run.py` still supports `INPUT_QUERY_CSV` and
`REPORT_FILE`, retaining the old workbook fallback. Prefer the category commands
for these CSVs. PowerShell runners for individual CSVs, all nine and the combined
605-question file are in `scripts/`, renamed `_v3` with v3 output paths.

## Grade Saved Results

Use `run_pipeline_v3\grade_final_answers.py` for v3. It uses the same NULL rules
for every category, based on the question and reference answer. The shared root
grader still has the older MC_diverse-only policy.

From `improvement5`, for example, grade the saved MC_diverse run:

```cmd
python run_pipeline_v3\grade_final_answers.py --output-dir pipeline_output_v3 --raw-report pipeline_output_v3\MC_diverse_v3_20260927_211627_973840.csv --graded-report pipeline_output_v3\graded\MC_diverse_v3_graded.csv
```

Use the corresponding raw report and graded destination for another dataset.
Select the main result CSV, not its `_debug.csv`. Add `--dry-run` to validate paths
without API calls or writes. Grading makes model calls; rerunning the pipeline is
not required. `Grade Status` contains MATCH/PARTIAL/MISMATCH/OTHER; `New Status`
keeps execution status. `Grading Policy` records the policy used. Resume reuses
unchanged grades only under the same model and policy.

Pipeline execution failures count as `MISMATCH` in `Grade Status`, so failed
questions stay in the end-to-end accuracy denominator. `Execution Status`,
`New Status` and the original error text are preserved. `Grade Reason` explains
that no successful answer was produced; `Direct LLM Grading Path` records
`execution_failure_as_mismatch`. No model call is needed for these rows.
Rerun the same grader command to replace old `SKIPPED_EXECUTION_FAILURE` labels;
unchanged successful grades are reused. This changes reporting, not the failed
pipeline answers. Grader API errors and pending grades remain separate and retryable.

## Offline Tests

```cmd
python -m unittest discover -s run_pipeline_v3\tests -q
```

See [OPERATOR_USAGE.md](OPERATOR_USAGE.md) for stages and repair limits.
