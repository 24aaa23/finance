# Main hybrid pipeline: GPT-6.1 Sol

Runs the existing SQL+KG pipeline on the fixed 1000-question workbook using
`gpt-6.1-sol` through the OpenAI Chat Completions API. No grader starts.
Shared core pipeline, prompts and existing model launchers are unchanged.

The existing project environment loader supplies `OPENAI_API_KEY`. The default
endpoint is `https://api.openai.com/v1`; `OPENAI_BASE_URL` can override it.
The launcher explicitly restores hybrid mode even if your shell was configured
for a SQL-only experiment. SQL database, KG schema, instance file and RDF aliases
are the main pipeline's existing assets, listed by the launcher at startup.
Fuseki must serve that KG at `http://127.0.0.1:3030/wealth/query`. The Improvement
11 server on port 3041 serves a different experiment and does not replace it.

If the main Fuseki endpoint is not running, start it in a separate terminal:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash ablations/openai_gpt_6_1_sol/start_fuseki.sh
```

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash ablations/openai_gpt_6_1_sol/run_raw.sh without_context \
  --run-tag run_01 --workers 2 --dag-workers 1
```

With optional domain-context preparation and reuse:

```bash
bash ablations/openai_gpt_6_1_sol/run_raw.sh with_context \
  --run-tag run_01 --workers 2 --dag-workers 1 \
  --domain-intro "$PWD/domain_intro.prompt" \
  --business-rules "$PWD/phase0_business_rules.md"
```

The existing context review/quarantine policy still applies. Supplying a document
does not guarantee its policies will be activated. Context preparation fails
before the benchmark if required context cannot be activated.

Repeat the same command to resume saved rows under the existing core resume
policy. Outputs are separated by condition under
`ablations/openai_gpt_6_1_sol/runs/gpt_6_1_sol/<condition>/run_01/raw_pipeline.csv`.
Use a new run tag when changing model settings, workers, code or input assets.
Defaults: two concurrent benchmark queries, one DAG worker, medium reasoning.
Set `SOL_REASONING_EFFORT=low|medium|high|xhigh|max` before starting a fresh run
to choose reasoning effort. Requests retain the existing prompts, convert
`max_tokens` to `max_completion_tokens` where needed, and omit sampling/logprob
parameters unsupported with reasoning. This adaptation is local to this launcher.

Offline configuration check (no inference calls):

```bash
bash ablations/openai_gpt_6_1_sol/run_raw.sh without_context --dry-run
```

Official model and compatibility references:
- https://developers.openai.com/api/docs/models/gpt-6.1-sol
- https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.1-sol
