# GPT-5 Mini graded baseline metrics

All five reports contain 1,000 questions graded by `gpt-5-mini`. A correct answer is a row whose `New Status` is `MATCH`; `PARTIAL`, `MISMATCH`, and error statuses are not counted as correct.

## Accuracy

`Accuracy = MATCH answers / total questions × 100`

| Pipeline | Questions | Correct (MATCH) | Accuracy |
|---|---:|---:|---:|
| Base SPARQL | 1,000 | 495 | 49.50% |
| Base SQL | 1,000 | 662 | 66.20% |
| GraphRAG Local | 1,000 | 68 | 6.80% |
| Parallel SPARQL | 1,000 | 454 | 45.40% |
| Parallel SQL | 1,000 | 632 | 63.20% |

## Token latency

`Token latency = total generation time / total output tokens`

For parallel ensembles, generation time is the sum of the three branch-call generation latencies, matching the summed branch token counts. Branch calls run concurrently, so this is model-call time per generated token rather than end-to-end wall-clock latency.

| Pipeline | Input tokens | Output tokens | Generation time (s) | Seconds/output token | Milliseconds/output token |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 2,520,045 | 678,155 | 4,667.365 | 0.006882 | 6.882 |
| Base SQL | 757,045 | 399,649 | 2,669.414 | 0.006679 | 6.679 |
| GraphRAG Local | 70,621,523 | 1,248,597 | 18,799.086 | 0.015056 | 15.056 |
| Parallel SPARQL | 6,795,135 | 1,841,342 | 12,879.300 | 0.006995 | 6.995 |
| Parallel SQL | 2,271,135 | 1,205,286 | 7,918.749 | 0.006570 | 6.570 |

## Inference cost

`Total cost = Σ[(input tokens × input price / 1,000,000) + (output tokens × output price / 1,000,000)]`

`Average cost per question = total cost / 1,000`

Pricing assumption: Amazon Bedrock Standard on-demand `openai.gpt-oss-120b-1:0` in `us-east-1`, at $0.15 per million input tokens and $0.60 per million output tokens. Source: [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/). Costs cover baseline generation only. GPT-5 Mini grader usage is not present in the result CSVs and is therefore excluded.

| Pipeline | Input cost (USD) | Output cost (USD) | Total inference cost (USD) | Average cost/question (USD) |
|---|---:|---:|---:|---:|
| Base SPARQL | $0.378007 | $0.406893 | $0.784900 | $0.000784900 |
| Base SQL | $0.113557 | $0.239789 | $0.353346 | $0.000353346 |
| GraphRAG Local | $10.593228 | $0.749158 | $11.342387 | $0.011342387 |
| Parallel SPARQL | $1.019270 | $1.104805 | $2.124075 | $0.002124075 |
| Parallel SQL | $0.340670 | $0.723172 | $1.063842 | $0.001063842 |

## Execution efficiency

`Execution efficiency = correct answers / total execution time in seconds`

Total execution time is the sum of the per-question `Elapsed Seconds` field. It measures aggregate question-processing time, not the shorter wall-clock duration obtained by running multiple questions concurrently.

| Pipeline | Correct (MATCH) | Total execution time (s) | Execution efficiency (correct answers/s) |
|---|---:|---:|---:|
| Base SPARQL | 495 | 4,868.797 | 0.101668 |
| Base SQL | 662 | 2,780.620 | 0.238076 |
| GraphRAG Local | 68 | 19,766.266 | 0.003440 |
| Parallel SPARQL | 454 | 7,237.612 | 0.062728 |
| Parallel SQL | 632 | 4,057.139 | 0.155775 |

## Source files

- **Base SPARQL:** `base_sparql_dynamic_namespace_1000q_20261002_graded_gpt_5_mini.csv`
- **Base SQL:** `base_pipeline_sql_schema_only_prompt_1000q_20261001_graded_gpt_5_mini.csv`
- **GraphRAG Local:** `graph_rag_local_domain_neutral_prompt_1000q_20261001_graded_gpt_5_mini.csv`
- **Parallel SPARQL:** `parallel_sparql_schema_only_prompt_parser_lock_1000q_20261002_graded_gpt_5_mini.csv`
- **Parallel SQL:** `parallel_sql_schema_only_prompt_1000q_20261001_graded_gpt_5_mini.csv`
