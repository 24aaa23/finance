# SQL-only ablation of the main hybrid pipeline

This ablation uses the main pipeline, not Improvement 10 or 11. It retains decomposition, QuerySpec, SQL generation, validation, repairs, DAG bindings, set operators, explanation, benchmark reference overrides and model stage configuration. The backend availability is the ablation variable: only SQL metadata is exposed to decomposition, every retrieval subquery runs on SQLite, and KG loading/Fuseki checks are skipped. Generated non-SQL plans are rejected and use the original full-question fallback, restricted to SQL. Without the opt-in `PIPELINE_BACKEND_MODE=sql_only`, the main pipeline retains its normal hybrid behavior.

Four separate processes each run one question at a time. The 1,000 questions are assigned to four fixed 250-question shards. Per-query DAG parallelism remains the existing setting (two independent nodes); question worker count inside each process is one. Outputs, logs, and resume state are isolated. Results merge by question ID approximately every 10 seconds into a single report. There is no grader launch and no paid run is automatically started during setup.

## Run

From `script_diff_llm2`:

```bash
bash ablations/hybrid_sql_only/run_raw.sh gpt_oss_120b without_context --run-tag run_01 --workers 4
```

Optional corresponding with-context condition:

```bash
bash ablations/hybrid_sql_only/run_raw.sh gpt_oss_120b with_context --run-tag run_01 --workers 4
```

With context, preparation runs once before workers start; subsequent runs reuse the compatible SQL-only context cache. It uses the same domain intro and business-rules document as the hybrid ablation, with the same quarantine and review policies. The context is prepared against SQL metadata alone; a previous hybrid cache is not reused. Evaluation-scoped business-rule documents remain quarantined.

Other supported model aliases: `deepseek_v3_2`, `gemma_3_27b_it`, `kimi_k2_thinking`, and `qwen3_coder_480b`. Replace the first model argument to compare the same model across hybrid and SQL-only runs.

Offline validation:

```bash
bash ablations/hybrid_sql_only/run_raw.sh gpt_oss_120b without_context --check
```

The identical run command resumes compatible worker reports using the main pipeline's existing resume policy. Source, assets, model, context settings and worker count are recorded; incompatible settings require a new run tag. Do not compare this run against a hybrid result from a different source revision without recording that difference. Worker input files must remain unchanged. A combined report is complete only when all 1,000 unique rows are saved; failures and mismatches are not silently discarded.

## Assets and outputs

Inputs retain the main hybrid ablation paths:

- SQL: `historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db`
- Queries: `wealth_management_1000_test_set_questions.xlsx`
- Evaluation reference overrides: `216_questions_full_results.json` (same existing benchmark reporting boundary)
- Optional domain intro: `domain_intro.prompt`
- Optional business rules: `phase0_business_rules.md`
- Model/configuration: the matching files in `ablations/v5_test1000/configs/`.

KG asset paths remain recorded by the inherited configuration, but KG files are not loaded or queried in SQL-only execution. No Fuseki server is needed.

Combined report:

```text
ablations/hybrid_sql_only/runs/gpt_oss_120b/without_context/run_01/raw_pipeline.csv
```

Worker folders: `worker_01` through `worker_04`, each with `questions.csv`, `raw_pipeline.csv`, and `pipeline.log`. For other models or conditions, the corresponding path segment changes. The SQL-only context cache is isolated at `ablations/hybrid_sql_only/context_cache/<model>/`.

Model responses can vary and concurrent requests may cause throttling; worker count is an execution setting, not a guarantee of identical answers or fourfold speedup.

## Live error reporting and API-failure retries

Run the existing four shards with two active processes:

```bash
bash ablations/hybrid_sql_only/run_raw.sh gpt_oss_120b with_context --run-tag run_01 --workers 4 --max-active-workers 2
```

The terminal checks outputs and logs approximately every two seconds. Newly saved rows display time, worker, question ID, status and elapsed seconds. Failed rows also show the failure stage, detailed error and whether the error is classified as a transient API failure. In-flight API errors appear as `API WARNING`; a warning can still be followed by a successful repaired query. Worker logs retain complete diagnostics.

By default, restarting retries saved failures that contain explicit transient API evidence, including rate limits, connection failures, timeouts and temporary server errors. Successful rows and semantic failures remain skipped. Each failed query is scheduled once per restart; this does not create an infinite immediate retry loop. Native per-call retry behavior remains unchanged. Previous worker CSVs with retryable rows are backed up under `worker_XX/backups/<timestamp>/raw_pipeline.csv` before processing. Native resume may temporarily remove pending retry rows from the live report; the backup retains their previous results until they are replaced.

The retry selection is an ablation-local entry wrapper in `run_worker.py`; it does not modify the shared main pipeline's resume policy or the grader. Execution options and wrapper hashes are recorded in `execution_options.json`.

To skip saved API failures instead, append `--no-retry-api-errors`. Any failures that recur remain saved and visible; a later restart can retry them again. Keep account-level concurrency low if throttling recurs.
