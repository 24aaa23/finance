# Improvement 11 KG-only: Azure continuation

Uses the unchanged Improvement 11 snapshot and only its ontology, KG instances,
domain introduction, business rules and 1000-question dataset. No SQL backend or
main-hybrid data assets are introduced. GPT-OSS is called through Azure using the
endpoint, deployment and key saved in `../azure_gpt_oss_120b/azure.env`.

The native client retains its existing environment-variable names internally;
the launcher explicitly supplies Azure values instead of Bedrock values. This
does not change pipeline prompts, operators or calculations. Each worker has
`TEST_MAX_WORKERS=1`, its own immutable question shard and its own report.

## Continue the previous experiment

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
/usr/bin/python3 -u -B \
  ablations/improvement11_gpt_oss_120b/run_azure_parallel.py \
  --source-run-tag run_01 --run-tag azure_run_01 \
  --workers 4 --max-active-workers 2
```

Four shards are scheduled with two active processes; one query executes at a time
per process. Use `--max-active-workers 4` for four concurrent queries, or `1` to
reduce request pressure. Stop the launcher before changing its active-worker
limit, then keep the same four shards and Azure run tag.

Fuseki must serve Improvement 11's KG on port 3041. If needed, start it in a
separate terminal:

```bash
bash ablations/improvement11_gpt_oss_120b/start_fuseki.sh
```

The first invocation preserves only `PIPELINE_SUCCESS` rows from the earlier
Bedrock report as a seed. It queues every other saved status first, including
transient, crash, pre-scan, scan and Final Spec failures; then queues unanswered
questions. All questions remain assigned once, and merged results retain their
original dataset order. Original Bedrock reports are never edited.

Repeat the same command to resume. For each Azure worker, successful rows remain
saved. Any non-success rows are backed up and queued again on restart; this also
works when a shard already has a saved status for every question. Failed queries
are attempted once per launcher invocation, alongside native within-query repair
and SDK retry behavior. There is no infinite restart loop. Saved-row counts can
decrease while failed rows await re-execution.

## Context and provenance

The existing Bedrock-prepared 30-rule knowledge pack is copied, unchanged, into
this experiment and validated with the original explicit-cache validator. The
copy receives its own Azure input/model binding; the original cache is untouched.
Its review status remains the baseline's reported status, not an assertion that
completeness review succeeded. No new context-preparation model call is required.

The combined report is intentionally a **mixed-provider continuation**: retained
Bedrock successes plus newly evaluated Azure questions. `seed.csv` contains the
retained rows, worker reports contain Azure rows, and `azure_manifest.json`
records source-report/cache hashes, the original commit, Azure deployment and
endpoint, and provider provenance. Do not present it as a fresh all-Azure run.

Output:

```text
ablations/improvement11_gpt_oss_120b/runs/azure_gpt_oss_120b/azure_run_01/parallel_workers4/raw_pipeline.csv
```

Logs and error-retry backups live in `worker_01` through `worker_04`. No grader
starts. Changing source results, deployment, endpoint or fixed shard count requires
a new Azure run tag, while changing only active-worker concurrency does not.

Offline planning and preparation checks:

```bash
/usr/bin/python3 -u -B ablations/improvement11_gpt_oss_120b/run_azure_parallel.py --check
/usr/bin/python3 -u -B ablations/improvement11_gpt_oss_120b/run_azure_parallel.py --prepare-only
```

`--check` makes no output changes or model calls; `--prepare-only` creates the
continuation shards, copies/validates the existing cache and stops before query
inference. Neither starts a full experiment.

## Change shard count while retaining completed answers

Stop the previous controller/workers first. Supply its combined report explicitly
and use a new run tag; otherwise selecting eight shards can fall back to an older
sequential Bedrock report. `--source-report` may be repeated to retain successes
from multiple stopped runs. IDs and question text are validated. The first success
for an ID is retained; a later success supersedes an earlier failure. All source
reports remain untouched, and their hashes are recorded in the new manifest.

```bash
/usr/bin/python3 -u -B ablations/improvement11_gpt_oss_120b/run_azure_parallel.py \
  --source-report "$PWD/ablations/improvement11_gpt_oss_120b/runs/azure_gpt_oss_120b/azure_run_01/parallel_workers4/raw_pipeline.csv" \
  --source-report "$PWD/ablations/improvement11_gpt_oss_120b/runs/azure_gpt_oss_120b/azure_run_01/parallel_workers8/raw_pipeline.csv" \
  --run-tag azure_resume8_01 --workers 8 --max-active-workers 8
```

At migration this retains 301 unique successful rows and shards 699 remaining
questions across eight processes. Repeat the same command to resume that new
folder. Do not restart the source runs while the continuation uses their hashes.
