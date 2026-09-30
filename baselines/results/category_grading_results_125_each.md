# Grading results by 125-question category

GPT-5.6 TERA grading counts grouped by the eight source categories in the
1,000-question benchmark. Every category contains exactly 125 questions.
Each pipeline is reported independently.

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

## Base SPARQL

| Code | Category | Total | MATCH | MISMATCH | PARTIAL |
|---|---|---:|---:|---:|---:|
| BM | Benchmark | 125 | 74 | 42 | 9 |
| ARC | At-Risk Critical | 125 | 94 | 30 | 1 |
| BS | Batch Status | 125 | 115 | 5 | 5 |
| EC | Enrichment Context | 125 | 35 | 45 | 45 |
| MC | Multi-Step Comparative | 125 | 25 | 58 | 42 |
| RC | Reference Compliance | 125 | 114 | 9 | 2 |
| SQ | Scoring Quantitative | 125 | 69 | 35 | 21 |
| TT | Temporal Transaction | 125 | 92 | 33 | 0 |
| **Overall** | **All categories** | **1000** | **618** | **257** | **125** |

## Base SQL

| Code | Category | Total | MATCH | MISMATCH | PARTIAL |
|---|---|---:|---:|---:|---:|
| BM | Benchmark | 125 | 124 | 1 | 0 |
| ARC | At-Risk Critical | 125 | 114 | 5 | 6 |
| BS | Batch Status | 125 | 108 | 8 | 9 |
| EC | Enrichment Context | 125 | 90 | 21 | 14 |
| MC | Multi-Step Comparative | 125 | 53 | 11 | 61 |
| RC | Reference Compliance | 125 | 116 | 1 | 8 |
| SQ | Scoring Quantitative | 125 | 100 | 15 | 10 |
| TT | Temporal Transaction | 125 | 110 | 13 | 2 |
| **Overall** | **All categories** | **1000** | **815** | **75** | **110** |

## GraphRAG Local

| Code | Category | Total | MATCH | MISMATCH | PARTIAL |
|---|---|---:|---:|---:|---:|
| BM | Benchmark | 125 | 30 | 93 | 2 |
| ARC | At-Risk Critical | 125 | 1 | 106 | 18 |
| BS | Batch Status | 125 | 2 | 120 | 3 |
| EC | Enrichment Context | 125 | 12 | 111 | 2 |
| MC | Multi-Step Comparative | 125 | 0 | 125 | 0 |
| RC | Reference Compliance | 125 | 12 | 107 | 6 |
| SQ | Scoring Quantitative | 125 | 1 | 122 | 2 |
| TT | Temporal Transaction | 125 | 2 | 120 | 3 |
| **Overall** | **All categories** | **1000** | **60** | **904** | **36** |

## Parallel SPARQL

| Code | Category | Total | MATCH | MISMATCH | PARTIAL |
|---|---|---:|---:|---:|---:|
| BM | Benchmark | 125 | 48 | 76 | 1 |
| ARC | At-Risk Critical | 125 | 33 | 87 | 5 |
| BS | Batch Status | 125 | 101 | 22 | 2 |
| EC | Enrichment Context | 125 | 14 | 58 | 53 |
| MC | Multi-Step Comparative | 125 | 11 | 99 | 15 |
| RC | Reference Compliance | 125 | 97 | 28 | 0 |
| SQ | Scoring Quantitative | 125 | 27 | 69 | 29 |
| TT | Temporal Transaction | 125 | 51 | 74 | 0 |
| **Overall** | **All categories** | **1000** | **382** | **513** | **105** |

## Parallel SQL

| Code | Category | Total | MATCH | MISMATCH | PARTIAL |
|---|---|---:|---:|---:|---:|
| BM | Benchmark | 125 | 119 | 6 | 0 |
| ARC | At-Risk Critical | 125 | 116 | 8 | 1 |
| BS | Batch Status | 125 | 104 | 16 | 5 |
| EC | Enrichment Context | 125 | 97 | 26 | 2 |
| MC | Multi-Step Comparative | 125 | 53 | 38 | 34 |
| RC | Reference Compliance | 125 | 119 | 1 | 5 |
| SQ | Scoring Quantitative | 125 | 97 | 24 | 4 |
| TT | Temporal Transaction | 125 | 101 | 22 | 2 |
| **Overall** | **All categories** | **1000** | **806** | **141** | **53** |
