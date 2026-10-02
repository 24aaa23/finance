Question
-> create 3 decomposition candidates
-> for each decomposition, create 3 DAG candidates
-> evaluate 9 DAG/decomposition combinations
-> select best
-> execute

## Run the 1,000-question benchmark by type

The workbook is split into eight independent 125-question runs.  Each run gets
its own folder under `pipelien_output`, so it can be resumed and graded without
mixing results from the other types.

Prepare all eight input manifests without invoking Fuseki or the model:

```powershell
cd C:\Users\AMAN KUMAR SINGH\Desktop\financial\experiment_week1\improvement6
.\run_pipeline_v2\scripts\run_question_types_v2.ps1 -PrepareOnly
```

Run one type (recommended before a full batch):

```powershell
.\run_pipeline_v2\scripts\run_question_types_v2.ps1 -Type 'Benchmark' -Workers 1
```

Run every type sequentially:

```powershell
.\run_pipeline_v2\scripts\run_question_types_v2.ps1 -Workers 1
```

Run eight terminals, with **one different command in each terminal**:

```powershell
.\run_one_type.cmd "Benchmark"
.\run_one_type.cmd "At-Risk Critical"
.\run_one_type.cmd "Batch Status"
.\run_one_type.cmd "Enrichment Context"
.\run_one_type.cmd "Multi-Step Comparative"
.\run_one_type.cmd "Reference Compliance"
.\run_one_type.cmd "Scoring Quantitative"
.\run_one_type.cmd "Temporal Transaction"
```

Use `-OutputRoot` to begin a fresh batch without overwriting or conflicting
with an earlier run's report manifest:

```powershell
.\run_pipeline_v2\scripts\run_question_types_v2.ps1 -Type 'Benchmark' -Workers 1 -OutputRoot 'pipelien_output_parallel_run'
```

The batch runner uses `improvement6/.env` by default. To use a different
credential/configuration file, pass `--env-file <path>` to the Python runner.

For every type, the output folder contains the existing grader-compatible CSV
files plus `raw_pipeline_v9.jsonl` and `raw_pipeline_v9_debug.jsonl`. The JSONL
files preserve large ground-truth and result tables without Excel cell limits.
The 216 complete reference answers in `datatset/216_questions_full_results.json`
are joined by `question_id` before each type runs.

## September 30 memory fix

The default output root is now `pipelien_output/run_v5_memory_safe`. Older
results are preserved: changes to source code require a new report identity.
Repeat the same command with unchanged source, inputs, limit and offset to
resume this new run. Use `-Limit 1` and a separate `-OutputRoot` for a smoke test.

Eight distinct types may run together. Only duplicate writers to the same
report are blocked. Each process uses one question worker and one numerical
library thread; numerical thread limits are set before pandas/NumPy imports.
On this workstation, measured startup private memory fell from roughly
447 MB to 94 MB per pipeline (around 100 MB if openpyxl is also imported).
The workbook preparation process now exits before the pipeline starts; the
supervisor no longer retains a second pandas/Excel allocation per terminal.

Detailed output and tracebacks go to `.runtime/logs/pipeline_*.log`; terminals
show launch and per-question progress. Inspect a log with `Get-Content <path>
-Tail 40`. Before startup and each question, the runner pauses if available
physical memory falls below 128 MB or available commit memory below 1 GB.
Close unused applications to let it resume, or press Ctrl+C. These checks
cannot prevent an allocation spike during a question or memory use by other apps.

The Windows event log reported low virtual memory at 21:26:27 on September 30,
followed by VS Code `reason: oom` at 21:26:46. Both versions used approximately
447 MB on import before this fix; the v2 launcher added an extra resident
Excel process. The existing Fuseki server uses `-Xmx4G` in both launchers;
that is a maximum heap size, not its current memory usage.
