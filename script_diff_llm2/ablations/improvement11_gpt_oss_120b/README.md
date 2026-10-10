# Improvement 11 — GPT-OSS 120B

The original `improvemnt11kgfixed` folder was exported from freshly fetched `origin/main`, commit `9ba4be150a7c8497dc33fe8c751605bf93fece09`. Its latest folder commit is `4cd0bb5723871bf0bfe9a3addbde7ff6286c75c2` (7 October 2026, 01:40:11 IST). All 125 tracked source and asset files remain byte-for-byte unchanged and are verified against `source_manifest.json` before and after launches. The active `kritik` checkout was preserved; no main-branch merge was performed over existing local changes.

This is the original KG-only workflow: one question at a time, simple knowledge compilation, query understanding, contract checks, and specialist consultation enabled. Only paths, credentials and the GPT-OSS model connection are configured externally. It uses its own ontology, KG, documents, workbook and reference-answer file from the snapshot. No Improvement 10 or hybrid data/context/cache is used. The local Fuseki executable is reused as server software; the graph loaded is exclusively Improvement 11's instance file.

Run these commands from `script_diff_llm2`.

In a separate terminal, start the dedicated graph server:

```bash
bash ablations/improvement11_gpt_oss_120b/start_fuseki.sh
```

Validate the running KG, then run all 1,000 questions:

```bash
bash ablations/improvement11_gpt_oss_120b/run_raw.sh --check-kg
bash ablations/improvement11_gpt_oss_120b/run_raw.sh --run-tag run_01
```

The same raw command resumes the original compatible report. To retry only saved execution errors:

```bash
bash ablations/improvement11_gpt_oss_120b/run_raw.sh --run-tag run_01 --retry
```

Offline validation and optional knowledge preparation:

```bash
bash ablations/improvement11_gpt_oss_120b/run_raw.sh --check
bash ablations/improvement11_gpt_oss_120b/run_raw.sh --prepare-knowledge
```

Preparation is also automatic during the full run; compatible cached knowledge is reused. The original pipeline keeps its cache in `source/improvemnt11kgfixed/.runtime/knowledge_v3_kg`.

The raw report is `runs/gpt_oss_120b/run_01/raw_pipeline.csv`. Native JSONL, debug and telemetry artifacts are produced by the original pipeline. No grader is launched.

Credentials are read from the existing shell or local `.env` files, including the historical GPT-OSS credential file. Only credential and connection fields are imported; previous experiment configuration is discarded. No API keys are copied into the source snapshot or manifests.

## Four parallel question workers

Stop the sequential raw launcher with Ctrl+C and wait for it to exit. Keep Fuseki running. Then use:

```bash
/usr/bin/python3 -u -B ablations/improvement11_gpt_oss_120b/run_parallel.py --run-tag run_01 --workers 4
```

The launcher prepares or reuses the original cache once, validates its explicit selection using the original code, then starts four independent original pipeline processes. Each process receives an immutable question shard, its own output report, and the same cache. Already saved sequential rows are retained in a seed report; only unattempted questions are assigned to workers. Saved error rows are retained, rather than silently retried.

The combined report is:

```text
ablations/improvement11_gpt_oss_120b/runs/gpt_oss_120b/run_01/parallel_workers4/raw_pipeline.csv
```

It is saved atomically approximately every 10 seconds in original question order, with unknown and duplicate IDs rejected. Individual outputs, logs, debug JSONL and native telemetry are in `parallel_workers4/worker_01` through `worker_04`. Repeat the identical parallel command to resume. After switching, use this parallel launcher to continue the experiment; the earlier sequential report remains preserved and is not updated by the parallel workers. No grader starts.

Offline checks:

```bash
/usr/bin/python3 -u -B ablations/improvement11_gpt_oss_120b/run_parallel.py --run-tag run_01 --workers 4 --check
```

Worker count does not change the pipeline prompts or operators. Concurrent API requests can still cause throttling or timeouts, and model responses are not guaranteed to be identical. The original cache review status is advisory: the launcher preserves the original acceptance policy and reports that status rather than imposing a new review requirement. The existing run's cache reported `unavailable` during implementation; it was retained unchanged.

### Temporarily reduce concurrency without repartitioning

Stop the existing controller and wait for its child processes to exit, then run:

```bash
/usr/bin/python3 -u -B ablations/improvement11_gpt_oss_120b/run_parallel.py --run-tag run_01 --workers 4 --max-active-workers 1
```

This retains the existing four shard folders and combined report, but runs only one process at a time. It resumes that shard, then advances to the next shard when it finishes. Omitting `--max-active-workers` restores the original concurrency on the next restart; never start both controllers together. The temporary concurrency limit is a scheduling setting and does not change the source, cache or immutable question assignments. The original worker resume policy still applies: retryable execution failures, including transient errors, may be retried on restart. This concurrency switch adds no separate retry policy.
