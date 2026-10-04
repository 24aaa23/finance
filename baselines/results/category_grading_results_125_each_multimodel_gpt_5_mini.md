# Multi-model grading results by 125-question category

Every model/pipeline report contains exactly 125 questions from each of the eight benchmark source categories.

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

## Overall

| Model | Pipeline | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| GPT-OSS 120B | Base SPARQL | 1000 | 452 | 253 | 288 | 7 |
| GPT-OSS 120B | Base SQL | 1000 | 681 | 92 | 226 | 1 |
| GPT-OSS 120B | GraphRAG Local | 1000 | 62 | 875 | 58 | 5 |
| GPT-OSS 120B | Parallel SPARQL | 1000 | 401 | 386 | 212 | 1 |
| GPT-OSS 120B | Parallel SQL | 1000 | 600 | 233 | 166 | 1 |
| Kimi K2 Thinking 1T | Base SPARQL | 1000 | 425 | 252 | 302 | 21 |
| Kimi K2 Thinking 1T | Base SQL | 1000 | 615 | 190 | 180 | 15 |
| Kimi K2 Thinking 1T | GraphRAG Local | 1000 | 61 | 884 | 52 | 3 |
| Kimi K2 Thinking 1T | Parallel SPARQL | 1000 | 324 | 533 | 143 | 0 |
| Kimi K2 Thinking 1T | Parallel SQL | 1000 | 504 | 370 | 126 | 0 |
| Gemma 3 27B IT | Base SPARQL | 1000 | 219 | 557 | 151 | 73 |
| Gemma 3 27B IT | Base SQL | 1000 | 545 | 253 | 196 | 6 |
| Gemma 3 27B IT | GraphRAG Local | 1000 | 49 | 649 | 36 | 266 |
| Gemma 3 27B IT | Parallel SPARQL | 1000 | 218 | 657 | 125 | 0 |
| Gemma 3 27B IT | Parallel SQL | 1000 | 534 | 281 | 185 | 0 |
| DeepSeek V3.2 685B | Base SPARQL | 1000 | 405 | 390 | 173 | 32 |
| DeepSeek V3.2 685B | Base SQL | 1000 | 581 | 179 | 238 | 2 |
| DeepSeek V3.2 685B | GraphRAG Local | 1000 | 67 | 869 | 63 | 1 |
| DeepSeek V3.2 685B | Parallel SPARQL | 1000 | 303 | 591 | 106 | 0 |
| DeepSeek V3.2 685B | Parallel SQL | 1000 | 513 | 305 | 182 | 0 |

## GPT-OSS 120B — Base SPARQL

Source: `base_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 81 | 33 | 11 | 0 |
| ARC | At-Risk Critical | 125 | 61 | 20 | 43 | 1 |
| BS | Batch Status | 125 | 75 | 20 | 30 | 0 |
| EC | Enrichment Context | 125 | 20 | 30 | 75 | 0 |
| MC | Multi-Step Comparative | 125 | 11 | 62 | 47 | 5 |
| RC | Reference Compliance | 125 | 91 | 8 | 26 | 0 |
| SQ | Scoring Quantitative | 125 | 54 | 21 | 49 | 1 |
| TT | Temporal Transaction | 125 | 59 | 59 | 7 | 0 |
| **Overall** | **All categories** | **1000** | 452 | 253 | 288 | 7 |

Other status details: `OTHER`: 7.

## GPT-OSS 120B — Base SQL

Source: `base_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 101 | 13 | 11 | 0 |
| ARC | At-Risk Critical | 125 | 81 | 5 | 39 | 0 |
| BS | Batch Status | 125 | 72 | 23 | 29 | 1 |
| EC | Enrichment Context | 125 | 95 | 12 | 18 | 0 |
| MC | Multi-Step Comparative | 125 | 74 | 5 | 46 | 0 |
| RC | Reference Compliance | 125 | 70 | 5 | 50 | 0 |
| SQ | Scoring Quantitative | 125 | 96 | 9 | 20 | 0 |
| TT | Temporal Transaction | 125 | 92 | 20 | 13 | 0 |
| **Overall** | **All categories** | **1000** | 681 | 92 | 226 | 1 |

Other status details: `TOKEN_OUTPUT_ERROR`: 1.

## GPT-OSS 120B — GraphRAG Local

Source: `graph_rag_local_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 27 | 93 | 5 | 0 |
| ARC | At-Risk Critical | 125 | 1 | 100 | 24 | 0 |
| BS | Batch Status | 125 | 3 | 116 | 6 | 0 |
| EC | Enrichment Context | 125 | 14 | 103 | 7 | 1 |
| MC | Multi-Step Comparative | 125 | 0 | 124 | 1 | 0 |
| RC | Reference Compliance | 125 | 13 | 107 | 4 | 1 |
| SQ | Scoring Quantitative | 125 | 1 | 112 | 11 | 1 |
| TT | Temporal Transaction | 125 | 3 | 120 | 0 | 2 |
| **Overall** | **All categories** | **1000** | 62 | 875 | 58 | 5 |

Other status details: `CRASH`: 4, `TOKEN_OUTPUT_ERROR`: 1.

## GPT-OSS 120B — Parallel SPARQL

Source: `parallel_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 72 | 43 | 10 | 0 |
| ARC | At-Risk Critical | 125 | 47 | 47 | 31 | 0 |
| BS | Batch Status | 125 | 50 | 46 | 29 | 0 |
| EC | Enrichment Context | 125 | 21 | 50 | 54 | 0 |
| MC | Multi-Step Comparative | 125 | 13 | 85 | 27 | 0 |
| RC | Reference Compliance | 125 | 91 | 16 | 18 | 0 |
| SQ | Scoring Quantitative | 125 | 55 | 30 | 39 | 1 |
| TT | Temporal Transaction | 125 | 52 | 69 | 4 | 0 |
| **Overall** | **All categories** | **1000** | 401 | 386 | 212 | 1 |

Other status details: `OTHER`: 1.

## GPT-OSS 120B — Parallel SQL

Source: `parallel_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 89 | 28 | 8 | 0 |
| ARC | At-Risk Critical | 125 | 67 | 28 | 30 | 0 |
| BS | Batch Status | 125 | 58 | 43 | 24 | 0 |
| EC | Enrichment Context | 125 | 91 | 19 | 15 | 0 |
| MC | Multi-Step Comparative | 125 | 65 | 35 | 25 | 0 |
| RC | Reference Compliance | 125 | 75 | 9 | 41 | 0 |
| SQ | Scoring Quantitative | 125 | 75 | 34 | 15 | 1 |
| TT | Temporal Transaction | 125 | 80 | 37 | 8 | 0 |
| **Overall** | **All categories** | **1000** | 600 | 233 | 166 | 1 |

Other status details: `OTHER`: 1.

## Kimi K2 Thinking 1T — Base SPARQL

Source: `base_sparql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 77 | 34 | 14 | 0 |
| ARC | At-Risk Critical | 125 | 47 | 34 | 44 | 0 |
| BS | Batch Status | 125 | 64 | 28 | 33 | 0 |
| EC | Enrichment Context | 125 | 23 | 27 | 72 | 3 |
| MC | Multi-Step Comparative | 125 | 15 | 45 | 47 | 18 |
| RC | Reference Compliance | 125 | 90 | 2 | 33 | 0 |
| SQ | Scoring Quantitative | 125 | 57 | 15 | 53 | 0 |
| TT | Temporal Transaction | 125 | 52 | 67 | 6 | 0 |
| **Overall** | **All categories** | **1000** | 425 | 252 | 302 | 21 |

Other status details: `OTHER`: 21.

## Kimi K2 Thinking 1T — Base SQL

Source: `base_sql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 87 | 27 | 11 | 0 |
| ARC | At-Risk Critical | 125 | 61 | 26 | 38 | 0 |
| BS | Batch Status | 125 | 69 | 29 | 25 | 2 |
| EC | Enrichment Context | 125 | 85 | 25 | 15 | 0 |
| MC | Multi-Step Comparative | 125 | 67 | 21 | 28 | 9 |
| RC | Reference Compliance | 125 | 80 | 8 | 37 | 0 |
| SQ | Scoring Quantitative | 125 | 92 | 15 | 16 | 2 |
| TT | Temporal Transaction | 125 | 74 | 39 | 10 | 2 |
| **Overall** | **All categories** | **1000** | 615 | 190 | 180 | 15 |

Other status details: `OTHER`: 14, `TOKEN_OUTPUT_ERROR`: 1.

## Kimi K2 Thinking 1T — GraphRAG Local

Source: `graph_rag_local_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 26 | 90 | 8 | 1 |
| ARC | At-Risk Critical | 125 | 1 | 100 | 24 | 0 |
| BS | Batch Status | 125 | 3 | 119 | 2 | 1 |
| EC | Enrichment Context | 125 | 13 | 106 | 6 | 0 |
| MC | Multi-Step Comparative | 125 | 0 | 125 | 0 | 0 |
| RC | Reference Compliance | 125 | 14 | 108 | 3 | 0 |
| SQ | Scoring Quantitative | 125 | 1 | 115 | 9 | 0 |
| TT | Temporal Transaction | 125 | 3 | 121 | 0 | 1 |
| **Overall** | **All categories** | **1000** | 61 | 884 | 52 | 3 |

Other status details: `CRASH`: 3.

## Kimi K2 Thinking 1T — Parallel SPARQL

Source: `parallel_sparql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 67 | 54 | 4 | 0 |
| ARC | At-Risk Critical | 125 | 18 | 87 | 20 | 0 |
| BS | Batch Status | 125 | 58 | 53 | 14 | 0 |
| EC | Enrichment Context | 125 | 19 | 64 | 42 | 0 |
| MC | Multi-Step Comparative | 125 | 7 | 106 | 12 | 0 |
| RC | Reference Compliance | 125 | 87 | 19 | 19 | 0 |
| SQ | Scoring Quantitative | 125 | 39 | 55 | 31 | 0 |
| TT | Temporal Transaction | 125 | 29 | 95 | 1 | 0 |
| **Overall** | **All categories** | **1000** | 324 | 533 | 143 | 0 |

Other status details: None.

## Kimi K2 Thinking 1T — Parallel SQL

Source: `parallel_sql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 80 | 40 | 5 | 0 |
| ARC | At-Risk Critical | 125 | 66 | 33 | 26 | 0 |
| BS | Batch Status | 125 | 53 | 50 | 22 | 0 |
| EC | Enrichment Context | 125 | 65 | 48 | 12 | 0 |
| MC | Multi-Step Comparative | 125 | 29 | 88 | 8 | 0 |
| RC | Reference Compliance | 125 | 80 | 15 | 30 | 0 |
| SQ | Scoring Quantitative | 125 | 65 | 47 | 13 | 0 |
| TT | Temporal Transaction | 125 | 66 | 49 | 10 | 0 |
| **Overall** | **All categories** | **1000** | 504 | 370 | 126 | 0 |

Other status details: None.

## Gemma 3 27B IT — Base SPARQL

Source: `base_sparql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 36 | 79 | 10 | 0 |
| ARC | At-Risk Critical | 125 | 35 | 53 | 37 | 0 |
| BS | Batch Status | 125 | 44 | 53 | 28 | 0 |
| EC | Enrichment Context | 125 | 5 | 76 | 33 | 11 |
| MC | Multi-Step Comparative | 125 | 1 | 80 | 1 | 43 |
| RC | Reference Compliance | 125 | 54 | 47 | 21 | 3 |
| SQ | Scoring Quantitative | 125 | 25 | 80 | 15 | 5 |
| TT | Temporal Transaction | 125 | 19 | 89 | 6 | 11 |
| **Overall** | **All categories** | **1000** | 219 | 557 | 151 | 73 |

Other status details: `OTHER`: 73.

## Gemma 3 27B IT — Base SQL

Source: `base_sql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 88 | 31 | 6 | 0 |
| ARC | At-Risk Critical | 125 | 65 | 19 | 41 | 0 |
| BS | Batch Status | 125 | 74 | 29 | 22 | 0 |
| EC | Enrichment Context | 125 | 72 | 36 | 16 | 1 |
| MC | Multi-Step Comparative | 125 | 19 | 58 | 43 | 5 |
| RC | Reference Compliance | 125 | 88 | 1 | 36 | 0 |
| SQ | Scoring Quantitative | 125 | 61 | 45 | 19 | 0 |
| TT | Temporal Transaction | 125 | 78 | 34 | 13 | 0 |
| **Overall** | **All categories** | **1000** | 545 | 253 | 196 | 6 |

Other status details: `OTHER`: 6.

## Gemma 3 27B IT — GraphRAG Local

Source: `graph_rag_local_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 29 | 70 | 7 | 19 |
| ARC | At-Risk Critical | 125 | 0 | 89 | 10 | 26 |
| BS | Batch Status | 125 | 1 | 73 | 2 | 49 |
| EC | Enrichment Context | 125 | 5 | 71 | 11 | 38 |
| MC | Multi-Step Comparative | 125 | 0 | 102 | 0 | 23 |
| RC | Reference Compliance | 125 | 11 | 91 | 1 | 22 |
| SQ | Scoring Quantitative | 125 | 1 | 91 | 5 | 28 |
| TT | Temporal Transaction | 125 | 2 | 62 | 0 | 61 |
| **Overall** | **All categories** | **1000** | 49 | 649 | 36 | 266 |

Other status details: `CRASH`: 266.

## Gemma 3 27B IT — Parallel SPARQL

Source: `parallel_sparql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 54 | 64 | 7 | 0 |
| ARC | At-Risk Critical | 125 | 28 | 65 | 32 | 0 |
| BS | Batch Status | 125 | 32 | 70 | 23 | 0 |
| EC | Enrichment Context | 125 | 8 | 94 | 23 | 0 |
| MC | Multi-Step Comparative | 125 | 1 | 123 | 1 | 0 |
| RC | Reference Compliance | 125 | 54 | 55 | 16 | 0 |
| SQ | Scoring Quantitative | 125 | 22 | 84 | 19 | 0 |
| TT | Temporal Transaction | 125 | 19 | 102 | 4 | 0 |
| **Overall** | **All categories** | **1000** | 218 | 657 | 125 | 0 |

Other status details: None.

## Gemma 3 27B IT — Parallel SQL

Source: `parallel_sql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 86 | 33 | 6 | 0 |
| ARC | At-Risk Critical | 125 | 66 | 18 | 41 | 0 |
| BS | Batch Status | 125 | 74 | 27 | 24 | 0 |
| EC | Enrichment Context | 125 | 69 | 44 | 12 | 0 |
| MC | Multi-Step Comparative | 125 | 20 | 74 | 31 | 0 |
| RC | Reference Compliance | 125 | 85 | 2 | 38 | 0 |
| SQ | Scoring Quantitative | 125 | 52 | 50 | 23 | 0 |
| TT | Temporal Transaction | 125 | 82 | 33 | 10 | 0 |
| **Overall** | **All categories** | **1000** | 534 | 281 | 185 | 0 |

Other status details: None.

## DeepSeek V3.2 685B — Base SPARQL

Source: `base_sparql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 50 | 66 | 6 | 3 |
| ARC | At-Risk Critical | 125 | 65 | 33 | 27 | 0 |
| BS | Batch Status | 125 | 51 | 50 | 22 | 2 |
| EC | Enrichment Context | 125 | 21 | 53 | 47 | 4 |
| MC | Multi-Step Comparative | 125 | 25 | 81 | 2 | 17 |
| RC | Reference Compliance | 125 | 88 | 6 | 31 | 0 |
| SQ | Scoring Quantitative | 125 | 41 | 50 | 32 | 2 |
| TT | Temporal Transaction | 125 | 64 | 51 | 6 | 4 |
| **Overall** | **All categories** | **1000** | 405 | 390 | 173 | 32 |

Other status details: `OTHER`: 32.

## DeepSeek V3.2 685B — Base SQL

Source: `base_sql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 97 | 19 | 9 | 0 |
| ARC | At-Risk Critical | 125 | 55 | 24 | 46 | 0 |
| BS | Batch Status | 125 | 68 | 37 | 20 | 0 |
| EC | Enrichment Context | 125 | 83 | 23 | 19 | 0 |
| MC | Multi-Step Comparative | 125 | 29 | 31 | 63 | 2 |
| RC | Reference Compliance | 125 | 79 | 1 | 45 | 0 |
| SQ | Scoring Quantitative | 125 | 86 | 13 | 26 | 0 |
| TT | Temporal Transaction | 125 | 84 | 31 | 10 | 0 |
| **Overall** | **All categories** | **1000** | 581 | 179 | 238 | 2 |

Other status details: `OTHER`: 2.

## DeepSeek V3.2 685B — GraphRAG Local

Source: `graph_rag_local_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 33 | 84 | 8 | 0 |
| ARC | At-Risk Critical | 125 | 1 | 109 | 15 | 0 |
| BS | Batch Status | 125 | 3 | 116 | 5 | 1 |
| EC | Enrichment Context | 125 | 12 | 99 | 14 | 0 |
| MC | Multi-Step Comparative | 125 | 0 | 124 | 1 | 0 |
| RC | Reference Compliance | 125 | 14 | 103 | 8 | 0 |
| SQ | Scoring Quantitative | 125 | 1 | 116 | 8 | 0 |
| TT | Temporal Transaction | 125 | 3 | 118 | 4 | 0 |
| **Overall** | **All categories** | **1000** | 67 | 869 | 63 | 1 |

Other status details: `CRASH`: 1.

## DeepSeek V3.2 685B — Parallel SPARQL

Source: `parallel_sparql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 33 | 88 | 4 | 0 |
| ARC | At-Risk Critical | 125 | 36 | 70 | 19 | 0 |
| BS | Batch Status | 125 | 43 | 67 | 15 | 0 |
| EC | Enrichment Context | 125 | 12 | 90 | 23 | 0 |
| MC | Multi-Step Comparative | 125 | 17 | 107 | 1 | 0 |
| RC | Reference Compliance | 125 | 81 | 22 | 22 | 0 |
| SQ | Scoring Quantitative | 125 | 34 | 69 | 22 | 0 |
| TT | Temporal Transaction | 125 | 47 | 78 | 0 | 0 |
| **Overall** | **All categories** | **1000** | 303 | 591 | 106 | 0 |

Other status details: None.

## DeepSeek V3.2 685B — Parallel SQL

Source: `parallel_sql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 88 | 27 | 10 | 0 |
| ARC | At-Risk Critical | 125 | 53 | 30 | 42 | 0 |
| BS | Batch Status | 125 | 62 | 38 | 25 | 0 |
| EC | Enrichment Context | 125 | 72 | 40 | 13 | 0 |
| MC | Multi-Step Comparative | 125 | 15 | 76 | 34 | 0 |
| RC | Reference Compliance | 125 | 78 | 8 | 39 | 0 |
| SQ | Scoring Quantitative | 125 | 71 | 39 | 15 | 0 |
| TT | Temporal Transaction | 125 | 74 | 47 | 4 | 0 |
| **Overall** | **All categories** | **1000** | 513 | 305 | 182 | 0 |

Other status details: None.
