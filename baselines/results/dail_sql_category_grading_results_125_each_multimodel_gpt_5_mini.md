# DAIL-SQL grading results by 125-question category — four pipeline-runner models

Each run contains exactly 125 questions from each of eight benchmark categories and was graded by `gpt-5-mini`. `OTHER / ERROR` contains every status other than `MATCH`, `MISMATCH`, and `PARTIAL`.

## Category key

| Code | Category | Source dataset |
|---|---|---|
| BM | Benchmark | `wealth_management_125_question_benchmark.csv` |
| ARC | At-Risk Critical | `wealth_management_at_risk_critical_125_questions.csv` |
| BS | Batch Status | `wealth_management_batch_status_125_questions.csv` |
| EC | Enrichment Context | `wealth_management_enrichment_context_125_questions.csv` |
| MC | Multi-Step Comparative | `wealth_management_multi_step_comparative_125_questions.csv` |
| RC | Reference Compliance | `wealth_management_reference_compliance_125_questions.csv` |
| SQ | Scoring Quantitative | `wealth_management_scoring_quantitative_125_questions.csv` |
| TT | Temporal Transaction | `wealth_management_temporal_transaction_125_questions.csv` |

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

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 102 | 7 | 16 | 0 |
| ARC | At-Risk Critical | 125 | 79 | 8 | 38 | 0 |
| BS | Batch Status | 125 | 92 | 10 | 23 | 0 |
| EC | Enrichment Context | 125 | 96 | 9 | 19 | 1 |
| MC | Multi-Step Comparative | 125 | 85 | 4 | 36 | 0 |
| RC | Reference Compliance | 125 | 84 | 3 | 38 | 0 |
| SQ | Scoring Quantitative | 125 | 103 | 5 | 17 | 0 |
| TT | Temporal Transaction | 125 | 95 | 15 | 15 | 0 |
| **Overall** | **All categories** | **1000** | 736 | 61 | 202 | 1 |

Other status details: `OTHER`: 1.

## Kimi K2 Thinking 1T

Model ID: `moonshotai.kimi-k2-thinking`

Source: `dail_sql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 97 | 15 | 13 | 0 |
| ARC | At-Risk Critical | 125 | 79 | 14 | 32 | 0 |
| BS | Batch Status | 125 | 87 | 14 | 24 | 0 |
| EC | Enrichment Context | 125 | 98 | 9 | 17 | 1 |
| MC | Multi-Step Comparative | 125 | 72 | 17 | 26 | 10 |
| RC | Reference Compliance | 125 | 87 | 1 | 36 | 1 |
| SQ | Scoring Quantitative | 125 | 102 | 7 | 16 | 0 |
| TT | Temporal Transaction | 125 | 89 | 21 | 15 | 0 |
| **Overall** | **All categories** | **1000** | 711 | 98 | 179 | 12 |

Other status details: `OTHER`: 11, `TOKEN_OUTPUT_ERROR`: 1.

## Gemma 3 27B IT

Model ID: `google.gemma-3-27b-it`

Source: `dail_sql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 103 | 7 | 15 | 0 |
| ARC | At-Risk Critical | 125 | 73 | 18 | 34 | 0 |
| BS | Batch Status | 125 | 85 | 10 | 29 | 1 |
| EC | Enrichment Context | 125 | 72 | 27 | 23 | 3 |
| MC | Multi-Step Comparative | 125 | 26 | 46 | 45 | 8 |
| RC | Reference Compliance | 125 | 89 | 0 | 36 | 0 |
| SQ | Scoring Quantitative | 125 | 73 | 29 | 19 | 4 |
| TT | Temporal Transaction | 125 | 90 | 19 | 14 | 2 |
| **Overall** | **All categories** | **1000** | 611 | 156 | 215 | 18 |

Other status details: `OTHER`: 18.

## DeepSeek V3.2 685B

Model ID: `deepseek.v3.2`

Source: `dail_sql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 105 | 6 | 13 | 1 |
| ARC | At-Risk Critical | 125 | 82 | 6 | 36 | 1 |
| BS | Batch Status | 125 | 94 | 7 | 23 | 1 |
| EC | Enrichment Context | 125 | 98 | 13 | 13 | 1 |
| MC | Multi-Step Comparative | 125 | 71 | 14 | 35 | 5 |
| RC | Reference Compliance | 125 | 82 | 1 | 41 | 1 |
| SQ | Scoring Quantitative | 125 | 96 | 9 | 20 | 0 |
| TT | Temporal Transaction | 125 | 101 | 11 | 12 | 1 |
| **Overall** | **All categories** | **1000** | 729 | 67 | 193 | 11 |

Other status details: `OTHER`: 11.
