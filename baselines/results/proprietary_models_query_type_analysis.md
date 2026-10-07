# Proprietary models: query-type grading analysis

This report covers three pipeline-runner models, six baselines per model, and 1,000 questions per baseline. Results were graded by `gpt-5-mini` and grouped by the CSV `Query Type` field.

All 18 graded files were validated to contain 1,000 unique question IDs and no API/error statuses. The unchanged grader emitted `OTHER` for 43 of 18,000 rows, so that label is retained explicitly rather than reassigned; every table reconciles exactly.

## Overall model totals across six baselines

| Model | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| GPT-6.1-Sol | 6000 | 3048 | 1667 | 1284 | 1 |
| Gemini-3.8-Flash | 6000 | 3044 | 1682 | 1274 | 0 |
| Qwen3-Coder-480B | 6000 | 2436 | 2360 | 1162 | 42 |

## GPT-6.1-Sol

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

### Base SPARQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 57 | 52 | 103 | 0 |
| Comparative | 15 | 0 | 2 | 13 | 0 |
| Composite Reasoning | 143 | 74 | 36 | 33 | 0 |
| Direct Retrieval | 34 | 29 | 5 | 0 | 0 |
| Exception Detection | 53 | 48 | 2 | 3 | 0 |
| Filtered List | 103 | 42 | 2 | 59 | 0 |
| Multi-Relational | 212 | 123 | 32 | 57 | 0 |
| Multi-step Comparative | 55 | 0 | 9 | 46 | 0 |
| Ranking | 65 | 50 | 7 | 8 | 0 |
| Reference Compliance | 39 | 39 | 0 | 0 | 0 |
| Rule-Based Detection | 29 | 25 | 0 | 4 | 0 |
| Temporal | 40 | 26 | 13 | 1 | 0 |
| **Overall** | **1000** | **513** | **160** | **327** | **0** |

### Base SQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 161 | 27 | 24 | 0 |
| Comparative | 15 | 7 | 1 | 7 | 0 |
| Composite Reasoning | 143 | 66 | 48 | 29 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 51 | 2 | 0 | 0 |
| Filtered List | 103 | 46 | 4 | 53 | 0 |
| Multi-Relational | 212 | 150 | 29 | 33 | 0 |
| Multi-step Comparative | 55 | 9 | 5 | 41 | 0 |
| Ranking | 65 | 52 | 4 | 9 | 0 |
| Reference Compliance | 39 | 13 | 9 | 17 | 0 |
| Rule-Based Detection | 29 | 25 | 0 | 4 | 0 |
| Temporal | 40 | 27 | 12 | 1 | 0 |
| **Overall** | **1000** | **641** | **141** | **218** | **0** |

### GraphRAG Local: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 2 | 203 | 7 | 0 |
| Comparative | 15 | 0 | 15 | 0 | 0 |
| Composite Reasoning | 143 | 2 | 139 | 2 | 0 |
| Direct Retrieval | 34 | 31 | 3 | 0 | 0 |
| Exception Detection | 53 | 3 | 44 | 6 | 0 |
| Filtered List | 103 | 3 | 76 | 24 | 0 |
| Multi-Relational | 212 | 16 | 177 | 19 | 0 |
| Multi-step Comparative | 55 | 0 | 55 | 0 | 0 |
| Ranking | 65 | 0 | 65 | 0 | 0 |
| Reference Compliance | 39 | 11 | 25 | 3 | 0 |
| Rule-Based Detection | 29 | 0 | 25 | 4 | 0 |
| Temporal | 40 | 0 | 40 | 0 | 0 |
| **Overall** | **1000** | **68** | **867** | **65** | **0** |

### Parallel SPARQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 54 | 71 | 87 | 0 |
| Comparative | 15 | 0 | 3 | 12 | 0 |
| Composite Reasoning | 143 | 66 | 57 | 20 | 0 |
| Direct Retrieval | 34 | 30 | 4 | 0 | 0 |
| Exception Detection | 53 | 45 | 8 | 0 | 0 |
| Filtered List | 103 | 41 | 8 | 54 | 0 |
| Multi-Relational | 212 | 121 | 39 | 52 | 0 |
| Multi-step Comparative | 55 | 0 | 18 | 37 | 0 |
| Ranking | 65 | 48 | 10 | 7 | 0 |
| Reference Compliance | 39 | 38 | 1 | 0 | 0 |
| Rule-Based Detection | 29 | 24 | 0 | 5 | 0 |
| Temporal | 40 | 27 | 11 | 2 | 0 |
| **Overall** | **1000** | **494** | **230** | **276** | **0** |

### Parallel SQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 156 | 33 | 23 | 0 |
| Comparative | 15 | 7 | 5 | 3 | 0 |
| Composite Reasoning | 143 | 67 | 56 | 20 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 50 | 3 | 0 | 0 |
| Filtered List | 103 | 49 | 7 | 46 | 1 |
| Multi-Relational | 212 | 143 | 38 | 31 | 0 |
| Multi-step Comparative | 55 | 13 | 20 | 22 | 0 |
| Ranking | 65 | 50 | 9 | 6 | 0 |
| Reference Compliance | 39 | 11 | 8 | 20 | 0 |
| Rule-Based Detection | 29 | 26 | 0 | 3 | 0 |
| Temporal | 40 | 27 | 12 | 1 | 0 |
| **Overall** | **1000** | **633** | **191** | **175** | **1** |

### DAIL-SQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 172 | 15 | 25 | 0 |
| Comparative | 15 | 10 | 0 | 5 | 0 |
| Composite Reasoning | 143 | 81 | 32 | 30 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 50 | 0 | 3 | 0 |
| Filtered List | 103 | 47 | 2 | 54 | 0 |
| Multi-Relational | 212 | 159 | 12 | 41 | 0 |
| Multi-step Comparative | 55 | 14 | 4 | 37 | 0 |
| Ranking | 65 | 54 | 3 | 8 | 0 |
| Reference Compliance | 39 | 27 | 0 | 12 | 0 |
| Rule-Based Detection | 29 | 23 | 0 | 6 | 0 |
| Temporal | 40 | 28 | 10 | 2 | 0 |
| **Overall** | **1000** | **699** | **78** | **223** | **0** |

## Gemini-3.8-Flash

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

### Base SPARQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 94 | 26 | 92 | 0 |
| Comparative | 15 | 1 | 2 | 12 | 0 |
| Composite Reasoning | 143 | 65 | 42 | 36 | 0 |
| Direct Retrieval | 34 | 30 | 4 | 0 | 0 |
| Exception Detection | 53 | 47 | 3 | 3 | 0 |
| Filtered List | 103 | 46 | 18 | 39 | 0 |
| Multi-Relational | 212 | 106 | 33 | 73 | 0 |
| Multi-step Comparative | 55 | 0 | 16 | 39 | 0 |
| Ranking | 65 | 55 | 3 | 7 | 0 |
| Reference Compliance | 39 | 39 | 0 | 0 | 0 |
| Rule-Based Detection | 29 | 20 | 4 | 5 | 0 |
| Temporal | 40 | 13 | 27 | 0 | 0 |
| **Overall** | **1000** | **516** | **178** | **306** | **0** |

### Base SQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 159 | 29 | 24 | 0 |
| Comparative | 15 | 6 | 1 | 8 | 0 |
| Composite Reasoning | 143 | 73 | 32 | 38 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 48 | 4 | 1 | 0 |
| Filtered List | 103 | 34 | 18 | 51 | 0 |
| Multi-Relational | 212 | 136 | 25 | 51 | 0 |
| Multi-step Comparative | 55 | 9 | 5 | 41 | 0 |
| Ranking | 65 | 53 | 6 | 6 | 0 |
| Reference Compliance | 39 | 14 | 4 | 21 | 0 |
| Rule-Based Detection | 29 | 19 | 5 | 5 | 0 |
| Temporal | 40 | 27 | 11 | 2 | 0 |
| **Overall** | **1000** | **612** | **140** | **248** | **0** |

### GraphRAG Local: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 0 | 211 | 1 | 0 |
| Comparative | 15 | 0 | 15 | 0 | 0 |
| Composite Reasoning | 143 | 2 | 141 | 0 | 0 |
| Direct Retrieval | 34 | 32 | 1 | 1 | 0 |
| Exception Detection | 53 | 3 | 44 | 6 | 0 |
| Filtered List | 103 | 3 | 79 | 21 | 0 |
| Multi-Relational | 212 | 18 | 173 | 21 | 0 |
| Multi-step Comparative | 55 | 0 | 55 | 0 | 0 |
| Ranking | 65 | 0 | 65 | 0 | 0 |
| Reference Compliance | 39 | 11 | 25 | 3 | 0 |
| Rule-Based Detection | 29 | 0 | 25 | 4 | 0 |
| Temporal | 40 | 0 | 40 | 0 | 0 |
| **Overall** | **1000** | **69** | **874** | **57** | **0** |

### Parallel SPARQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 95 | 36 | 81 | 0 |
| Comparative | 15 | 1 | 7 | 7 | 0 |
| Composite Reasoning | 143 | 62 | 49 | 32 | 0 |
| Direct Retrieval | 34 | 30 | 4 | 0 | 0 |
| Exception Detection | 53 | 49 | 4 | 0 | 0 |
| Filtered List | 103 | 40 | 21 | 42 | 0 |
| Multi-Relational | 212 | 109 | 43 | 60 | 0 |
| Multi-step Comparative | 55 | 0 | 19 | 36 | 0 |
| Ranking | 65 | 57 | 8 | 0 | 0 |
| Reference Compliance | 39 | 39 | 0 | 0 | 0 |
| Rule-Based Detection | 29 | 20 | 4 | 5 | 0 |
| Temporal | 40 | 14 | 26 | 0 | 0 |
| **Overall** | **1000** | **516** | **221** | **263** | **0** |

### Parallel SQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 137 | 62 | 13 | 0 |
| Comparative | 15 | 6 | 4 | 5 | 0 |
| Composite Reasoning | 143 | 74 | 40 | 29 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 44 | 5 | 4 | 0 |
| Filtered List | 103 | 44 | 18 | 41 | 0 |
| Multi-Relational | 212 | 116 | 45 | 51 | 0 |
| Multi-step Comparative | 55 | 6 | 19 | 30 | 0 |
| Ranking | 65 | 52 | 8 | 5 | 0 |
| Reference Compliance | 39 | 14 | 5 | 20 | 0 |
| Rule-Based Detection | 29 | 19 | 5 | 5 | 0 |
| Temporal | 40 | 25 | 14 | 1 | 0 |
| **Overall** | **1000** | **571** | **225** | **204** | **0** |

### DAIL-SQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 181 | 12 | 19 | 0 |
| Comparative | 15 | 9 | 3 | 3 | 0 |
| Composite Reasoning | 143 | 97 | 16 | 30 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 48 | 2 | 3 | 0 |
| Filtered List | 103 | 45 | 3 | 55 | 0 |
| Multi-Relational | 212 | 162 | 6 | 44 | 0 |
| Multi-step Comparative | 55 | 34 | 1 | 20 | 0 |
| Ranking | 65 | 64 | 0 | 1 | 0 |
| Reference Compliance | 39 | 23 | 0 | 16 | 0 |
| Rule-Based Detection | 29 | 24 | 0 | 5 | 0 |
| Temporal | 40 | 39 | 1 | 0 | 0 |
| **Overall** | **1000** | **760** | **44** | **196** | **0** |

## Qwen3-Coder-480B

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

### Base SPARQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 39 | 118 | 44 | 11 |
| Comparative | 15 | 0 | 12 | 1 | 2 |
| Composite Reasoning | 143 | 35 | 68 | 26 | 14 |
| Direct Retrieval | 34 | 27 | 7 | 0 | 0 |
| Exception Detection | 53 | 18 | 30 | 5 | 0 |
| Filtered List | 103 | 27 | 47 | 29 | 0 |
| Multi-Relational | 212 | 77 | 72 | 63 | 0 |
| Multi-step Comparative | 55 | 0 | 44 | 1 | 10 |
| Ranking | 65 | 39 | 20 | 6 | 0 |
| Reference Compliance | 39 | 29 | 8 | 2 | 0 |
| Rule-Based Detection | 29 | 19 | 4 | 6 | 0 |
| Temporal | 40 | 4 | 34 | 2 | 0 |
| **Overall** | **1000** | **314** | **464** | **185** | **37** |

### Base SQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 139 | 51 | 21 | 1 |
| Comparative | 15 | 7 | 4 | 4 | 0 |
| Composite Reasoning | 143 | 41 | 70 | 30 | 2 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 45 | 5 | 3 | 0 |
| Filtered List | 103 | 27 | 10 | 66 | 0 |
| Multi-Relational | 212 | 115 | 34 | 63 | 0 |
| Multi-step Comparative | 55 | 6 | 3 | 45 | 1 |
| Ranking | 65 | 41 | 23 | 1 | 0 |
| Reference Compliance | 39 | 20 | 0 | 19 | 0 |
| Rule-Based Detection | 29 | 20 | 3 | 6 | 0 |
| Temporal | 40 | 27 | 10 | 3 | 0 |
| **Overall** | **1000** | **522** | **213** | **261** | **4** |

### GraphRAG Local: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 2 | 195 | 15 | 0 |
| Comparative | 15 | 0 | 10 | 5 | 0 |
| Composite Reasoning | 143 | 1 | 136 | 6 | 0 |
| Direct Retrieval | 34 | 29 | 0 | 5 | 0 |
| Exception Detection | 53 | 3 | 45 | 5 | 0 |
| Filtered List | 103 | 3 | 81 | 19 | 0 |
| Multi-Relational | 212 | 13 | 169 | 30 | 0 |
| Multi-step Comparative | 55 | 0 | 51 | 4 | 0 |
| Ranking | 65 | 0 | 63 | 2 | 0 |
| Reference Compliance | 39 | 7 | 27 | 5 | 0 |
| Rule-Based Detection | 29 | 0 | 24 | 5 | 0 |
| Temporal | 40 | 0 | 40 | 0 | 0 |
| **Overall** | **1000** | **58** | **841** | **101** | **0** |

### Parallel SPARQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 36 | 137 | 39 | 0 |
| Comparative | 15 | 0 | 15 | 0 | 0 |
| Composite Reasoning | 143 | 50 | 74 | 19 | 0 |
| Direct Retrieval | 34 | 17 | 17 | 0 | 0 |
| Exception Detection | 53 | 22 | 28 | 3 | 0 |
| Filtered List | 103 | 32 | 48 | 23 | 0 |
| Multi-Relational | 212 | 101 | 57 | 54 | 0 |
| Multi-step Comparative | 55 | 0 | 54 | 1 | 0 |
| Ranking | 65 | 33 | 25 | 7 | 0 |
| Reference Compliance | 39 | 31 | 6 | 2 | 0 |
| Rule-Based Detection | 29 | 22 | 4 | 3 | 0 |
| Temporal | 40 | 1 | 38 | 1 | 0 |
| **Overall** | **1000** | **345** | **503** | **152** | **0** |

### Parallel SQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 138 | 55 | 19 | 0 |
| Comparative | 15 | 7 | 2 | 6 | 0 |
| Composite Reasoning | 143 | 36 | 81 | 26 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 46 | 4 | 3 | 0 |
| Filtered List | 103 | 36 | 11 | 56 | 0 |
| Multi-Relational | 212 | 111 | 37 | 64 | 0 |
| Multi-step Comparative | 55 | 4 | 12 | 39 | 0 |
| Ranking | 65 | 42 | 21 | 2 | 0 |
| Reference Compliance | 39 | 18 | 1 | 20 | 0 |
| Rule-Based Detection | 29 | 19 | 4 | 6 | 0 |
| Temporal | 40 | 26 | 10 | 4 | 0 |
| **Overall** | **1000** | **517** | **238** | **245** | **0** |

### DAIL-SQL: query types

| Query type | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 164 | 25 | 23 | 0 |
| Comparative | 15 | 11 | 2 | 2 | 0 |
| Composite Reasoning | 143 | 76 | 33 | 34 | 0 |
| Direct Retrieval | 34 | 34 | 0 | 0 | 0 |
| Exception Detection | 53 | 47 | 3 | 3 | 0 |
| Filtered List | 103 | 40 | 11 | 51 | 1 |
| Multi-Relational | 212 | 142 | 12 | 58 | 0 |
| Multi-step Comparative | 55 | 27 | 4 | 24 | 0 |
| Ranking | 65 | 49 | 9 | 7 | 0 |
| Reference Compliance | 39 | 30 | 0 | 9 | 0 |
| Rule-Based Detection | 29 | 23 | 0 | 6 | 0 |
| Temporal | 40 | 37 | 2 | 1 | 0 |
| **Overall** | **1000** | **680** | **101** | **218** | **1** |
