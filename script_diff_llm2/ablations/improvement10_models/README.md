# Improvement 10: four model experiments, original SQL pipeline

This folder contains an unchanged snapshot of `origin/main` commit
`9ce5a6d99c96f3c17dda0b98ec8edc0c11bd2380`, restricted to `improvement10`.
`source_manifest.json` records all 128 original files; the launcher verifies their
hashes before and after execution. No original operator, prompt, rules, grader,
database or dataset file has been edited. New launchers live outside the snapshot.

Models: GPT-OSS 120B, DeepSeek V3.2, Gemma 3 27B IT and Kimi K2 Thinking.
Only the context-enabled configuration is run. The snapshot's own domain intro,
business-rules addendum, YAML metadata, SQLite database, question workbook and
216 full-answer overrides are used. No Fuseki or KG files are required.

The launcher uses the original `run_all.py` dataset preparation and launches the
original `run.py`. It preserves the supplied configuration: simple knowledge
compilation, consultation on, default query understanding and contract checks,
original deterministic explanation and retry policy, no shuffle, and **one question
worker per experiment**. It sets the existing model/endpoint environment variables
so every model stage, including knowledge preparation, uses the selected model.
It does not call `run_all.main`, because that function hardcodes GPT-OSS.
All four models use the original OpenAI-compatible client with their selected
Bedrock endpoints. The original pipeline files and output budgets remain unchanged.
The earlier Llama adapter and run artifacts are retained for inspection but are
not used by these four experiments.

## Credentials and endpoints

The existing `script_diff_llm2` local environment loader supplies credentials;
credential values are never printed or written to manifests.

| Alias | Default model ID | Endpoint | Credentials |
|---|---|---|---|
| `gpt_oss_120b` | `openai.gpt-oss-120b-1:0` | `BEDROCK_BASE_URL`, otherwise Bedrock Runtime in configured region | `AWS_BEDROCK_API_KEY`, legacy GPT-OSS key or `BEDROCK_API_KEY` |
| `deepseek_v3_2` | `deepseek.v3.2` | `BEDROCK_MANTLE_BASE_URL`, otherwise Bedrock Mantle | `BEDROCK_MANTLE_API_KEY`, `AWS_BEDROCK_API_KEY` or `BEDROCK_API_KEY` |
| `gemma_3_27b_it` | `google.gemma-3-27b-it` | Same Mantle configuration | Same Mantle configuration |
| `kimi_k2_thinking` | `moonshotai.kimi-k2-thinking` | Same Mantle configuration | Same Mantle configuration |

The existing AWS region settings select the region, defaulting to `us-east-1`.
No separate provider key is required for Kimi. Each model keeps its own context cache.

## Run all four concurrently

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2

/usr/bin/python3 -u ablations/improvement10_models/run_parallel.py \
  --run-tag run_01
```

This starts four experiment processes simultaneously, each using one question
worker. It requires all four connections to be configured before starting. There
are no without-context conditions and no graders. Repeat the same command to use
the original resume logic. Do not start a second copy while the first is running.
The baseline's native report locks protect each report. Source/model/path changes
require a fresh tag; use a separate tag when changing `--limit` for a pilot.

Offline checks (no API calls; no credentials required):

```bash
/usr/bin/python3 -u ablations/improvement10_models/run_parallel.py --check
```

Inspect configurations only:

```bash
/usr/bin/python3 -u ablations/improvement10_models/run_parallel.py --dry-run
```

## Run one experiment

```bash
bash ablations/improvement10_models/run_raw.sh gpt_oss_120b --run-tag run_01
bash ablations/improvement10_models/run_raw.sh deepseek_v3_2 --run-tag run_01
bash ablations/improvement10_models/run_raw.sh gemma_3_27b_it --run-tag run_01
bash ablations/improvement10_models/run_raw.sh kimi_k2_thinking --run-tag run_01
```

Those four lines run sequentially if pasted together. Use `run_parallel.py` to
start them concurrently. Single-model overrides accept `--base-url`, `--model-id`
and `--api-key-env NAME`. The parallel launcher uses the model-specific environment
variables above, rather than one shared endpoint override for all models.

## Outputs and logs

```text
ablations/improvement10_models/
  source/improvement10/              unchanged source and original assets
  source_manifest.json               pinned source hashes
  runs/<model>/run_01/
    launcher_manifest.json
    input_questions.jsonl            prepared by the original dataset code
    raw_pipeline.csv
    raw_pipeline.jsonl
    raw_pipeline_debug.jsonl
    knowledge_cache/                independent per experiment
    _telemetry/                     original timing and token measurements
    launcher.log
  launcher_logs/run_01/<model>.log   parent launcher console output
```

The original pipeline redirects detailed operator logs into
`source/improvement10/.runtime/logs/`; the launcher log prints the exact path for
each process. Runtime-created files do not replace the 128 tracked source files.
The original telemetry already records model request durations and token usage;
no measurement patch is needed. Reference answers remain in the original input
format for evaluation; this wrapper neither changes nor re-audits the baseline's
internal inference boundary. Treat the included domain rules as this baseline's
original rules, not as the generic v5 terminology-only context condition.

## Add Kimi while the other three experiments are running

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash ablations/improvement10_models/run_raw.sh kimi_k2_thinking --run-tag run_01
```

This starts only Kimi and leaves the three existing processes alone. Use the
four-model parallel command when those existing processes have finished or stopped.
Do not launch duplicate writers to their current run folders.

## Four question workers per model (16 processes)

Stop the existing `run_parallel.py` and Kimi `run_raw.py` with Ctrl+C in their
terminals and wait for their children to exit. Then run:

```bash
/usr/bin/python3 -u ablations/improvement10_models/run_sharded.py --workers 4 --run-tag run_01
```

The external launcher leaves all original code unchanged, freezes existing saved
rows (including failures), partitions only unsaved questions into four disjoint
batches per model, and uses each model's exact reviewed cache with the original
`--knowledge-cache` option. Each question follows the original sequential agent
workflow. No graders start. Identical commands resume the fixed worker batches.
The launcher refuses to start while original pipeline processes remain active.

Combined reports appear at `runs/<model>/run_01/parallel_workers4/raw_pipeline.csv`,
updated every ten seconds and at shutdown. Original reports remain preserved.
Each `worker_01` through `worker_04` folder retains its own native telemetry,
CSV, JSONL, debug CSV and log. The combined CSV retains the original per-question
token and timing columns. Knowledge preparation timing remains in the original run.
Question processing order changes; there is no guarantee of identical model answers
or fourfold speedup under provider quotas. Saved failures are not retried by this switch.
Do not subsequently run the original sequential launcher against this tag: it cannot
see the new worker outputs. Use only the sharded launcher to resume this experiment.

Offline preflight: append `--check` to the sharded command.

## Llama 3.1 405B on Bedrock, four workers

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash ablations/improvement10_models/run_llama_405b.sh run_01
```

This first runs the unchanged simple knowledge preparation/review using Llama
405B, then starts four native pipeline processes sharing that model's validated
cache. Repeating the command reuses the preparation cache and resumes fixed
question shards. No other models or graders start. Existing graders can continue.
Stop any remaining original raw/sharded runner before using this launcher.

Default model is `meta.llama3-1-405b-instruct-v1:0`; endpoint is native
Bedrock Runtime in `us-west-2`. The earlier us-east-1 cross-region default was
rejected by Bedrock and has been corrected. Overrides are
`BEDROCK_LLAMA_405B_MODEL` and `BEDROCK_LLAMA_405B_BASE_URL`. Existing Bedrock
bearer/API credentials are reused. The external Converse adapter preserves
system/user prompt text, parameters and native token usage. Original code hashes
remain unchanged. Llama's domain preparation budget is explicitly 4096 tokens,
recorded in both manifests; other model settings retain their original defaults.
AWS documents a 4K maximum output and legacy lifecycle for this model. Account
access and regional availability must permit inference. Offline checks do not
verify live access. If complete preparation cannot fit, the script stops and does
not substitute another model's cache, silently truncate rules or switch compiler.

Combined report:
`runs/llama_3_1_405b/run_01/parallel_workers4/raw_pipeline.csv`.
Worker telemetry and logs are in that folder's `worker_01` through `worker_04`
subfolders. Preparation logs/telemetry are printed by the original runner.

## Qwen3-Coder 480B, four workers

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash ablations/improvement10_models/run_qwen3_coder_480b.sh run_01
```

The script uses `qwen.qwen3-coder-480b-a35b-instruct` on the existing Bedrock
Mantle connection and credentials. A one-token live connection probe succeeded.
It prepares/reviews this model's own context once with the original simple
compiler, then runs four independent workers on the original 1000 questions.
Subsequent runs reuse the cache and resume fixed shards. No graders start.
All original code/assets remain unchanged. Domain preparation's output budget is
explicitly 16384 (instead of original 32768), recorded in both launcher and
sharding manifests to accommodate Bedrock's documented 16K output maximum.
It does not truncate source documents or substitute another model's cache.
Grading processes can continue separately; stop other raw launchers first.

Combined report:
`runs/qwen3_coder_480b/run_01/parallel_workers4/raw_pipeline.csv`.
Native worker telemetry/logs are saved in `worker_01` through `worker_04`.
