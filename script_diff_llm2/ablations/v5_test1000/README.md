# V5 model/context ablations on the fixed 1,000-question benchmark

These launchers run the existing v5 pipeline against the original SQL database,
KG files and 1,000-question workbook. Raw launchers never start grading. No
benchmark or grader API calls were made while creating this ablation setup.

For the latest generic reliability fixes, pilot windows, fresh-run commands and
parallel grading, see [README_RELIABILITY_V6.md](../../README_RELIABILITY_V6.md).
New raw runs use the version label `ablation-generic-reliability-v6`.

## Run layout

```text
ablations/v5_test1000/
  configs/models/                    four model configs
  configs/experiments/               eight model/condition configs
  context_cache/<model>/             model-specific document preparation caches
  runs/<model>/without_context/run_01/
  runs/<model>/with_context/run_01/
  run_raw.sh                        raw-only launcher
  run_raw.py                        fixed sources, model settings and resume guard
  grade_only.py                     manual GPT-5 Mini grader wrapper
```

Each run saves `raw_pipeline.csv`, `pipeline.log`, and `run_manifest.json`.
Manual grading saves `graded_pipeline_gpt_5_mini.csv` in that same run folder.
The four model aliases are `deepseek_v3_2`, `gemma_3_27b_it`,
`kimi_k2_thinking`, and `gpt_oss_120b`.

## Fixed sources and settings

All paths below are relative to the absolute `script_diff_llm2` directory:

| Setting | Value |
| --- | --- |
| Questions | `wealth_management_1000_test_set_questions.xlsx` |
| Sheet selection | `ALL_BENCHMARK_SHEETS` |
| Reference overrides | `216_questions_full_results.json` |
| SQLite | `historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db` |
| KG schema | `data/kg/wealth_management_diverse_schema.ttl` |
| KG instance file | `data/kg/wealth_management_diverse_kg.ttl` |
| RDF alias map | `data/kg/rdf_id_alias_map.json` |
| Fuseki | `http://127.0.0.1:3030/wealth/query` |
| Query limit / offset | 1000 / 0 |
| Shuffle seed | 4043113952 |
| Query / DAG workers | 4 / 2 |
| Report save interval | Every completed question |
| Explanation | Existing deterministic explanation mode |

The launcher prints resolved absolute source paths and endpoint/model settings.
It overrides inherited source variables so another dataset cannot accidentally
be selected. Fuseki must already serve the corresponding wealth graph.

Every LLM stage of the raw pipeline inherits the selected raw model, including
classification, decomposition, retrieval, QuerySpec, generation, validation,
refinement and document preparation. Deterministic explanation remains identical
across conditions; the grader model is not used by the raw runner.

## Provider configuration

Defaults use the existing Bedrock OpenAI-compatible setup:

| Model | Bedrock API model ID | Endpoint family |
| --- | --- | --- |
| DeepSeek V3.2 | `deepseek.v3.2` | Mantle |
| Gemma 3 27B IT | `google.gemma-3-27b-it` | Mantle |
| Kimi K2 Thinking | `moonshotai.kimi-k2-thinking` | Mantle |
| GPT-OSS 120B | `openai.gpt-oss-120b-1:0` | Runtime, matching existing v5 |

The normal local environment file loader is used. Mantle credentials are read
from `BEDROCK_MANTLE_API_KEY`, `AWS_BEDROCK_API_KEY` or `BEDROCK_API_KEY`;
GPT-OSS retains the existing credential names. `ABLATION_API_KEY` overrides those
when explicitly supplied. Never put credential values in run manifests or YAML.

Endpoint priority is `--base-url`, then `ABLATION_BASE_URL`, then the model's
normal `BEDROCK_MANTLE_BASE_URL`/`BEDROCK_BASE_URL`, then a region-derived URL.
Region priority is `BEDROCK_REGION`, `AWS_REGION`, `AWS_DEFAULT_REGION`, then
`us-east-1`. Ensure your account has access and quota for the exact selected model.

For another OpenAI-compatible provider, supply both its endpoint and model ID:

```bash
bash ablations/v5_test1000/run_raw.sh gemma_3_27b_it without_context \
  --base-url https://your-provider.example/v1 \
  --model-id YOUR_PROVIDER_MODEL_ID \
  --run-tag other_provider_01
```

Set `ABLATION_API_KEY` securely in your environment for that provider. Defaults do
not silently substitute a different model. Official endpoint/model references:
[DeepSeek](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-deepseek-deepseek-v3-2.html),
[Gemma](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-google-gemma-3-27b-pt.html),
[Kimi](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-moonshot-ai-kimi-k2-thinking.html).
The AWS Gemma page title says PT, but its programmatic model ID is the requested
`google.gemma-3-27b-it`.

## Eight raw-only commands

Run from:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
```

Without context:

```bash
bash ablations/v5_test1000/run_raw.sh deepseek_v3_2 without_context
bash ablations/v5_test1000/run_raw.sh gemma_3_27b_it without_context
bash ablations/v5_test1000/run_raw.sh kimi_k2_thinking without_context
bash ablations/v5_test1000/run_raw.sh gpt_oss_120b without_context
```

With eligible database context:

```bash
bash ablations/v5_test1000/run_raw.sh deepseek_v3_2 with_context
bash ablations/v5_test1000/run_raw.sh gemma_3_27b_it with_context
bash ablations/v5_test1000/run_raw.sh kimi_k2_thinking with_context
bash ablations/v5_test1000/run_raw.sh gpt_oss_120b with_context
```

Execute individually or sequentially; these are eight separate experiments, not
an instruction to launch eight processes simultaneously. Each full command can
be repeated to resume saved question rows. The normal v5 error/stale-version
retry rules still apply; an interrupted individual question may be repeated.

## What “with context” means

Defaults supply `domain_intro.prompt` and `phase0_business_rules.md` as document
paths, but Phase 0 is evaluation-scoped and remains quarantined. It is not used
for inference. Eligible, schema-grounded qualitative terminology can activate
without approval. Numeric/operational definitions and policies require independent
hash-bound approval. This is a **context ablation**, not evidence that the disputed
Phase 0 rules have been incorporated.

Context preparation uses each selected raw model and separate caches. The first
startup prepares context; matching later startups use that model's cache.
`DOMAIN_CONTEXT_REQUIRED=1` stops before benchmark questions if no entries activate.
Models can extract different context, so this setup measures the complete
model-specific preparation-plus-answering pipeline. It does not hold extracted
context identical across models. Record the context review/trace alongside results.

To use a separately authored business-rules Markdown file:

```bash
bash ablations/v5_test1000/run_raw.sh deepseek_v3_2 with_context \
  --business-rules /absolute/path/to/source_owned_business_rules.md \
  --approval-file /absolute/path/to/deepseek_context_approval.json \
  --run-tag approved_rules_01
```

Only independently approved, nonconflicting, schema-valid entries are eligible.
An approval file is tied to the document/schema/preparation-model fingerprint;
prepare and review candidates for each model before approving computational rules.
See [context approval instructions](../../docs/domain_context.md). Omitting
`--approval-file` does not auto-approve policies. `--domain-intro ''` or
`--business-rules ''` omits that document explicitly.

## Dry run, repeats and resume protection

```bash
bash ablations/v5_test1000/run_raw.sh kimi_k2_thinking with_context --dry-run
bash ablations/v5_test1000/run_raw.sh kimi_k2_thinking with_context --run-tag run_02
```

Dry run inspects configuration without model or grader calls. A new run tag creates
a fresh experiment directory. The resume manifest records source hashes, endpoint,
model ID/config, context/approvals, worker counts and pipeline implementation hashes.
It refuses to resume a nonempty report after those settings change. It does not
snapshot the live Fuseki graph, SDK versions, provider deployment changes or every
inherited runtime variable: keep them fixed for controlled comparisons and use a
new run tag after changes. Do not use results from different configurations together.

## Manual grader only: GPT-5 Mini

No raw command invokes this wrapper. Run it yourself after the corresponding raw
report is complete and your OpenAI API quota is available:

```bash
/usr/bin/python3 -u ablations/v5_test1000/grade_only.py deepseek_v3_2 without_context
```

Replace the model alias and condition to grade another folder; add the same
`--run-tag` used by its raw run. Inspect without API calls using `--dry-run`.
This wrapper imports the original grader without changing its file, sets the
requested model to `gpt-5-mini` after its .env loader, and calls its existing
comparison/resume functions. It preserves the original grading logic. Output is
separate from prior GPT-5.6 reports. `OPENAI_API_KEY` is required; `--base-url` can
select an explicitly configured grader endpoint.
[Official GPT-5 Mini documentation](https://developers.openai.com/api/docs/models/gpt-5-mini).

## Context preparation output limits

Context preparation requests an explicit output budget of 16,384 tokens. A response
ending with `finish_reason=length` is never activated; preparation retries once
with 32,768 tokens and asks for fewer concise entries. This addresses thinking models
that exhaust the endpoint default before producing final JSON. These budgets apply
only to context preparation, not benchmark question answering.

Optional overrides are `DOMAIN_CONTEXT_MAX_TOKENS` and
`DOMAIN_CONTEXT_RETRY_MAX_TOKENS`. The retry budget must be at least the initial
budget and both must be positive. The context run manifest records these settings.
Successful prepared context is reused; failure diagnostics are not a valid cache.

To retry the Kimi startup failure before any raw CSV was created:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
DOMAIN_CONTEXT_MAX_TOKENS=16384 DOMAIN_CONTEXT_RETRY_MAX_TOKENS=32768 \
  bash ablations/v5_test1000/run_raw.sh kimi_k2_thinking with_context
```

No cache deletion is needed for this failure. Runs already containing raw rows
remain subject to the configuration/code resume guard; use a fresh run tag for
those after implementation changes. Evaluation-scoped business-rule documents
remain quarantined regardless of the output budget.
