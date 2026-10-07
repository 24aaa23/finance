# Proprietary models: category-wise grading analysis

This report covers three pipeline-runner models, six baselines per model, and 1,000 questions per baseline. Results were graded by `gpt-5-mini` and grouped by the eight 125-question source categories.

All 18 graded files were validated to contain 1,000 unique question IDs and no API/error statuses. The unchanged grader emitted `OTHER` for 43 of 18,000 rows, so that label is retained explicitly rather than reassigned; every table reconciles exactly.

## Overall model totals across six baselines

| Model | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| GPT-6.1-Sol | 6000 | 3048 | 1667 | 1284 | 1 |
| Gemini-3.8-Flash | 6000 | 3044 | 1682 | 1274 | 0 |
| Qwen3-Coder-480B | 6000 | 2436 | 2360 | 1162 | 42 |

## Category definitions

| Code | Category | Source dataset | Questions per baseline |
|---|---|---|---:|
| BM | Benchmark | `wealth_management_125_question_benchmark.csv` | 125 |
| ARC | At-Risk Critical | `wealth_management_at_risk_critical_125_questions.csv` | 125 |
| BS | Batch Status | `wealth_management_batch_status_125_questions.csv` | 125 |
| EC | Enrichment Context | `wealth_management_enrichment_context_125_questions.csv` | 125 |
| MC | Multi-Step Comparative | `wealth_management_multi_step_comparative_125_questions.csv` | 125 |
| RC | Reference Compliance | `wealth_management_reference_compliance_125_questions.csv` | 125 |
| SQ | Scoring Quantitative | `wealth_management_scoring_quantitative_125_questions.csv` | 125 |
| TT | Temporal Transaction | `wealth_management_temporal_transaction_125_questions.csv` | 125 |

## GPT-6.1-Sol

### Model total by category across six baselines

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 750 | 469 | 242 | 39 | 0 |
| ARC | At-Risk Critical | 750 | 458 | 181 | 111 | 0 |
| BS | Batch Status | 750 | 428 | 194 | 128 | 0 |
| EC | Enrichment Context | 750 | 326 | 187 | 237 | 0 |
| MC | Multi-Step Comparative | 750 | 145 | 280 | 325 | 0 |
| RC | Reference Compliance | 750 | 428 | 132 | 190 | 0 |
| SQ | Scoring Quantitative | 750 | 460 | 135 | 154 | 1 |
| TT | Temporal Transaction | 750 | 334 | 316 | 100 | 0 |
| **Overall** | **All categories** | **6000** | **3048** | **1667** | **1284** | **1** |

### Baseline totals

| Baseline | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 1000 | 513 | 160 | 327 | 0 |
| Base SQL | 1000 | 641 | 141 | 218 | 0 |
| GraphRAG Local | 1000 | 68 | 867 | 65 | 0 |
| Parallel SPARQL | 1000 | 494 | 230 | 276 | 0 |
| Parallel SQL | 1000 | 633 | 191 | 175 | 1 |
| DAIL-SQL | 1000 | 699 | 78 | 223 | 0 |
| **Overall** | **6000** | **3048** | **1667** | **1284** | **1** |

### Base SPARQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 73 | 41 | 11 | 0 |
| ARC | At-Risk Critical | 125 | 92 | 17 | 16 | 0 |
| BS | Batch Status | 125 | 68 | 22 | 35 | 0 |
| EC | Enrichment Context | 125 | 31 | 20 | 74 | 0 |
| MC | Multi-Step Comparative | 125 | 22 | 18 | 85 | 0 |
| RC | Reference Compliance | 125 | 95 | 1 | 29 | 0 |
| SQ | Scoring Quantitative | 125 | 69 | 0 | 56 | 0 |
| TT | Temporal Transaction | 125 | 63 | 41 | 21 | 0 |
| **Overall** | **All categories** | **1000** | **513** | **160** | **327** | **0** |

### Base SQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 93 | 26 | 6 | 0 |
| ARC | At-Risk Critical | 125 | 95 | 19 | 11 | 0 |
| BS | Batch Status | 125 | 99 | 5 | 21 | 0 |
| EC | Enrichment Context | 125 | 80 | 17 | 28 | 0 |
| MC | Multi-Step Comparative | 125 | 32 | 23 | 70 | 0 |
| RC | Reference Compliance | 125 | 70 | 9 | 46 | 0 |
| SQ | Scoring Quantitative | 125 | 106 | 4 | 15 | 0 |
| TT | Temporal Transaction | 125 | 66 | 38 | 21 | 0 |
| **Overall** | **All categories** | **1000** | **641** | **141** | **218** | **0** |

### GraphRAG Local: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 31 | 91 | 3 | 0 |
| ARC | At-Risk Critical | 125 | 1 | 96 | 28 | 0 |
| BS | Batch Status | 125 | 3 | 116 | 6 | 0 |
| EC | Enrichment Context | 125 | 15 | 105 | 5 | 0 |
| MC | Multi-Step Comparative | 125 | 0 | 125 | 0 | 0 |
| RC | Reference Compliance | 125 | 14 | 103 | 8 | 0 |
| SQ | Scoring Quantitative | 125 | 1 | 112 | 12 | 0 |
| TT | Temporal Transaction | 125 | 3 | 119 | 3 | 0 |
| **Overall** | **All categories** | **1000** | **68** | **867** | **65** | **0** |

### Parallel SPARQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 72 | 50 | 3 | 0 |
| ARC | At-Risk Critical | 125 | 91 | 18 | 16 | 0 |
| BS | Batch Status | 125 | 65 | 34 | 26 | 0 |
| EC | Enrichment Context | 125 | 30 | 19 | 76 | 0 |
| MC | Multi-Step Comparative | 125 | 16 | 43 | 66 | 0 |
| RC | Reference Compliance | 125 | 90 | 10 | 25 | 0 |
| SQ | Scoring Quantitative | 125 | 68 | 13 | 44 | 0 |
| TT | Temporal Transaction | 125 | 62 | 43 | 20 | 0 |
| **Overall** | **All categories** | **1000** | **494** | **230** | **276** | **0** |

### Parallel SQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 93 | 26 | 6 | 0 |
| ARC | At-Risk Critical | 125 | 91 | 20 | 14 | 0 |
| BS | Batch Status | 125 | 97 | 10 | 18 | 0 |
| EC | Enrichment Context | 125 | 73 | 24 | 28 | 0 |
| MC | Multi-Step Comparative | 125 | 36 | 51 | 38 | 0 |
| RC | Reference Compliance | 125 | 73 | 9 | 43 | 0 |
| SQ | Scoring Quantitative | 125 | 106 | 6 | 12 | 1 |
| TT | Temporal Transaction | 125 | 64 | 45 | 16 | 0 |
| **Overall** | **All categories** | **1000** | **633** | **191** | **175** | **1** |

### DAIL-SQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 107 | 8 | 10 | 0 |
| ARC | At-Risk Critical | 125 | 88 | 11 | 26 | 0 |
| BS | Batch Status | 125 | 96 | 7 | 22 | 0 |
| EC | Enrichment Context | 125 | 97 | 2 | 26 | 0 |
| MC | Multi-Step Comparative | 125 | 39 | 20 | 66 | 0 |
| RC | Reference Compliance | 125 | 86 | 0 | 39 | 0 |
| SQ | Scoring Quantitative | 125 | 110 | 0 | 15 | 0 |
| TT | Temporal Transaction | 125 | 76 | 30 | 19 | 0 |
| **Overall** | **All categories** | **1000** | **699** | **78** | **223** | **0** |

## Gemini-3.8-Flash

### Model total by category across six baselines

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 750 | 478 | 235 | 37 | 0 |
| ARC | At-Risk Critical | 750 | 397 | 168 | 185 | 0 |
| BS | Batch Status | 750 | 462 | 152 | 136 | 0 |
| EC | Enrichment Context | 750 | 321 | 231 | 198 | 0 |
| MC | Multi-Step Comparative | 750 | 168 | 273 | 309 | 0 |
| RC | Reference Compliance | 750 | 444 | 115 | 191 | 0 |
| SQ | Scoring Quantitative | 750 | 417 | 153 | 180 | 0 |
| TT | Temporal Transaction | 750 | 357 | 355 | 38 | 0 |
| **Overall** | **All categories** | **6000** | **3044** | **1682** | **1274** | **0** |

### Baseline totals

| Baseline | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 1000 | 516 | 178 | 306 | 0 |
| Base SQL | 1000 | 612 | 140 | 248 | 0 |
| GraphRAG Local | 1000 | 69 | 874 | 57 | 0 |
| Parallel SPARQL | 1000 | 516 | 221 | 263 | 0 |
| Parallel SQL | 1000 | 571 | 225 | 204 | 0 |
| DAIL-SQL | 1000 | 760 | 44 | 196 | 0 |
| **Overall** | **6000** | **3044** | **1682** | **1274** | **0** |

### Base SPARQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 85 | 34 | 6 | 0 |
| ARC | At-Risk Critical | 125 | 73 | 17 | 35 | 0 |
| BS | Batch Status | 125 | 94 | 6 | 25 | 0 |
| EC | Enrichment Context | 125 | 27 | 21 | 77 | 0 |
| MC | Multi-Step Comparative | 125 | 18 | 33 | 74 | 0 |
| RC | Reference Compliance | 125 | 104 | 1 | 20 | 0 |
| SQ | Scoring Quantitative | 125 | 59 | 4 | 62 | 0 |
| TT | Temporal Transaction | 125 | 56 | 62 | 7 | 0 |
| **Overall** | **All categories** | **1000** | **516** | **178** | **306** | **0** |

### Base SQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 90 | 30 | 5 | 0 |
| ARC | At-Risk Critical | 125 | 75 | 13 | 37 | 0 |
| BS | Batch Status | 125 | 96 | 4 | 25 | 0 |
| EC | Enrichment Context | 125 | 87 | 17 | 21 | 0 |
| MC | Multi-Step Comparative | 125 | 29 | 19 | 77 | 0 |
| RC | Reference Compliance | 125 | 67 | 4 | 54 | 0 |
| SQ | Scoring Quantitative | 125 | 103 | 6 | 16 | 0 |
| TT | Temporal Transaction | 125 | 65 | 47 | 13 | 0 |
| **Overall** | **All categories** | **1000** | **612** | **140** | **248** | **0** |

### GraphRAG Local: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 32 | 89 | 4 | 0 |
| ARC | At-Risk Critical | 125 | 1 | 98 | 26 | 0 |
| BS | Batch Status | 125 | 1 | 117 | 7 | 0 |
| EC | Enrichment Context | 125 | 17 | 103 | 5 | 0 |
| MC | Multi-Step Comparative | 125 | 0 | 125 | 0 | 0 |
| RC | Reference Compliance | 125 | 14 | 103 | 8 | 0 |
| SQ | Scoring Quantitative | 125 | 1 | 119 | 5 | 0 |
| TT | Temporal Transaction | 125 | 3 | 120 | 2 | 0 |
| **Overall** | **All categories** | **1000** | **69** | **874** | **57** | **0** |

### Parallel SPARQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 85 | 34 | 6 | 0 |
| ARC | At-Risk Critical | 125 | 76 | 24 | 25 | 0 |
| BS | Batch Status | 125 | 90 | 10 | 25 | 0 |
| EC | Enrichment Context | 125 | 24 | 37 | 64 | 0 |
| MC | Multi-Step Comparative | 125 | 23 | 44 | 58 | 0 |
| RC | Reference Compliance | 125 | 101 | 0 | 24 | 0 |
| SQ | Scoring Quantitative | 125 | 54 | 11 | 60 | 0 |
| TT | Temporal Transaction | 125 | 63 | 61 | 1 | 0 |
| **Overall** | **All categories** | **1000** | **516** | **221** | **263** | **0** |

### Parallel SQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 80 | 39 | 6 | 0 |
| ARC | At-Risk Critical | 125 | 75 | 12 | 38 | 0 |
| BS | Batch Status | 125 | 83 | 14 | 28 | 0 |
| EC | Enrichment Context | 125 | 67 | 45 | 13 | 0 |
| MC | Multi-Step Comparative | 125 | 24 | 42 | 59 | 0 |
| RC | Reference Compliance | 125 | 77 | 7 | 41 | 0 |
| SQ | Scoring Quantitative | 125 | 102 | 9 | 14 | 0 |
| TT | Temporal Transaction | 125 | 63 | 57 | 5 | 0 |
| **Overall** | **All categories** | **1000** | **571** | **225** | **204** | **0** |

### DAIL-SQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 106 | 9 | 10 | 0 |
| ARC | At-Risk Critical | 125 | 97 | 4 | 24 | 0 |
| BS | Batch Status | 125 | 98 | 1 | 26 | 0 |
| EC | Enrichment Context | 125 | 99 | 8 | 18 | 0 |
| MC | Multi-Step Comparative | 125 | 74 | 10 | 41 | 0 |
| RC | Reference Compliance | 125 | 81 | 0 | 44 | 0 |
| SQ | Scoring Quantitative | 125 | 98 | 4 | 23 | 0 |
| TT | Temporal Transaction | 125 | 107 | 8 | 10 | 0 |
| **Overall** | **All categories** | **1000** | **760** | **44** | **196** | **0** |

## Qwen3-Coder-480B

### Model total by category across six baselines

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 750 | 417 | 273 | 58 | 2 |
| ARC | At-Risk Critical | 750 | 305 | 234 | 211 | 0 |
| BS | Batch Status | 750 | 321 | 284 | 145 | 0 |
| EC | Enrichment Context | 750 | 306 | 258 | 181 | 5 |
| MC | Multi-Step Comparative | 750 | 123 | 408 | 190 | 29 |
| RC | Reference Compliance | 750 | 356 | 227 | 167 | 0 |
| SQ | Scoring Quantitative | 750 | 364 | 252 | 130 | 4 |
| TT | Temporal Transaction | 750 | 244 | 424 | 80 | 2 |
| **Overall** | **All categories** | **6000** | **2436** | **2360** | **1162** | **42** |

### Baseline totals

| Baseline | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 1000 | 314 | 464 | 185 | 37 |
| Base SQL | 1000 | 522 | 213 | 261 | 4 |
| GraphRAG Local | 1000 | 58 | 841 | 101 | 0 |
| Parallel SPARQL | 1000 | 345 | 503 | 152 | 0 |
| Parallel SQL | 1000 | 517 | 238 | 245 | 0 |
| DAIL-SQL | 1000 | 680 | 101 | 218 | 1 |
| **Overall** | **6000** | **2436** | **2360** | **1162** | **42** |

### Base SPARQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 52 | 65 | 6 | 2 |
| ARC | At-Risk Critical | 125 | 55 | 34 | 36 | 0 |
| BS | Batch Status | 125 | 51 | 52 | 22 | 0 |
| EC | Enrichment Context | 125 | 30 | 34 | 57 | 4 |
| MC | Multi-Step Comparative | 125 | 9 | 82 | 8 | 26 |
| RC | Reference Compliance | 125 | 50 | 62 | 13 | 0 |
| SQ | Scoring Quantitative | 125 | 46 | 46 | 30 | 3 |
| TT | Temporal Transaction | 125 | 21 | 89 | 13 | 2 |
| **Overall** | **All categories** | **1000** | **314** | **464** | **185** | **37** |

### Base SQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 90 | 28 | 7 | 0 |
| ARC | At-Risk Critical | 125 | 46 | 36 | 43 | 0 |
| BS | Batch Status | 125 | 62 | 28 | 35 | 0 |
| EC | Enrichment Context | 125 | 74 | 29 | 21 | 1 |
| MC | Multi-Step Comparative | 125 | 24 | 31 | 67 | 3 |
| RC | Reference Compliance | 125 | 71 | 0 | 54 | 0 |
| SQ | Scoring Quantitative | 125 | 93 | 15 | 17 | 0 |
| TT | Temporal Transaction | 125 | 62 | 46 | 17 | 0 |
| **Overall** | **All categories** | **1000** | **522** | **213** | **261** | **4** |

### GraphRAG Local: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 29 | 83 | 13 | 0 |
| ARC | At-Risk Critical | 125 | 1 | 96 | 28 | 0 |
| BS | Batch Status | 125 | 3 | 112 | 10 | 0 |
| EC | Enrichment Context | 125 | 12 | 98 | 15 | 0 |
| MC | Multi-Step Comparative | 125 | 0 | 116 | 9 | 0 |
| RC | Reference Compliance | 125 | 10 | 108 | 7 | 0 |
| SQ | Scoring Quantitative | 125 | 0 | 110 | 15 | 0 |
| TT | Temporal Transaction | 125 | 3 | 118 | 4 | 0 |
| **Overall** | **All categories** | **1000** | **58** | **841** | **101** | **0** |

### Parallel SPARQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 61 | 57 | 7 | 0 |
| ARC | At-Risk Critical | 125 | 84 | 16 | 25 | 0 |
| BS | Batch Status | 125 | 52 | 55 | 18 | 0 |
| EC | Enrichment Context | 125 | 26 | 51 | 48 | 0 |
| MC | Multi-Step Comparative | 125 | 8 | 113 | 4 | 0 |
| RC | Reference Compliance | 125 | 56 | 56 | 13 | 0 |
| SQ | Scoring Quantitative | 125 | 42 | 54 | 29 | 0 |
| TT | Temporal Transaction | 125 | 16 | 101 | 8 | 0 |
| **Overall** | **All categories** | **1000** | **345** | **503** | **152** | **0** |

### Parallel SQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 87 | 30 | 8 | 0 |
| ARC | At-Risk Critical | 125 | 43 | 39 | 43 | 0 |
| BS | Batch Status | 125 | 61 | 29 | 35 | 0 |
| EC | Enrichment Context | 125 | 69 | 35 | 21 | 0 |
| MC | Multi-Step Comparative | 125 | 21 | 45 | 59 | 0 |
| RC | Reference Compliance | 125 | 79 | 1 | 45 | 0 |
| SQ | Scoring Quantitative | 125 | 95 | 13 | 17 | 0 |
| TT | Temporal Transaction | 125 | 62 | 46 | 17 | 0 |
| **Overall** | **All categories** | **1000** | **517** | **238** | **245** | **0** |

### DAIL-SQL: categories

| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---|---:|---:|---:|---:|---:|
| BM | Benchmark | 125 | 98 | 10 | 17 | 0 |
| ARC | At-Risk Critical | 125 | 76 | 13 | 36 | 0 |
| BS | Batch Status | 125 | 92 | 8 | 25 | 0 |
| EC | Enrichment Context | 125 | 95 | 11 | 19 | 0 |
| MC | Multi-Step Comparative | 125 | 61 | 21 | 43 | 0 |
| RC | Reference Compliance | 125 | 90 | 0 | 35 | 0 |
| SQ | Scoring Quantitative | 125 | 88 | 14 | 22 | 1 |
| TT | Temporal Transaction | 125 | 80 | 24 | 21 | 0 |
| **Overall** | **All categories** | **1000** | **680** | **101** | **218** | **1** |
