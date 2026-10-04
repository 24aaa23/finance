# DAIL-SQL grading results by 125-question category

The report contains exactly 125 questions from each of the eight benchmark source categories. All questions were graded by `gpt-5-mini`.

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

## Results

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
