# Multi-model grading results by query type

All reports contain 1,000 questions graded by `gpt-5-mini`. `OTHER / ERROR` contains every status other than `MATCH`, `MISMATCH`, and `PARTIAL`.

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

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 80 | 56 | 75 | 1 |
| Comparative | 15 | 0 | 6 | 9 | 0 |
| Composite Reasoning | 143 | 59 | 66 | 14 | 4 |
| Direct Retrieval | 34 | 28 | 4 | 2 | 0 |
| Exception Detection | 53 | 46 | 2 | 4 | 1 |
| Filtered List | 103 | 33 | 20 | 50 | 0 |
| Multi-Relational | 212 | 79 | 39 | 94 | 0 |
| Multi-step Comparative | 55 | 0 | 22 | 32 | 1 |
| Ranking | 65 | 56 | 6 | 3 | 0 |
| Reference Compliance | 39 | 32 | 7 | 0 | 0 |
| Rule-Based Detection | 29 | 22 | 2 | 5 | 0 |
| Temporal | 40 | 17 | 23 | 0 | 0 |
| **Overall** | **1000** | 452 | 253 | 288 | 7 |

Other status details: `OTHER`: 7.

## GPT-OSS 120B — Base SQL

Source: `base_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 165 | 25 | 22 | 0 |
| Comparative | 15 | 9 | 2 | 4 | 0 |
| Composite Reasoning | 143 | 104 | 11 | 28 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 45 | 3 | 5 | 0 |
| Filtered List | 103 | 29 | 11 | 62 | 1 |
| Multi-Relational | 212 | 135 | 22 | 55 | 0 |
| Multi-step Comparative | 55 | 29 | 1 | 25 | 0 |
| Ranking | 65 | 56 | 7 | 2 | 0 |
| Reference Compliance | 39 | 17 | 4 | 18 | 0 |
| Rule-Based Detection | 29 | 22 | 3 | 4 | 0 |
| Temporal | 40 | 36 | 3 | 1 | 0 |
| **Overall** | **1000** | 681 | 92 | 226 | 1 |

Other status details: `TOKEN_OUTPUT_ERROR`: 1.

## GPT-OSS 120B — GraphRAG Local

Source: `graph_rag_local_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 2 | 199 | 11 | 0 |
| Comparative | 15 | 0 | 14 | 1 | 0 |
| Composite Reasoning | 143 | 2 | 139 | 2 | 0 |
| Direct Retrieval | 34 | 27 | 3 | 4 | 0 |
| Exception Detection | 53 | 2 | 48 | 3 | 0 |
| Filtered List | 103 | 3 | 88 | 12 | 0 |
| Multi-Relational | 212 | 15 | 177 | 19 | 1 |
| Multi-step Comparative | 55 | 0 | 55 | 0 | 0 |
| Ranking | 65 | 0 | 64 | 0 | 1 |
| Reference Compliance | 39 | 11 | 24 | 3 | 1 |
| Rule-Based Detection | 29 | 0 | 26 | 3 | 0 |
| Temporal | 40 | 0 | 38 | 0 | 2 |
| **Overall** | **1000** | 62 | 875 | 58 | 5 |

Other status details: `CRASH`: 4, `TOKEN_OUTPUT_ERROR`: 1.

## GPT-OSS 120B — Parallel SPARQL

Source: `parallel_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 67 | 89 | 56 | 0 |
| Comparative | 15 | 2 | 9 | 4 | 0 |
| Composite Reasoning | 143 | 38 | 79 | 26 | 0 |
| Direct Retrieval | 34 | 30 | 4 | 0 | 0 |
| Exception Detection | 53 | 44 | 7 | 2 | 0 |
| Filtered List | 103 | 39 | 34 | 29 | 1 |
| Multi-Relational | 212 | 68 | 64 | 80 | 0 |
| Multi-step Comparative | 55 | 0 | 46 | 9 | 0 |
| Ranking | 65 | 54 | 9 | 2 | 0 |
| Reference Compliance | 39 | 32 | 7 | 0 | 0 |
| Rule-Based Detection | 29 | 18 | 7 | 4 | 0 |
| Temporal | 40 | 9 | 31 | 0 | 0 |
| **Overall** | **1000** | 401 | 386 | 212 | 1 |

Other status details: `OTHER`: 1.

## GPT-OSS 120B — Parallel SQL

Source: `parallel_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 128 | 69 | 15 | 0 |
| Comparative | 15 | 6 | 8 | 1 | 0 |
| Composite Reasoning | 143 | 95 | 25 | 23 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 46 | 6 | 1 | 0 |
| Filtered List | 103 | 37 | 22 | 43 | 1 |
| Multi-Relational | 212 | 111 | 50 | 51 | 0 |
| Multi-step Comparative | 55 | 22 | 25 | 8 | 0 |
| Ranking | 65 | 47 | 15 | 3 | 0 |
| Reference Compliance | 39 | 17 | 4 | 18 | 0 |
| Rule-Based Detection | 29 | 22 | 4 | 3 | 0 |
| Temporal | 40 | 35 | 5 | 0 | 0 |
| **Overall** | **1000** | 600 | 233 | 166 | 1 |

Other status details: `OTHER`: 1.

## Kimi K2 Thinking 1T — Base SPARQL

Source: `base_sparql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 72 | 61 | 76 | 3 |
| Comparative | 15 | 2 | 2 | 11 | 0 |
| Composite Reasoning | 143 | 42 | 65 | 22 | 14 |
| Direct Retrieval | 34 | 29 | 4 | 1 | 0 |
| Exception Detection | 53 | 46 | 5 | 2 | 0 |
| Filtered List | 103 | 33 | 15 | 55 | 0 |
| Multi-Relational | 212 | 80 | 34 | 98 | 0 |
| Multi-step Comparative | 55 | 0 | 25 | 26 | 4 |
| Ranking | 65 | 53 | 8 | 4 | 0 |
| Reference Compliance | 39 | 38 | 1 | 0 | 0 |
| Rule-Based Detection | 29 | 18 | 4 | 7 | 0 |
| Temporal | 40 | 12 | 28 | 0 | 0 |
| **Overall** | **1000** | 425 | 252 | 302 | 21 |

Other status details: `OTHER`: 21.

## Kimi K2 Thinking 1T — Base SQL

Source: `base_sql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 151 | 49 | 11 | 1 |
| Comparative | 15 | 11 | 1 | 3 | 0 |
| Composite Reasoning | 143 | 67 | 52 | 14 | 10 |
| Direct Retrieval | 34 | 31 | 0 | 3 | 0 |
| Exception Detection | 53 | 46 | 2 | 5 | 0 |
| Filtered List | 103 | 34 | 9 | 60 | 0 |
| Multi-Relational | 212 | 125 | 36 | 49 | 2 |
| Multi-step Comparative | 55 | 29 | 5 | 21 | 0 |
| Ranking | 65 | 40 | 22 | 1 | 2 |
| Reference Compliance | 39 | 23 | 8 | 8 | 0 |
| Rule-Based Detection | 29 | 21 | 3 | 5 | 0 |
| Temporal | 40 | 37 | 3 | 0 | 0 |
| **Overall** | **1000** | 615 | 190 | 180 | 15 |

Other status details: `OTHER`: 14, `TOKEN_OUTPUT_ERROR`: 1.

## Kimi K2 Thinking 1T — GraphRAG Local

Source: `graph_rag_local_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 2 | 203 | 6 | 1 |
| Comparative | 15 | 0 | 15 | 0 | 0 |
| Composite Reasoning | 143 | 2 | 139 | 2 | 0 |
| Direct Retrieval | 34 | 26 | 2 | 6 | 0 |
| Exception Detection | 53 | 3 | 48 | 2 | 0 |
| Filtered List | 103 | 3 | 93 | 6 | 1 |
| Multi-Relational | 212 | 14 | 174 | 23 | 1 |
| Multi-step Comparative | 55 | 0 | 55 | 0 | 0 |
| Ranking | 65 | 0 | 64 | 1 | 0 |
| Reference Compliance | 39 | 11 | 25 | 3 | 0 |
| Rule-Based Detection | 29 | 0 | 26 | 3 | 0 |
| Temporal | 40 | 0 | 40 | 0 | 0 |
| **Overall** | **1000** | 61 | 884 | 52 | 3 |

Other status details: `CRASH`: 3.

## Kimi K2 Thinking 1T — Parallel SPARQL

Source: `parallel_sparql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 67 | 92 | 53 | 0 |
| Comparative | 15 | 1 | 10 | 4 | 0 |
| Composite Reasoning | 143 | 14 | 122 | 7 | 0 |
| Direct Retrieval | 34 | 30 | 4 | 0 | 0 |
| Exception Detection | 53 | 45 | 8 | 0 | 0 |
| Filtered List | 103 | 25 | 50 | 28 | 0 |
| Multi-Relational | 212 | 58 | 111 | 43 | 0 |
| Multi-step Comparative | 55 | 0 | 49 | 6 | 0 |
| Ranking | 65 | 30 | 35 | 0 | 0 |
| Reference Compliance | 39 | 32 | 7 | 0 | 0 |
| Rule-Based Detection | 29 | 19 | 8 | 2 | 0 |
| Temporal | 40 | 3 | 37 | 0 | 0 |
| **Overall** | **1000** | 324 | 533 | 143 | 0 |

Other status details: None.

## Kimi K2 Thinking 1T — Parallel SQL

Source: `parallel_sql_kimi_k2_thinking_1t_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 107 | 93 | 12 | 0 |
| Comparative | 15 | 5 | 10 | 0 | 0 |
| Composite Reasoning | 143 | 59 | 70 | 14 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 41 | 12 | 0 | 0 |
| Filtered List | 103 | 37 | 20 | 46 | 0 |
| Multi-Relational | 212 | 110 | 65 | 37 | 0 |
| Multi-step Comparative | 55 | 7 | 42 | 6 | 0 |
| Ranking | 65 | 30 | 35 | 0 | 0 |
| Reference Compliance | 39 | 25 | 8 | 6 | 0 |
| Rule-Based Detection | 29 | 16 | 8 | 5 | 0 |
| Temporal | 40 | 33 | 7 | 0 | 0 |
| **Overall** | **1000** | 504 | 370 | 126 | 0 |

Other status details: None.

## Gemma 3 27B IT — Base SPARQL

Source: `base_sparql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 39 | 141 | 16 | 16 |
| Comparative | 15 | 0 | 11 | 0 | 4 |
| Composite Reasoning | 143 | 31 | 78 | 12 | 22 |
| Direct Retrieval | 34 | 0 | 34 | 0 | 0 |
| Exception Detection | 53 | 24 | 29 | 0 | 0 |
| Filtered List | 103 | 16 | 44 | 40 | 3 |
| Multi-Relational | 212 | 48 | 93 | 71 | 0 |
| Multi-step Comparative | 55 | 0 | 40 | 0 | 15 |
| Ranking | 65 | 11 | 41 | 4 | 9 |
| Reference Compliance | 39 | 27 | 10 | 1 | 1 |
| Rule-Based Detection | 29 | 8 | 14 | 7 | 0 |
| Temporal | 40 | 15 | 22 | 0 | 3 |
| **Overall** | **1000** | 219 | 557 | 151 | 73 |

Other status details: `OTHER`: 73.

## Gemma 3 27B IT — Base SQL

Source: `base_sql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 132 | 64 | 15 | 1 |
| Comparative | 15 | 3 | 8 | 4 | 0 |
| Composite Reasoning | 143 | 58 | 57 | 26 | 2 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 46 | 6 | 1 | 0 |
| Filtered List | 103 | 37 | 15 | 51 | 0 |
| Multi-Relational | 212 | 123 | 38 | 51 | 0 |
| Multi-step Comparative | 55 | 1 | 27 | 24 | 3 |
| Ranking | 65 | 32 | 26 | 7 | 0 |
| Reference Compliance | 39 | 27 | 1 | 11 | 0 |
| Rule-Based Detection | 29 | 19 | 4 | 6 | 0 |
| Temporal | 40 | 33 | 7 | 0 | 0 |
| **Overall** | **1000** | 545 | 253 | 196 | 6 |

Other status details: `OTHER`: 6.

## Gemma 3 27B IT — GraphRAG Local

Source: `graph_rag_local_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 2 | 110 | 5 | 95 |
| Comparative | 15 | 0 | 10 | 0 | 5 |
| Composite Reasoning | 143 | 1 | 110 | 2 | 30 |
| Direct Retrieval | 34 | 27 | 1 | 6 | 0 |
| Exception Detection | 53 | 3 | 42 | 1 | 7 |
| Filtered List | 103 | 2 | 75 | 2 | 24 |
| Multi-Relational | 212 | 6 | 149 | 17 | 40 |
| Multi-step Comparative | 55 | 0 | 42 | 0 | 13 |
| Ranking | 65 | 0 | 61 | 0 | 4 |
| Reference Compliance | 39 | 8 | 18 | 1 | 12 |
| Rule-Based Detection | 29 | 0 | 18 | 2 | 9 |
| Temporal | 40 | 0 | 13 | 0 | 27 |
| **Overall** | **1000** | 49 | 649 | 36 | 266 |

Other status details: `CRASH`: 266.

## Gemma 3 27B IT — Parallel SPARQL

Source: `parallel_sparql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 25 | 177 | 10 | 0 |
| Comparative | 15 | 0 | 15 | 0 | 0 |
| Composite Reasoning | 143 | 30 | 99 | 14 | 0 |
| Direct Retrieval | 34 | 23 | 11 | 0 | 0 |
| Exception Detection | 53 | 22 | 31 | 0 | 0 |
| Filtered List | 103 | 14 | 59 | 30 | 0 |
| Multi-Relational | 212 | 33 | 120 | 59 | 0 |
| Multi-step Comparative | 55 | 0 | 55 | 0 | 0 |
| Ranking | 65 | 12 | 47 | 6 | 0 |
| Reference Compliance | 39 | 30 | 8 | 1 | 0 |
| Rule-Based Detection | 29 | 15 | 9 | 5 | 0 |
| Temporal | 40 | 14 | 26 | 0 | 0 |
| **Overall** | **1000** | 218 | 657 | 125 | 0 |

Other status details: None.

## Gemma 3 27B IT — Parallel SQL

Source: `parallel_sql_gemma_3_27b_it_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 126 | 75 | 11 | 0 |
| Comparative | 15 | 3 | 8 | 4 | 0 |
| Composite Reasoning | 143 | 56 | 64 | 23 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 45 | 5 | 3 | 0 |
| Filtered List | 103 | 33 | 17 | 53 | 0 |
| Multi-Relational | 212 | 126 | 38 | 48 | 0 |
| Multi-step Comparative | 55 | 1 | 37 | 17 | 0 |
| Ranking | 65 | 31 | 26 | 8 | 0 |
| Reference Compliance | 39 | 24 | 2 | 13 | 0 |
| Rule-Based Detection | 29 | 21 | 4 | 4 | 0 |
| Temporal | 40 | 34 | 5 | 1 | 0 |
| **Overall** | **1000** | 534 | 281 | 185 | 0 |

Other status details: None.

## DeepSeek V3.2 685B — Base SPARQL

Source: `base_sparql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 59 | 110 | 33 | 10 |
| Comparative | 15 | 0 | 13 | 0 | 2 |
| Composite Reasoning | 143 | 43 | 79 | 17 | 4 |
| Direct Retrieval | 34 | 18 | 16 | 0 | 0 |
| Exception Detection | 53 | 47 | 4 | 2 | 0 |
| Filtered List | 103 | 26 | 25 | 52 | 0 |
| Multi-Relational | 212 | 91 | 62 | 59 | 0 |
| Multi-step Comparative | 55 | 0 | 44 | 0 | 11 |
| Ranking | 65 | 41 | 13 | 6 | 5 |
| Reference Compliance | 39 | 39 | 0 | 0 | 0 |
| Rule-Based Detection | 29 | 19 | 6 | 4 | 0 |
| Temporal | 40 | 22 | 18 | 0 | 0 |
| **Overall** | **1000** | 405 | 390 | 173 | 32 |

Other status details: `OTHER`: 32.

## DeepSeek V3.2 685B — Base SQL

Source: `base_sql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 147 | 42 | 23 | 0 |
| Comparative | 15 | 5 | 1 | 9 | 0 |
| Composite Reasoning | 143 | 55 | 56 | 30 | 2 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 45 | 5 | 3 | 0 |
| Filtered List | 103 | 37 | 10 | 56 | 0 |
| Multi-Relational | 212 | 127 | 36 | 49 | 0 |
| Multi-step Comparative | 55 | 9 | 2 | 44 | 0 |
| Ranking | 65 | 48 | 15 | 2 | 0 |
| Reference Compliance | 39 | 21 | 1 | 17 | 0 |
| Rule-Based Detection | 29 | 20 | 4 | 5 | 0 |
| Temporal | 40 | 33 | 7 | 0 | 0 |
| **Overall** | **1000** | 581 | 179 | 238 | 2 |

Other status details: `OTHER`: 2.

## DeepSeek V3.2 685B — GraphRAG Local

Source: `graph_rag_local_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 2 | 200 | 10 | 0 |
| Comparative | 15 | 0 | 14 | 1 | 0 |
| Composite Reasoning | 143 | 2 | 133 | 8 | 0 |
| Direct Retrieval | 34 | 33 | 0 | 1 | 0 |
| Exception Detection | 53 | 3 | 49 | 1 | 0 |
| Filtered List | 103 | 3 | 88 | 12 | 0 |
| Multi-Relational | 212 | 13 | 180 | 19 | 0 |
| Multi-step Comparative | 55 | 0 | 55 | 0 | 0 |
| Ranking | 65 | 0 | 64 | 1 | 0 |
| Reference Compliance | 39 | 11 | 21 | 7 | 0 |
| Rule-Based Detection | 29 | 0 | 25 | 3 | 1 |
| Temporal | 40 | 0 | 40 | 0 | 0 |
| **Overall** | **1000** | 67 | 869 | 63 | 1 |

Other status details: `CRASH`: 1.

## DeepSeek V3.2 685B — Parallel SPARQL

Source: `parallel_sparql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 48 | 141 | 23 | 0 |
| Comparative | 15 | 0 | 15 | 0 | 0 |
| Composite Reasoning | 143 | 28 | 112 | 3 | 0 |
| Direct Retrieval | 34 | 15 | 19 | 0 | 0 |
| Exception Detection | 53 | 43 | 8 | 2 | 0 |
| Filtered List | 103 | 21 | 42 | 40 | 0 |
| Multi-Relational | 212 | 52 | 127 | 33 | 0 |
| Multi-step Comparative | 55 | 0 | 55 | 0 | 0 |
| Ranking | 65 | 33 | 30 | 2 | 0 |
| Reference Compliance | 39 | 33 | 6 | 0 | 0 |
| Rule-Based Detection | 29 | 19 | 7 | 3 | 0 |
| Temporal | 40 | 11 | 29 | 0 | 0 |
| **Overall** | **1000** | 303 | 591 | 106 | 0 |

Other status details: None.

## DeepSeek V3.2 685B — Parallel SQL

Source: `parallel_sql_deepseek_v3_2_685b_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 128 | 71 | 13 | 0 |
| Comparative | 15 | 2 | 12 | 1 | 0 |
| Composite Reasoning | 143 | 42 | 76 | 25 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 45 | 5 | 3 | 0 |
| Filtered List | 103 | 42 | 21 | 40 | 0 |
| Multi-Relational | 212 | 123 | 42 | 47 | 0 |
| Multi-step Comparative | 55 | 3 | 25 | 27 | 0 |
| Ranking | 65 | 33 | 31 | 1 | 0 |
| Reference Compliance | 39 | 16 | 5 | 18 | 0 |
| Rule-Based Detection | 29 | 16 | 6 | 7 | 0 |
| Temporal | 40 | 29 | 11 | 0 | 0 |
| **Overall** | **1000** | 513 | 305 | 182 | 0 |

Other status details: None.
