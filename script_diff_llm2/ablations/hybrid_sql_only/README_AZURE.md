# Azure GPT-OSS SQL-only continuation

This launcher runs the main pipeline's SQL-only ablation through the existing
Azure deployment. It does not change the core pipeline or start a grader.

Credentials load automatically from `../azure_gpt_oss_120b/azure.env`. Use the
same endpoint, deployment and key already configured there.

## Fresh run of all 1000 questions

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2

/usr/bin/python3 -u -B ablations/hybrid_sql_only/run_azure_parallel.py \
  gpt_oss_120b without_context --fresh \
  --run-tag azure_fresh_dag_retry_01 \
  --workers 4 --max-active-workers 4
```

`--fresh` imports no earlier answers and does not require a source run. Initially,
all 1000 questions are assigned to four 250-question shards. All generated answers
come from Azure. Repeat this exact command, including `--fresh`, to resume the
same new experiment: its successful rows are retained and failures are retried.
The flag does not delete or reset that experiment. Use another new run tag to
start another full experiment. Replace `without_context` with `with_context` to
enable the existing optional context preparation.

## Continue an older Bedrock run

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2

/usr/bin/python3 -u -B ablations/hybrid_sql_only/run_azure_parallel.py \
  gpt_oss_120b with_context \
  --source-run-tag run_01 --run-tag azure_run_01 \
  --workers 4 --max-active-workers 4
```

Four fixed shards run concurrently. Each process handles one question at a time,
with one DAG worker. SQL-only mode skips KG loading and Fuseki.

The source is:

`runs/gpt_oss_120b/with_context/run_01/raw_pipeline.csv`

Its 256 `PIPELINE_SUCCESS` rows are preserved; its 744 failed rows are retried.
These counts describe the source at setup, and indicate execution status, not
answer correctness. Source files are never overwritten.

The combined output is:

`runs/azure_gpt_oss_120b/with_context/azure_run_01/raw_pipeline.csv`

It contains retained Bedrock answers and newly generated Azure answers. The
manifest records this provenance; this is a continuation, not a fresh experiment
in which every answer was generated on Azure.

Run the same command again to resume. It retains Azure successes and backs up
and retries saved Azure failures, including non-API errors. Each launch makes
one benchmark attempt per pending question, in addition to the pipeline's
existing internal retries and repairs. Errors appear in terminal progress and
each `worker_XX/pipeline.log`. Completed shards make no new question requests.

With-context mode prepares or reuses an Azure-specific SQL-only context cache
under `context_cache/azure_gpt_oss_120b`. It uses the main pipeline's domain intro
and business-rules inputs and existing validation/quarantine policy. This does
not activate quarantined evaluation material. Preparation must succeed before
question workers launch; its log is `preparation/pipeline.log`.

The SQL database, 1000-question workbook, reference overrides and Azure model
configuration are the existing main-pipeline assets. No Improvement10/11 context
or data is imported. Environment credentials are not written to the manifest.

For an offline input check, append `--check` to the command. This makes no API
calls and writes no run output. To run without context, replace `with_context`
with `without_context`; the corresponding prior source run must exist.

`--workers` fixes the shard structure and must remain unchanged when resuming.
`--max-active-workers` can change between launches (for example, to `2`) while
retaining those four shards. Stop an existing launcher before resuming the same
Azure output folder; the folder lock prevents duplicate writers.
