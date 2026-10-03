# Domain-context baseline metrics (GPT-5 Mini grader)

All five reports contain 1,000 questions graded by `gpt-5-mini`. A correct answer is a row whose `New Status` is `MATCH`; `PARTIAL`, `MISMATCH`, and error statuses are not counted as correct.

## Accuracy

`Accuracy = MATCH answers / total questions × 100`

| Pipeline | Questions | Correct (MATCH) | Accuracy |
|---|---:|---:|---:|
| Base SPARQL | 1,000 | 452 | 45.20% |
| Base SQL | 1,000 | 681 | 68.10% |
| GraphRAG Local | 1,000 | 62 | 6.20% |
| Parallel SPARQL | 1,000 | 401 | 40.10% |
| Parallel SQL | 1,000 | 600 | 60.00% |

## Token latency

`Token latency = total generation time / total output tokens`

For parallel ensembles, generation time is the sum of the three branch-call generation latencies, matching the summed branch token counts. Branch calls run concurrently, so this is model-call time per generated token rather than end-to-end wall-clock latency.

| Pipeline | Input tokens | Output tokens | Generation time (s) | Seconds/output token | Milliseconds/output token |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 9,591,045 | 638,526 | 4,635.682 | 0.007260 | 7.260 |
| Base SQL | 7,828,045 | 436,602 | 3,241.117 | 0.007424 | 7.424 |
| GraphRAG Local | 75,053,743 | 1,744,950 | 22,842.686 | 0.013091 | 13.091 |
| Parallel SPARQL | 28,008,135 | 1,788,225 | 13,588.360 | 0.007599 | 7.599 |
| Parallel SQL | 23,484,135 | 1,341,755 | 10,247.796 | 0.007638 | 7.638 |

## Inference cost

`Total cost = Σ[(input tokens × input price / 1,000,000) + (output tokens × output price / 1,000,000)]`

`Average cost per question = total cost / 1,000`

Pricing assumption: Amazon Bedrock Standard on-demand `openai.gpt-oss-120b-1:0` in `us-east-1`, at $0.15 per million input tokens and $0.60 per million output tokens. Source: [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/). Costs cover baseline generation only. GPT-5 Mini grader usage is not present in the result CSVs and is therefore excluded.

| Pipeline | Input cost (USD) | Output cost (USD) | Total inference cost (USD) | Average cost/question (USD) |
|---|---:|---:|---:|---:|
| Base SPARQL | $1.438657 | $0.383116 | $1.821772 | $0.001821772 |
| Base SQL | $1.174207 | $0.261961 | $1.436168 | $0.001436168 |
| GraphRAG Local | $11.258061 | $1.046970 | $12.305031 | $0.012305031 |
| Parallel SPARQL | $4.201220 | $1.072935 | $5.274155 | $0.005274155 |
| Parallel SQL | $3.522620 | $0.805053 | $4.327673 | $0.004327673 |

## Execution efficiency

`Execution efficiency = correct answers / total execution time in seconds`

Total execution time is the sum of the per-question `Elapsed Seconds` field. It measures aggregate question-processing time, not the shorter wall-clock duration obtained by running multiple questions concurrently.

| Pipeline | Correct (MATCH) | Total execution time (s) | Execution efficiency (correct answers/s) |
|---|---:|---:|---:|
| Base SPARQL | 452 | 4,867.151 | 0.092867 |
| Base SQL | 681 | 3,315.679 | 0.205388 |
| GraphRAG Local | 62 | 24,888.025 | 0.002491 |
| Parallel SPARQL | 401 | 7,089.949 | 0.056559 |
| Parallel SQL | 600 | 5,164.848 | 0.116170 |

## Source files

- **Base SPARQL:** `base_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`
- **Base SQL:** `base_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`
- **GraphRAG Local:** `graph_rag_local_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`
- **Parallel SPARQL:** `parallel_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`
- **Parallel SQL:** `parallel_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`
