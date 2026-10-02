# GPT-5 Mini grading results by 125-question category

Counts are grouped by the eight source datasets in the 1,000-question benchmark.
Every pipeline contains exactly 125 questions from each category.
`OTHER / ERROR` contains non-semantic statuses so every table reconciles exactly.

## Category codes

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

| Pipeline | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 1000 | 495 | 182 | 311 | 12 |
| Base SQL | 1000 | 662 | 105 | 228 | 5 |
| GraphRAG Local | 1000 | 68 | 876 | 54 | 2 |
| Parallel SPARQL | 1000 | 454 | 326 | 220 | 0 |
| Parallel SQL | 1000 | 632 | 168 | 198 | 2 |

## Base SPARQL

Source: `base_sparql_dynamic_namespace_1000q_20261002_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 82 | 27 | 16 | 0 |
| ARC | At-Risk Critical | 125 | 68 | 18 | 39 | 0 |
| BS | Batch Status | 125 | 86 | 10 | 28 | 1 |
| EC | Enrichment Context | 125 | 28 | 18 | 75 | 4 |
| MC | Multi-Step Comparative | 125 | 12 | 45 | 62 | 6 |
| RC | Reference Compliance | 125 | 99 | 2 | 24 | 0 |
| SQ | Scoring Quantitative | 125 | 55 | 13 | 56 | 1 |
| TT | Temporal Transaction | 125 | 65 | 49 | 11 | 0 |
| **Overall** | **All categories** | **1000** | 495 | 182 | 311 | 12 |

Other status details: `OTHER`: 11, `TOKEN_OUTPUT_ERROR`: 1.

## Base SQL

Source: `base_pipeline_sql_schema_only_prompt_1000q_20261001_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 93 | 19 | 13 | 0 |
| ARC | At-Risk Critical | 125 | 76 | 4 | 44 | 1 |
| BS | Batch Status | 125 | 97 | 1 | 27 | 0 |
| EC | Enrichment Context | 125 | 75 | 29 | 20 | 1 |
| MC | Multi-Step Comparative | 125 | 62 | 18 | 43 | 2 |
| RC | Reference Compliance | 125 | 79 | 8 | 38 | 0 |
| SQ | Scoring Quantitative | 125 | 87 | 9 | 28 | 1 |
| TT | Temporal Transaction | 125 | 93 | 17 | 15 | 0 |
| **Overall** | **All categories** | **1000** | 662 | 105 | 228 | 5 |

Other status details: `OTHER`: 4, `TOKEN_OUTPUT_ERROR`: 1.

## GraphRAG Local

Source: `graph_rag_local_domain_neutral_prompt_1000q_20261001_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 30 | 93 | 2 | 0 |
| ARC | At-Risk Critical | 125 | 1 | 103 | 21 | 0 |
| BS | Batch Status | 125 | 4 | 115 | 5 | 1 |
| EC | Enrichment Context | 125 | 17 | 104 | 4 | 0 |
| MC | Multi-Step Comparative | 125 | 0 | 121 | 3 | 1 |
| RC | Reference Compliance | 125 | 14 | 103 | 8 | 0 |
| SQ | Scoring Quantitative | 125 | 1 | 115 | 9 | 0 |
| TT | Temporal Transaction | 125 | 1 | 122 | 2 | 0 |
| **Overall** | **All categories** | **1000** | 68 | 876 | 54 | 2 |

Other status details: `CRASH`: 1, `TOKEN_OUTPUT_ERROR`: 1.

## Parallel SPARQL

Source: `parallel_sparql_schema_only_prompt_parser_lock_1000q_20261002_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 79 | 31 | 15 | 0 |
| ARC | At-Risk Critical | 125 | 65 | 30 | 30 | 0 |
| BS | Batch Status | 125 | 87 | 9 | 29 | 0 |
| EC | Enrichment Context | 125 | 26 | 51 | 48 | 0 |
| MC | Multi-Step Comparative | 125 | 6 | 100 | 19 | 0 |
| RC | Reference Compliance | 125 | 86 | 13 | 26 | 0 |
| SQ | Scoring Quantitative | 125 | 45 | 30 | 50 | 0 |
| TT | Temporal Transaction | 125 | 60 | 62 | 3 | 0 |
| **Overall** | **All categories** | **1000** | 454 | 326 | 220 | 0 |

Other status details: None.

## Parallel SQL

Source: `parallel_sql_schema_only_prompt_1000q_20261001_graded_gpt_5_mini.csv`

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 89 | 22 | 14 | 0 |
| ARC | At-Risk Critical | 125 | 71 | 17 | 36 | 1 |
| BS | Batch Status | 125 | 85 | 11 | 29 | 0 |
| EC | Enrichment Context | 125 | 65 | 40 | 20 | 0 |
| MC | Multi-Step Comparative | 125 | 58 | 31 | 36 | 0 |
| RC | Reference Compliance | 125 | 82 | 13 | 30 | 0 |
| SQ | Scoring Quantitative | 125 | 84 | 17 | 23 | 1 |
| TT | Temporal Transaction | 125 | 98 | 17 | 10 | 0 |
| **Overall** | **All categories** | **1000** | 632 | 168 | 198 | 2 |

Other status details: `OTHER`: 2.
