# Proprietary models: difficulty grading analysis

This report covers three pipeline-runner models, six baselines per model, and 1,000 questions per baseline. Results were graded by `gpt-5-mini` and grouped by the CSV `Difficulty` field.

All 18 graded files were validated to contain 1,000 unique question IDs and no API/error statuses. The unchanged grader emitted `OTHER` for 43 of 18,000 rows, so that label is retained explicitly rather than reassigned; every table reconciles exactly.

## Overall model totals across six baselines

| Model | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| GPT-6.1-Sol | 6000 | 3048 | 1667 | 1284 | 1 |
| Gemini-3.8-Flash | 6000 | 3044 | 1682 | 1274 | 0 |
| Qwen3-Coder-480B | 6000 | 2436 | 2360 | 1162 | 42 |

## Benchmark difficulty distribution

| Difficulty | Questions per baseline |
|---|---:|
| Easy | 82 |
| Medium | 361 |
| Hard | 306 |
| Advanced | 124 |
| Expert | 127 |
| **Overall** | **1,000** |

## GPT-6.1-Sol

### Model total by difficulty across six baselines

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 492 | 385 | 47 | 60 | 0 |
| Medium | 2166 | 1309 | 551 | 305 | 1 |
| Hard | 1836 | 780 | 496 | 560 | 0 |
| Advanced | 744 | 388 | 236 | 120 | 0 |
| Expert | 762 | 186 | 337 | 239 | 0 |
| **Overall** | **6000** | **3048** | **1667** | **1284** | **1** |

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

### Base SPARQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 64 | 6 | 12 | 0 |
| Medium | 361 | 225 | 58 | 78 | 0 |
| Hard | 306 | 132 | 39 | 135 | 0 |
| Advanced | 124 | 56 | 23 | 45 | 0 |
| Expert | 127 | 36 | 34 | 57 | 0 |
| **Overall** | **1000** | **513** | **160** | **327** | **0** |

### Base SQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 78 | 1 | 3 | 0 |
| Medium | 361 | 276 | 41 | 44 | 0 |
| Hard | 306 | 163 | 38 | 105 | 0 |
| Advanced | 124 | 89 | 23 | 12 | 0 |
| Expert | 127 | 35 | 38 | 54 | 0 |
| **Overall** | **1000** | **641** | **141** | **218** | **0** |

### GraphRAG Local: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 31 | 35 | 16 | 0 |
| Medium | 361 | 28 | 305 | 28 | 0 |
| Hard | 306 | 6 | 285 | 15 | 0 |
| Advanced | 124 | 1 | 118 | 5 | 0 |
| Expert | 127 | 2 | 124 | 1 | 0 |
| **Overall** | **1000** | **68** | **867** | **65** | **0** |

### Parallel SPARQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 65 | 5 | 12 | 0 |
| Medium | 361 | 218 | 82 | 61 | 0 |
| Hard | 306 | 130 | 54 | 122 | 0 |
| Advanced | 124 | 51 | 34 | 39 | 0 |
| Expert | 127 | 30 | 55 | 42 | 0 |
| **Overall** | **1000** | **494** | **230** | **276** | **0** |

### Parallel SQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 76 | 0 | 6 | 0 |
| Medium | 361 | 267 | 47 | 46 | 1 |
| Hard | 306 | 167 | 56 | 83 | 0 |
| Advanced | 124 | 87 | 29 | 8 | 0 |
| Expert | 127 | 36 | 59 | 32 | 0 |
| **Overall** | **1000** | **633** | **191** | **175** | **1** |

### DAIL-SQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 71 | 0 | 11 | 0 |
| Medium | 361 | 295 | 18 | 48 | 0 |
| Hard | 306 | 182 | 24 | 100 | 0 |
| Advanced | 124 | 104 | 9 | 11 | 0 |
| Expert | 127 | 47 | 27 | 53 | 0 |
| **Overall** | **1000** | **699** | **78** | **223** | **0** |

## Gemini-3.8-Flash

### Model total by difficulty across six baselines

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 492 | 367 | 56 | 69 | 0 |
| Medium | 2166 | 1285 | 552 | 329 | 0 |
| Hard | 1836 | 790 | 539 | 507 | 0 |
| Advanced | 744 | 378 | 221 | 145 | 0 |
| Expert | 762 | 224 | 314 | 224 | 0 |
| **Overall** | **6000** | **3044** | **1682** | **1274** | **0** |

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

### Base SPARQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 66 | 5 | 11 | 0 |
| Medium | 361 | 229 | 55 | 77 | 0 |
| Hard | 306 | 136 | 51 | 119 | 0 |
| Advanced | 124 | 54 | 21 | 49 | 0 |
| Expert | 127 | 31 | 46 | 50 | 0 |
| **Overall** | **1000** | **516** | **178** | **306** | **0** |

### Base SQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 68 | 6 | 8 | 0 |
| Medium | 361 | 257 | 40 | 64 | 0 |
| Hard | 306 | 156 | 49 | 101 | 0 |
| Advanced | 124 | 90 | 15 | 19 | 0 |
| Expert | 127 | 41 | 30 | 56 | 0 |
| **Overall** | **1000** | **612** | **140** | **248** | **0** |

### GraphRAG Local: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 32 | 32 | 18 | 0 |
| Medium | 361 | 28 | 308 | 25 | 0 |
| Hard | 306 | 6 | 288 | 12 | 0 |
| Advanced | 124 | 1 | 121 | 2 | 0 |
| Expert | 127 | 2 | 125 | 0 | 0 |
| **Overall** | **1000** | **69** | **874** | **57** | **0** |

### Parallel SPARQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 65 | 8 | 9 | 0 |
| Medium | 361 | 236 | 64 | 61 | 0 |
| Hard | 306 | 135 | 67 | 104 | 0 |
| Advanced | 124 | 46 | 31 | 47 | 0 |
| Expert | 127 | 34 | 51 | 42 | 0 |
| **Overall** | **1000** | **516** | **221** | **263** | **0** |

### Parallel SQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 65 | 4 | 13 | 0 |
| Medium | 361 | 228 | 76 | 57 | 0 |
| Hard | 306 | 152 | 74 | 80 | 0 |
| Advanced | 124 | 89 | 24 | 11 | 0 |
| Expert | 127 | 37 | 47 | 43 | 0 |
| **Overall** | **1000** | **571** | **225** | **204** | **0** |

### DAIL-SQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 71 | 1 | 10 | 0 |
| Medium | 361 | 307 | 9 | 45 | 0 |
| Hard | 306 | 205 | 10 | 91 | 0 |
| Advanced | 124 | 98 | 9 | 17 | 0 |
| Expert | 127 | 79 | 15 | 33 | 0 |
| **Overall** | **1000** | **760** | **44** | **196** | **0** |

## Qwen3-Coder-480B

### Model total by difficulty across six baselines

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 492 | 313 | 106 | 73 | 0 |
| Medium | 2166 | 1035 | 798 | 326 | 7 |
| Hard | 1836 | 659 | 710 | 462 | 5 |
| Advanced | 744 | 303 | 283 | 154 | 4 |
| Expert | 762 | 126 | 463 | 147 | 26 |
| **Overall** | **6000** | **2436** | **2360** | **1162** | **42** |

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

### Base SPARQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 55 | 16 | 11 | 0 |
| Medium | 361 | 120 | 176 | 58 | 7 |
| Hard | 306 | 90 | 144 | 69 | 3 |
| Advanced | 124 | 34 | 47 | 39 | 4 |
| Expert | 127 | 15 | 81 | 8 | 23 |
| **Overall** | **1000** | **314** | **464** | **185** | **37** |

### Base SQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 58 | 12 | 12 | 0 |
| Medium | 361 | 233 | 57 | 71 | 0 |
| Hard | 306 | 142 | 63 | 100 | 1 |
| Advanced | 124 | 71 | 27 | 26 | 0 |
| Expert | 127 | 18 | 54 | 52 | 3 |
| **Overall** | **1000** | **522** | **213** | **261** | **4** |

### GraphRAG Local: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 29 | 33 | 20 | 0 |
| Medium | 361 | 21 | 303 | 37 | 0 |
| Hard | 306 | 6 | 276 | 24 | 0 |
| Advanced | 124 | 1 | 107 | 16 | 0 |
| Expert | 127 | 1 | 122 | 4 | 0 |
| **Overall** | **1000** | **58** | **841** | **101** | **0** |

### Parallel SPARQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 47 | 28 | 7 | 0 |
| Medium | 361 | 138 | 175 | 48 | 0 |
| Hard | 306 | 101 | 144 | 61 | 0 |
| Advanced | 124 | 39 | 54 | 31 | 0 |
| Expert | 127 | 20 | 102 | 5 | 0 |
| **Overall** | **1000** | **345** | **503** | **152** | **0** |

### Parallel SQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 56 | 13 | 13 | 0 |
| Medium | 361 | 238 | 61 | 62 | 0 |
| Hard | 306 | 144 | 61 | 101 | 0 |
| Advanced | 124 | 65 | 35 | 24 | 0 |
| Expert | 127 | 14 | 68 | 45 | 0 |
| **Overall** | **1000** | **517** | **238** | **245** | **0** |

### DAIL-SQL: difficulty

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 68 | 4 | 10 | 0 |
| Medium | 361 | 285 | 26 | 50 | 0 |
| Hard | 306 | 176 | 22 | 107 | 1 |
| Advanced | 124 | 93 | 13 | 18 | 0 |
| Expert | 127 | 58 | 36 | 33 | 0 |
| **Overall** | **1000** | **680** | **101** | **218** | **1** |
