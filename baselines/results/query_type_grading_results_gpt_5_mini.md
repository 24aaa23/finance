# GPT-5 Mini grading results by query type

Counts are grouped by the CSV `Query Type` field. Each pipeline is reported independently.
The requested semantic grades are shown explicitly; `OTHER / ERROR` contains all remaining statuses so every table reconciles to 1,000 questions.

## Overall

| Pipeline | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 1000 | 495 | 182 | 311 | 12 |
| Base SQL | 1000 | 662 | 105 | 228 | 5 |
| GraphRAG Local | 1000 | 68 | 876 | 54 | 2 |
| Parallel SPARQL | 1000 | 454 | 326 | 220 | 0 |
| Parallel SQL | 1000 | 632 | 168 | 198 | 2 |

## Base SPARQL

Source: `base_sparql_dynamic_namespace_1000q_20261002_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 100 | 25 | 83 | 4 |
| Comparative | 15 | 0 | 2 | 13 | 0 |
| Composite Reasoning | 143 | 54 | 52 | 33 | 4 |
| Direct Retrieval | 34 | 30 | 4 | 0 | 0 |
| Exception Detection | 53 | 47 | 0 | 6 | 0 |
| Filtered List | 103 | 42 | 13 | 48 | 0 |
| Multi-Relational | 212 | 101 | 27 | 83 | 1 |
| Multi-step Comparative | 55 | 0 | 20 | 33 | 2 |
| Ranking | 65 | 52 | 6 | 6 | 1 |
| Reference Compliance | 39 | 37 | 1 | 1 | 0 |
| Rule-Based Detection | 29 | 18 | 6 | 5 | 0 |
| Temporal | 40 | 14 | 26 | 0 | 0 |
| **Overall** | **1000** | 495 | 182 | 311 | 12 |

Other status details: `OTHER`: 11, `TOKEN_OUTPUT_ERROR`: 1.

## Base SQL

Source: `base_pipeline_sql_schema_only_prompt_1000q_20261001_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 160 | 32 | 19 | 1 |
| Comparative | 15 | 7 | 3 | 5 | 0 |
| Composite Reasoning | 143 | 82 | 24 | 36 | 1 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 47 | 2 | 4 | 0 |
| Filtered List | 103 | 35 | 5 | 62 | 1 |
| Multi-Relational | 212 | 133 | 17 | 62 | 0 |
| Multi-step Comparative | 55 | 29 | 5 | 20 | 1 |
| Ranking | 65 | 54 | 6 | 5 | 0 |
| Reference Compliance | 39 | 23 | 8 | 8 | 0 |
| Rule-Based Detection | 29 | 20 | 2 | 6 | 1 |
| Temporal | 40 | 38 | 1 | 1 | 0 |
| **Overall** | **1000** | 662 | 105 | 228 | 5 |

Other status details: `OTHER`: 4, `TOKEN_OUTPUT_ERROR`: 1.

## GraphRAG Local

Source: `graph_rag_local_domain_neutral_prompt_1000q_20261001_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 2 | 203 | 7 | 0 |
| Comparative | 15 | 0 | 14 | 1 | 0 |
| Composite Reasoning | 143 | 2 | 139 | 2 | 0 |
| Direct Retrieval | 34 | 30 | 4 | 0 | 0 |
| Exception Detection | 53 | 3 | 49 | 1 | 0 |
| Filtered List | 103 | 2 | 86 | 15 | 0 |
| Multi-Relational | 212 | 18 | 175 | 18 | 1 |
| Multi-step Comparative | 55 | 0 | 53 | 2 | 0 |
| Ranking | 65 | 0 | 64 | 0 | 1 |
| Reference Compliance | 39 | 11 | 23 | 5 | 0 |
| Rule-Based Detection | 29 | 0 | 26 | 3 | 0 |
| Temporal | 40 | 0 | 40 | 0 | 0 |
| **Overall** | **1000** | 68 | 876 | 54 | 2 |

Other status details: `CRASH`: 1, `TOKEN_OUTPUT_ERROR`: 1.

## Parallel SPARQL

Source: `parallel_sparql_schema_only_prompt_parser_lock_1000q_20261002_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 102 | 55 | 55 | 0 |
| Comparative | 15 | 0 | 9 | 6 | 0 |
| Composite Reasoning | 143 | 56 | 59 | 28 | 0 |
| Direct Retrieval | 34 | 30 | 4 | 0 | 0 |
| Exception Detection | 53 | 46 | 7 | 0 | 0 |
| Filtered List | 103 | 26 | 33 | 44 | 0 |
| Multi-Relational | 212 | 90 | 48 | 74 | 0 |
| Multi-step Comparative | 55 | 0 | 51 | 4 | 0 |
| Ranking | 65 | 43 | 19 | 3 | 0 |
| Reference Compliance | 39 | 33 | 6 | 0 | 0 |
| Rule-Based Detection | 29 | 18 | 6 | 5 | 0 |
| Temporal | 40 | 10 | 29 | 1 | 0 |
| **Overall** | **1000** | 454 | 326 | 220 | 0 |

Other status details: None.

## Parallel SQL

Source: `parallel_sql_schema_only_prompt_1000q_20261001_graded_gpt_5_mini.csv`

| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 146 | 48 | 18 | 0 |
| Comparative | 15 | 7 | 5 | 3 | 0 |
| Composite Reasoning | 143 | 76 | 29 | 38 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 46 | 5 | 1 | 1 |
| Filtered List | 103 | 44 | 7 | 51 | 1 |
| Multi-Relational | 212 | 121 | 31 | 60 | 0 |
| Multi-step Comparative | 55 | 24 | 19 | 12 | 0 |
| Ranking | 65 | 55 | 8 | 2 | 0 |
| Reference Compliance | 39 | 22 | 10 | 7 | 0 |
| Rule-Based Detection | 29 | 18 | 6 | 5 | 0 |
| Temporal | 40 | 39 | 0 | 1 | 0 |
| **Overall** | **1000** | 632 | 168 | 198 | 2 |

Other status details: `OTHER`: 2.
