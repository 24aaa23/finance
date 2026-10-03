# Domain-context baseline grading by 125-question category

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
| Base SPARQL | 1000 | 452 | 253 | 288 | 7 |
| Base SQL | 1000 | 681 | 92 | 226 | 1 |
| GraphRAG Local | 1000 | 62 | 875 | 58 | 5 |
| Parallel SPARQL | 1000 | 401 | 386 | 212 | 1 |
| Parallel SQL | 1000 | 600 | 233 | 166 | 1 |

## Base SPARQL

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

## Base SQL

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

## GraphRAG Local

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

## Parallel SPARQL

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

## Parallel SQL

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
