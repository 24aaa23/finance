# Multi-model baseline metrics (GPT-5 Mini grader)

Correct answers are rows whose final `New Status` is `MATCH`.

- `Accuracy = correct answers / total questions × 100`
- `Token latency = total generation time / total output tokens`
- `Inference cost = Σ[(input tokens × input price / 1,000,000) + (output tokens × output price / 1,000,000)]`
- `Average inference cost per question = total inference cost / total questions`
- `Execution efficiency = correct answers / total execution time in seconds`

For parallel ensembles, generation time and tokens are summed across all branch calls. Total execution time is the sum of per-question `Elapsed Seconds`, not concurrent wall-clock duration. GPT-5 Mini grader cost is excluded because grader token usage is not recorded in the graded CSVs.

## Pricing assumptions

Amazon Bedrock Standard on-demand pricing in `us-east-1`, checked 2026-10-04 from [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/):

| Model | Model ID | Input / 1M tokens | Output / 1M tokens |
|---|---|---:|---:|
| GPT-OSS 120B | `openai.gpt-oss-120b-1:0` | $0.15 | $0.60 |
| Kimi K2 Thinking 1T | `moonshotai.kimi-k2-thinking` | $0.60 | $2.50 |
| Gemma 3 27B IT | `google.gemma-3-27b-it` | $0.23 | $0.38 |
| DeepSeek V3.2 685B | `deepseek.v3.2` | $0.62 | $1.85 |

## Model-level aggregate across five pipelines

| Model | Questions | Correct | Accuracy | Input tokens | Output tokens | Generation time (s) | Token latency (ms/output token) | Total cost | Avg. cost/question | Execution time (s) | Correct/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-OSS 120B | 5,000 | 2,196 | 43.92% | 143,965,103 | 5,950,058 | 54,555.641 | 9.169 | $25.164800 | $0.005032960 | 45,325.652 | 0.048449 |
| Kimi K2 Thinking 1T | 5,000 | 1,929 | 38.58% | 140,662,278 | 19,955,656 | 350,074.148 | 17.543 | $134.286507 | $0.026857301 | 276,631.280 | 0.006973 |
| Gemma 3 27B IT | 5,000 | 1,565 | 31.30% | 137,332,899 | 1,629,049 | 128,159.111 | 78.671 | $32.205605 | $0.006441121 | 133,645.319 | 0.011710 |
| DeepSeek V3.2 685B | 5,000 | 1,869 | 37.38% | 148,846,566 | 1,911,937 | 59,273.475 | 31.002 | $95.821954 | $0.019164391 | 45,559.108 | 0.041024 |

## Pipeline-level detail

| Model | Pipeline | Questions | Correct | Accuracy | Input tokens | Output tokens | Generation time (s) | Token latency (ms/output token) | Total cost | Avg. cost/question | Execution time (s) | Correct/s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-OSS 120B | Base SPARQL | 1,000 | 452 | 45.20% | 9,591,045 | 638,526 | 4,635.682 | 7.260 | $1.821772 | $0.001821772 | 4,867.151 | 0.092867 |
| GPT-OSS 120B | Base SQL | 1,000 | 681 | 68.10% | 7,828,045 | 436,602 | 3,241.117 | 7.424 | $1.436168 | $0.001436168 | 3,315.679 | 0.205388 |
| GPT-OSS 120B | GraphRAG Local | 1,000 | 62 | 6.20% | 75,053,743 | 1,744,950 | 22,842.686 | 13.091 | $12.305031 | $0.012305031 | 24,888.025 | 0.002491 |
| GPT-OSS 120B | Parallel SPARQL | 1,000 | 401 | 40.10% | 28,008,135 | 1,788,225 | 13,588.360 | 7.599 | $5.274155 | $0.005274155 | 7,089.949 | 0.056559 |
| GPT-OSS 120B | Parallel SQL | 1,000 | 600 | 60.00% | 23,484,135 | 1,341,755 | 10,247.796 | 7.638 | $4.327673 | $0.004327673 | 5,164.848 | 0.116170 |
| Kimi K2 Thinking 1T | Base SPARQL | 1,000 | 425 | 42.50% | 8,959,789 | 1,915,431 | 39,503.529 | 20.624 | $10.164451 | $0.010164451 | 48,795.302 | 0.008710 |
| Kimi K2 Thinking 1T | Base SQL | 1,000 | 615 | 61.50% | 7,262,714 | 1,441,878 | 31,860.901 | 22.097 | $7.962323 | $0.007962323 | 40,338.923 | 0.015246 |
| Kimi K2 Thinking 1T | GraphRAG Local | 1,000 | 61 | 6.10% | 74,885,040 | 4,332,312 | 90,382.265 | 20.862 | $55.761804 | $0.055761804 | 91,893.702 | 0.000664 |
| Kimi K2 Thinking 1T | Parallel SPARQL | 1,000 | 324 | 32.40% | 27,429,507 | 7,441,234 | 108,135.529 | 14.532 | $35.060789 | $0.035060789 | 50,641.299 | 0.006398 |
| Kimi K2 Thinking 1T | Parallel SQL | 1,000 | 504 | 50.40% | 22,125,228 | 4,824,801 | 80,191.924 | 16.621 | $25.337139 | $0.025337139 | 44,962.054 | 0.011209 |
| Gemma 3 27B IT | Base SPARQL | 1,000 | 219 | 21.90% | 10,240,083 | 172,317 | 9,307.863 | 54.016 | $2.420700 | $0.002420700 | 13,369.192 | 0.016381 |
| Gemma 3 27B IT | Base SQL | 1,000 | 545 | 54.50% | 8,570,968 | 168,705 | 7,800.546 | 46.238 | $2.035431 | $0.002035431 | 7,818.039 | 0.069711 |
| Gemma 3 27B IT | GraphRAG Local | 1,000 | 49 | 4.90% | 62,719,925 | 288,039 | 46,728.742 | 162.231 | $14.535038 | $0.014535038 | 68,123.269 | 0.000719 |
| Gemma 3 27B IT | Parallel SPARQL | 1,000 | 218 | 21.80% | 30,089,019 | 492,900 | 32,610.518 | 66.161 | $7.107776 | $0.007107776 | 24,881.819 | 0.008761 |
| Gemma 3 27B IT | Parallel SQL | 1,000 | 534 | 53.40% | 25,712,904 | 507,088 | 31,711.442 | 62.536 | $6.106661 | $0.006106661 | 19,453.000 | 0.027451 |
| DeepSeek V3.2 685B | Base SPARQL | 1,000 | 405 | 40.50% | 9,987,045 | 202,720 | 5,457.685 | 26.922 | $6.567000 | $0.006567000 | 5,585.974 | 0.072503 |
| DeepSeek V3.2 685B | Base SQL | 1,000 | 581 | 58.10% | 7,952,045 | 145,083 | 4,219.319 | 29.082 | $5.198671 | $0.005198671 | 4,260.608 | 0.136366 |
| DeepSeek V3.2 685B | GraphRAG Local | 1,000 | 67 | 6.70% | 78,044,206 | 576,601 | 21,242.988 | 36.842 | $49.454120 | $0.049454120 | 22,152.154 | 0.003025 |
| DeepSeek V3.2 685B | Parallel SPARQL | 1,000 | 303 | 30.30% | 29,007,135 | 538,854 | 15,280.903 | 28.358 | $18.981304 | $0.018981304 | 7,418.178 | 0.040846 |
| DeepSeek V3.2 685B | Parallel SQL | 1,000 | 513 | 51.30% | 23,856,135 | 448,679 | 13,072.580 | 29.136 | $15.620860 | $0.015620860 | 6,142.194 | 0.083521 |

## Source files

- **GPT-OSS 120B — Base SPARQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/base_pipeline_qwen/output/base_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`
- **GPT-OSS 120B — Base SQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/base_pipeline_sql/output/base_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`
- **GPT-OSS 120B — GraphRAG Local:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/graph_rag_baseline/output/graph_rag_local_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`
- **GPT-OSS 120B — Parallel SPARQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/parallel_pipeline_baseline/output/parallel_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`
- **GPT-OSS 120B — Parallel SQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/parallel_pipeline_sql_baseline/output/parallel_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`
- **Kimi K2 Thinking 1T — Base SPARQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/base_pipeline_qwen/output/multimodel_domain_context_20261004/kimi_k2_thinking_1t/base_sparql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **Kimi K2 Thinking 1T — Base SQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/base_pipeline_sql/output/multimodel_domain_context_20261004/kimi_k2_thinking_1t/base_sql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **Kimi K2 Thinking 1T — GraphRAG Local:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/graph_rag_baseline/output/multimodel_domain_context_20261004/kimi_k2_thinking_1t/graph_rag_local_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **Kimi K2 Thinking 1T — Parallel SPARQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/parallel_pipeline_baseline/output/multimodel_domain_context_20261004/kimi_k2_thinking_1t/parallel_sparql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **Kimi K2 Thinking 1T — Parallel SQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/parallel_pipeline_sql_baseline/output/multimodel_domain_context_20261004/kimi_k2_thinking_1t/parallel_sql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **Gemma 3 27B IT — Base SPARQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/base_pipeline_qwen/output/multimodel_domain_context_20261004/gemma_3_27b_it/base_sparql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **Gemma 3 27B IT — Base SQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/base_pipeline_sql/output/multimodel_domain_context_20261004/gemma_3_27b_it/base_sql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **Gemma 3 27B IT — GraphRAG Local:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/graph_rag_baseline/output/multimodel_domain_context_20261004/gemma_3_27b_it/graph_rag_local_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **Gemma 3 27B IT — Parallel SPARQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/parallel_pipeline_baseline/output/multimodel_domain_context_20261004/gemma_3_27b_it/parallel_sparql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **Gemma 3 27B IT — Parallel SQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/parallel_pipeline_sql_baseline/output/multimodel_domain_context_20261004/gemma_3_27b_it/parallel_sql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **DeepSeek V3.2 685B — Base SPARQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/base_pipeline_qwen/output/multimodel_domain_context_20261004/deepseek_v3_2_685b/base_sparql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **DeepSeek V3.2 685B — Base SQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/base_pipeline_sql/output/multimodel_domain_context_20261004/deepseek_v3_2_685b/base_sql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **DeepSeek V3.2 685B — GraphRAG Local:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/graph_rag_baseline/output/multimodel_domain_context_20261004/deepseek_v3_2_685b/graph_rag_local_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **DeepSeek V3.2 685B — Parallel SPARQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/parallel_pipeline_baseline/output/multimodel_domain_context_20261004/deepseek_v3_2_685b/parallel_sparql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- **DeepSeek V3.2 685B — Parallel SQL:** `/indian-slp/Users/ug/ZEPA/Rohan/neosapients/finance/parallel_pipeline_sql_baseline/output/multimodel_domain_context_20261004/deepseek_v3_2_685b/parallel_sql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
