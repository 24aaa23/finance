# Domain-context baseline grading by query type

Counts are grouped by the CSV `Query Type` field. Each pipeline is reported independently.
The requested semantic grades are shown explicitly; `OTHER / ERROR` contains all remaining statuses so every table reconciles to 1,000 questions.

## Overall

| Pipeline | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 1000 | 452 | 253 | 288 | 7 |
| Base SQL | 1000 | 681 | 92 | 226 | 1 |
| GraphRAG Local | 1000 | 62 | 875 | 58 | 5 |
| Parallel SPARQL | 1000 | 401 | 386 | 212 | 1 |
| Parallel SQL | 1000 | 600 | 233 | 166 | 1 |

## Base SPARQL

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

## Base SQL

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

## GraphRAG Local

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

## Parallel SPARQL

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

## Parallel SQL

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
