# DAIL-SQL grading results by query type — four pipeline-runner models

This report combines four independent 1,000-question DAIL-SQL runs graded by `gpt-5-mini`. `OTHER / ERROR` contains every status other than `MATCH`, `MISMATCH`, and `PARTIAL`.

## Overall comparison

| Pipeline-runner model | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| GPT-OSS 120B | 1000 | 736 | 61 | 202 | 1 |
| Kimi K2 Thinking 1T | 1000 | 711 | 98 | 179 | 12 |
| Gemma 3 27B IT | 1000 | 611 | 156 | 215 | 18 |
| DeepSeek V3.2 685B | 1000 | 729 | 67 | 193 | 11 |

## GPT-OSS 120B

Model ID: `openai.gpt-oss-120b-1:0`

Source: `dail_sql_gpt_oss_120b_domain_context_1000q_20261005_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 174 | 19 | 18 | 1 |
| Comparative | 15 | 11 | 2 | 2 | 0 |
| Composite Reasoning | 143 | 103 | 10 | 30 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 46 | 2 | 5 | 0 |
| Filtered List | 103 | 43 | 2 | 58 | 0 |
| Multi-Relational | 212 | 138 | 19 | 55 | 0 |
| Multi-step Comparative | 55 | 40 | 0 | 15 | 0 |
| Ranking | 65 | 59 | 4 | 2 | 0 |
| Reference Compliance | 39 | 26 | 3 | 10 | 0 |
| Rule-Based Detection | 29 | 23 | 0 | 6 | 0 |
| Temporal | 40 | 39 | 0 | 1 | 0 |
| **Overall** | **1000** | 736 | 61 | 202 | 1 |

Other status details: `OTHER`: 1.

## Kimi K2 Thinking 1T

Model ID: `moonshotai.kimi-k2-thinking`

Source: `dail_sql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 179 | 17 | 15 | 1 |
| Comparative | 15 | 11 | 0 | 4 | 0 |
| Composite Reasoning | 143 | 87 | 35 | 13 | 8 |
| Direct Retrieval | 34 | 33 | 0 | 1 | 0 |
| Exception Detection | 53 | 46 | 3 | 3 | 1 |
| Filtered List | 103 | 42 | 6 | 55 | 0 |
| Multi-Relational | 212 | 137 | 23 | 52 | 0 |
| Multi-step Comparative | 55 | 33 | 2 | 18 | 2 |
| Ranking | 65 | 54 | 8 | 3 | 0 |
| Reference Compliance | 39 | 28 | 1 | 10 | 0 |
| Rule-Based Detection | 29 | 23 | 1 | 5 | 0 |
| Temporal | 40 | 38 | 2 | 0 | 0 |
| **Overall** | **1000** | 711 | 98 | 179 | 12 |

Other status details: `OTHER`: 11, `TOKEN_OUTPUT_ERROR`: 1.

## Gemma 3 27B IT

Model ID: `google.gemma-3-27b-it`

Source: `dail_sql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 156 | 30 | 22 | 4 |
| Comparative | 15 | 3 | 4 | 8 | 0 |
| Composite Reasoning | 143 | 83 | 31 | 24 | 5 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 45 | 7 | 1 | 0 |
| Filtered List | 103 | 38 | 10 | 54 | 1 |
| Multi-Relational | 212 | 127 | 29 | 56 | 0 |
| Multi-step Comparative | 55 | 6 | 19 | 26 | 4 |
| Ranking | 65 | 36 | 19 | 6 | 4 |
| Reference Compliance | 39 | 27 | 0 | 12 | 0 |
| Rule-Based Detection | 29 | 22 | 1 | 6 | 0 |
| Temporal | 40 | 34 | 6 | 0 | 0 |
| **Overall** | **1000** | 611 | 156 | 215 | 18 |

Other status details: `OTHER`: 18.

## DeepSeek V3.2 685B

Model ID: `deepseek.v3.2`

Source: `dail_sql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 176 | 19 | 15 | 2 |
| Comparative | 15 | 9 | 0 | 5 | 1 |
| Composite Reasoning | 143 | 94 | 18 | 28 | 3 |
| Direct Retrieval | 34 | 33 | 1 | 0 | 0 |
| Exception Detection | 53 | 48 | 1 | 3 | 1 |
| Filtered List | 103 | 39 | 5 | 59 | 0 |
| Multi-Relational | 212 | 150 | 14 | 47 | 1 |
| Multi-step Comparative | 55 | 36 | 2 | 15 | 2 |
| Ranking | 65 | 57 | 5 | 2 | 1 |
| Reference Compliance | 39 | 26 | 0 | 13 | 0 |
| Rule-Based Detection | 29 | 23 | 0 | 6 | 0 |
| Temporal | 40 | 38 | 2 | 0 | 0 |
| **Overall** | **1000** | 729 | 67 | 193 | 11 |

Other status details: `OTHER`: 11.
