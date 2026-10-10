# Small-sample token and cost measurements

This runner measures the unchanged answering pipeline in a separate process. It
does not edit production pipeline files, alter grader scoring, or start a grader.
Existing full runs remain untouched. The default is the same 40 seeded questions
for all four models and both context conditions: 320 question executions total.
Selection uses query type, difficulty and source metadata, never reference answers
or previous success/failure labels. Query types have at least two examples when
the sample size permits. Estimates are weighted by the full benchmark's query-type
distribution, rather than taking an unweighted average of the oversampled types.

## Run all eight measurements

From `script_diff_llm2`:

```bash
/usr/bin/python3 -u ablations/v5_test1000/measurement/run.py \
  --sample-size 40 --workers 4 --tag sample40_01
```

Repeat the identical command to resume saved question rows. Experiments run
sequentially to reduce competition between models. Existing ablation model
credentials, source paths, Fuseki endpoint and per-model context caches are used.
Fuseki must already be running. Wait for existing full runs to finish before
measuring, especially Kimi, to reduce contention. No streaming or generation
parameters are changed. Failed questions saved in the raw report are not
automatically rerun. A process interrupted during an active request may incur
unrecorded provider charges; treat that experiment's estimated cost cautiously.

Inspect selection without model calls:

```bash
/usr/bin/python3 ablations/v5_test1000/measurement/run.py --select-only
```

Run just one condition/model, preserving the common selection:

```bash
/usr/bin/python3 -u ablations/v5_test1000/measurement/run.py \
  --models gpt_oss_120b --conditions without_context \
  --sample-size 40 --workers 4 --tag sample40_01
```

For a larger independent sample, use a fresh tag, for example
`--sample-size 80 --tag sample80_01`. Changing selection, pipeline code or worker
counts cannot resume into the same nonempty experiment directory.

## Prices and cost

`measurement/prices.json` is populated with these user-supplied USD assumptions:

| Model | Input / 1M tokens | Output / 1M tokens | User-supplied provider reference |
|---|---:|---:|---|
| DeepSeek V3.2 | $0.28 | $0.42 | Last official DeepSeek V3.2 rate |
| Gemma 3 27B IT | $0.27 | $0.45 | AWS Bedrock |
| Kimi K2 Thinking | $0.47 | $2.00 | Vercel AI Gateway |
| GPT-OSS 120B | $0.15 | $0.60 | Groq / Together / Fireworks-class pricing |

These rates are not independently verified. Since the current experiments use
AWS endpoints, estimates using cross-provider prices are illustrative token costs,
not reconstructed AWS bills. The JSON and CSV summaries retain pricing assumptions
and the per-experiment JSON records exact rates for reproducibility. Replace rates
with your endpoint's prices if actual incurred-cost estimates are required. Null
rates are also supported; monetary estimates then remain unavailable. The
calculation assumes ordinary input/output token billing; special cached-token,
reasoning-token or discounted pricing requires adjusting the calculation to your
provider's billing rules. Do not copy baseline cost/query into these rate fields.

After filling prices, recompute without API calls:

```bash
/usr/bin/python3 ablations/v5_test1000/measurement/run.py \
  --sample-size 40 --workers 4 --tag sample40_01 --summarize-only
```

## Outputs and interpretation

Files live under `measurement/runs/sample40_01/`:

- `sample.json`: reproducible selected IDs, metadata and population weights.
- `<model>/<condition>/requests.jsonl`: request duration, usage, stage, question
  attribution and failure type; no prompt contents or credentials are stored.
- `<model>/<condition>/raw_pipeline.csv`: isolated sample answering results.
- `<model>/<condition>/summary.json`: weighted estimates, per-question usage and
  stratified bootstrap intervals.
- `combined_summary.json`: all selected experiment summaries.
- `summary_table.csv`: spreadsheet-ready latency/cost estimates and intervals.

`request_latency_ms_per_output_token` is weighted total **non-streaming model
request duration** divided by weighted output tokens, times 1,000. Request duration
includes network overhead, queueing, internal SDK retries and prompt processing.
It is a clearly labelled proxy for generation-only token latency, not a measure
of pure decoding speed or time to first token. Simultaneous calls contribute their
individual durations. `completion_tokens` is the provider-reported count; hidden
reasoning is included only if the provider counts it in that field.

`average_cost_per_question` sums all measured model calls, including successful
repairs, then applies query-type population weights. Database time and grading
are excluded. Observed startup/context preparation is reported separately, and
also added to the 1,000-question cost projection. A cache hit costs zero preparation
in this measurement; it does not reveal the earlier cache-creation cost. The
evaluation-scoped business-rules document stays quarantined, exactly as in the
existing with-context runs.

Final estimates are withheld if selected rows are missing or provider usage is
missing/failed requests have unknown usage. Known token counts remain available
for diagnosis. Final answering output tokens are not substituted for model usage.
Bootstrap intervals describe sampling variability only: 40 questions cannot
guarantee tight estimates, especially for Kimi and rare repair-heavy questions.
Report these as new **sample-based estimates**, separately from historical full-run
accuracy. Retain the original full-run accuracy and execution-efficiency values;
this measurement does not produce new grading scores.
