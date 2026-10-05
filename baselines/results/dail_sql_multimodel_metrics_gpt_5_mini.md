# DAIL-SQL four-model metrics (GPT-5 Mini grader)

This report compares four 1,000-question DAIL-SQL runs graded by `gpt-5-mini`. A correct answer is a row whose final `New Status` is `MATCH`.

DAIL-SQL makes two model calls per question. Generation tokens and generation time include both the preliminary-SQL call and the final-SQL call.

## Accuracy

`Accuracy = MATCH answers / total questions × 100`

| Pipeline-runner model | Questions | Correct (MATCH) | Accuracy |
|---|---:|---:|---:|
| GPT-OSS 120B | 1,000 | 736 | 73.60% |
| Kimi K2 Thinking 1T | 1,000 | 711 | 71.10% |
| Gemma 3 27B IT | 1,000 | 611 | 61.10% |
| DeepSeek V3.2 685B | 1,000 | 729 | 72.90% |

## Token latency

`Token latency = total generation time / total output tokens`

| Pipeline-runner model | Input tokens | Output tokens | Generation time (s) | Seconds/output token | Milliseconds/output token |
|---|---:|---:|---:|---:|---:|
| GPT-OSS 120B | 17,909,162 | 912,308 | 6,559.438 | 0.007190 | 7.190 |
| Kimi K2 Thinking 1T | 17,032,816 | 3,293,863 | 32,857.235 | 0.009975 | 9.975 |
| Gemma 3 27B IT | 19,852,390 | 290,188 | 6,678.922 | 0.023016 | 23.016 |
| DeepSeek V3.2 685B | 18,271,011 | 284,444 | 8,502.202 | 0.029891 | 29.891 |

## Inference cost

`Total cost = Σ[(input tokens × input price / 1,000,000) + (output tokens × output price / 1,000,000)]`

`Average cost per question = total cost / total questions`

Pricing assumptions use the same Amazon Bedrock Standard on-demand rates as the existing multi-model reports. GPT-5 Mini grader cost is excluded.

| Pipeline-runner model | Input price / 1M | Output price / 1M | Input cost (USD) | Output cost (USD) | Total inference cost (USD) | Average cost/question (USD) |
|---|---:|---:|---:|---:|---:|---:|
| GPT-OSS 120B | $0.15 | $0.60 | $2.686374 | $0.547385 | $3.233759 | $0.003233759 |
| Kimi K2 Thinking 1T | $0.60 | $2.50 | $10.219690 | $8.234658 | $18.454347 | $0.018454347 |
| Gemma 3 27B IT | $0.23 | $0.38 | $4.566050 | $0.110271 | $4.676321 | $0.004676321 |
| DeepSeek V3.2 685B | $0.62 | $1.85 | $11.328027 | $0.526221 | $11.854248 | $0.011854248 |

## Execution efficiency

`Execution efficiency = correct answers / total execution time in seconds`

Total execution time is the sum of per-question `Elapsed Seconds`, not concurrent wall-clock duration.

| Pipeline-runner model | Correct (MATCH) | Total execution time (s) | Execution efficiency (correct answers/s) |
|---|---:|---:|---:|
| GPT-OSS 120B | 736 | 6,657.385 | 0.110554 |
| Kimi K2 Thinking 1T | 711 | 36,302.887 | 0.019585 |
| Gemma 3 27B IT | 611 | 6,845.717 | 0.089253 |
| DeepSeek V3.2 685B | 729 | 9,203.331 | 0.079210 |

## Model and source files

- GPT-OSS 120B (`openai.gpt-oss-120b-1:0`): `dail_sql_gpt_oss_120b_domain_context_1000q_20261005_graded_gpt_5_mini.csv`
- Kimi K2 Thinking 1T (`moonshotai.kimi-k2-thinking`): `dail_sql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- Gemma 3 27B IT (`google.gemma-3-27b-it`): `dail_sql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`
- DeepSeek V3.2 685B (`deepseek.v3.2`): `dail_sql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

Pricing source: [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).
