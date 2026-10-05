# Difficulty-level grading analysis across all baselines and models

This report covers 24 independent 1,000-question outputs: six pipelines run with four models and graded by `gpt-5-mini`. `OTHER / ERROR` contains every status other than `MATCH`, `MISMATCH`, and `PARTIAL`.

The source data contains five difficulty levels. `Expert` is included so every pipeline total reconciles to 1,000 questions.

## Benchmark difficulty distribution

| Difficulty | Questions per pipeline |
|---|---:|
| Easy | 82 |
| Medium | 361 |
| Hard | 306 |
| Advanced | 124 |
| Expert | 127 |
| **Overall** | **1000** |

## GPT-OSS 120B

Model ID: `openai.gpt-oss-120b-1:0`

### Model total across six pipelines

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 492 | 318 | 98 | 75 | 1 |
| Medium | 2166 | 1245 | 595 | 319 | 7 |
| Hard | 1836 | 719 | 615 | 501 | 1 |
| Advanced | 744 | 349 | 274 | 118 | 3 |
| Expert | 762 | 301 | 318 | 139 | 4 |
| **Overall** | **6000** | **2932** | **1900** | **1152** | **16** |

### Pipeline detail

#### Base SPARQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 57 | 12 | 13 | 0 |
| Medium | 361 | 221 | 61 | 77 | 2 |
| Hard | 306 | 100 | 81 | 124 | 1 |
| Advanced | 124 | 47 | 31 | 46 | 0 |
| Expert | 127 | 27 | 68 | 28 | 4 |
| **Overall** | **1000** | **452** | **253** | **288** | **7** |

Other status details: `OTHER`: 7.

#### Base SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 57 | 8 | 16 | 1 |
| Medium | 361 | 276 | 33 | 52 | 0 |
| Hard | 306 | 169 | 27 | 110 | 0 |
| Advanced | 124 | 95 | 16 | 13 | 0 |
| Expert | 127 | 84 | 8 | 35 | 0 |
| **Overall** | **1000** | **681** | **92** | **226** | **1** |

Other status details: `TOKEN_OUTPUT_ERROR`: 1.

#### GraphRAG Local

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 27 | 38 | 17 | 0 |
| Medium | 361 | 26 | 305 | 27 | 3 |
| Hard | 306 | 6 | 293 | 7 | 0 |
| Advanced | 124 | 1 | 116 | 5 | 2 |
| Expert | 127 | 2 | 123 | 2 | 0 |
| **Overall** | **1000** | **62** | **875** | **58** | **5** |

Other status details: `CRASH`: 4, `TOKEN_OUTPUT_ERROR`: 1.

#### Parallel SPARQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 51 | 23 | 8 | 0 |
| Medium | 361 | 190 | 105 | 65 | 1 |
| Hard | 306 | 107 | 113 | 86 | 0 |
| Advanced | 124 | 34 | 59 | 31 | 0 |
| Expert | 127 | 19 | 86 | 22 | 0 |
| **Overall** | **1000** | **401** | **386** | **212** | **1** |

Other status details: `OTHER`: 1.

#### Parallel SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 59 | 14 | 9 | 0 |
| Medium | 361 | 238 | 74 | 48 | 1 |
| Hard | 306 | 150 | 83 | 73 | 0 |
| Advanced | 124 | 74 | 37 | 13 | 0 |
| Expert | 127 | 79 | 25 | 23 | 0 |
| **Overall** | **1000** | **600** | **233** | **166** | **1** |

Other status details: `OTHER`: 1.

#### DAIL-SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 67 | 3 | 12 | 0 |
| Medium | 361 | 294 | 17 | 50 | 0 |
| Hard | 306 | 187 | 18 | 101 | 0 |
| Advanced | 124 | 98 | 15 | 10 | 1 |
| Expert | 127 | 90 | 8 | 29 | 0 |
| **Overall** | **1000** | **736** | **61** | **202** | **1** |

Other status details: `OTHER`: 1.

## Kimi K2 Thinking 1T

Model ID: `moonshotai.kimi-k2-thinking`

### Model total across six pipelines

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 492 | 313 | 106 | 73 | 0 |
| Medium | 2166 | 1176 | 703 | 283 | 4 |
| Hard | 1836 | 683 | 704 | 445 | 4 |
| Advanced | 744 | 305 | 328 | 104 | 7 |
| Expert | 762 | 163 | 486 | 77 | 36 |
| **Overall** | **6000** | **2640** | **2327** | **982** | **51** |

### Pipeline detail

#### Base SPARQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 55 | 14 | 13 | 0 |
| Medium | 361 | 198 | 78 | 85 | 0 |
| Hard | 306 | 111 | 61 | 134 | 0 |
| Advanced | 124 | 47 | 31 | 43 | 3 |
| Expert | 127 | 14 | 68 | 27 | 18 |
| **Overall** | **1000** | **425** | **252** | **302** | **21** |

Other status details: `OTHER`: 21.

#### Base SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 53 | 10 | 19 | 0 |
| Medium | 361 | 261 | 53 | 46 | 1 |
| Hard | 306 | 171 | 50 | 83 | 2 |
| Advanced | 124 | 80 | 30 | 11 | 3 |
| Expert | 127 | 50 | 47 | 21 | 9 |
| **Overall** | **1000** | **615** | **190** | **180** | **15** |

Other status details: `OTHER`: 14, `TOKEN_OUTPUT_ERROR`: 1.

#### GraphRAG Local

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 26 | 42 | 14 | 0 |
| Medium | 361 | 26 | 305 | 28 | 2 |
| Hard | 306 | 6 | 293 | 6 | 1 |
| Advanced | 124 | 1 | 120 | 3 | 0 |
| Expert | 127 | 2 | 124 | 1 | 0 |
| **Overall** | **1000** | **61** | **884** | **52** | **3** |

Other status details: `CRASH`: 3.

#### Parallel SPARQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 54 | 21 | 7 | 0 |
| Medium | 361 | 172 | 139 | 50 | 0 |
| Hard | 306 | 77 | 167 | 62 | 0 |
| Advanced | 124 | 17 | 86 | 21 | 0 |
| Expert | 127 | 4 | 120 | 3 | 0 |
| **Overall** | **1000** | **324** | **533** | **143** | **0** |

Other status details: None.

#### Parallel SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 58 | 15 | 9 | 0 |
| Medium | 361 | 227 | 108 | 26 | 0 |
| Hard | 306 | 128 | 108 | 70 | 0 |
| Advanced | 124 | 64 | 48 | 12 | 0 |
| Expert | 127 | 27 | 91 | 9 | 0 |
| **Overall** | **1000** | **504** | **370** | **126** | **0** |

Other status details: None.

#### DAIL-SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 67 | 4 | 11 | 0 |
| Medium | 361 | 292 | 20 | 48 | 1 |
| Hard | 306 | 190 | 25 | 90 | 1 |
| Advanced | 124 | 96 | 13 | 14 | 1 |
| Expert | 127 | 66 | 36 | 16 | 9 |
| **Overall** | **1000** | **711** | **98** | **179** | **12** |

Other status details: `OTHER`: 11, `TOKEN_OUTPUT_ERROR`: 1.

## Gemma 3 27B IT

Model ID: `google.gemma-3-27b-it`

### Model total across six pipelines

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 492 | 281 | 139 | 53 | 19 |
| Medium | 2166 | 965 | 786 | 279 | 136 |
| Hard | 1836 | 571 | 795 | 372 | 98 |
| Advanced | 744 | 252 | 341 | 112 | 39 |
| Expert | 762 | 107 | 492 | 92 | 71 |
| **Overall** | **6000** | **2176** | **2553** | **908** | **363** |

### Pipeline detail

#### Base SPARQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 22 | 52 | 8 | 0 |
| Medium | 361 | 107 | 200 | 44 | 10 |
| Hard | 306 | 58 | 154 | 70 | 24 |
| Advanced | 124 | 22 | 71 | 27 | 4 |
| Expert | 127 | 10 | 80 | 2 | 35 |
| **Overall** | **1000** | **219** | **557** | **151** | **73** |

Other status details: `OTHER`: 73.

#### Base SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 64 | 11 | 7 | 0 |
| Medium | 361 | 238 | 66 | 57 | 0 |
| Hard | 306 | 153 | 71 | 81 | 1 |
| Advanced | 124 | 70 | 37 | 17 | 0 |
| Expert | 127 | 20 | 68 | 34 | 5 |
| **Overall** | **1000** | **545** | **253** | **196** | **6** |

Other status details: `OTHER`: 6.

#### GraphRAG Local

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 27 | 25 | 11 | 19 |
| Medium | 361 | 16 | 201 | 20 | 124 |
| Hard | 306 | 4 | 232 | 0 | 70 |
| Advanced | 124 | 1 | 87 | 4 | 32 |
| Expert | 127 | 1 | 104 | 1 | 21 |
| **Overall** | **1000** | **49** | **649** | **36** | **266** |

Other status details: `CRASH`: 266.

#### Parallel SPARQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 45 | 33 | 4 | 0 |
| Medium | 361 | 100 | 219 | 42 | 0 |
| Hard | 306 | 43 | 209 | 54 | 0 |
| Advanced | 124 | 23 | 78 | 23 | 0 |
| Expert | 127 | 7 | 118 | 2 | 0 |
| **Overall** | **1000** | **218** | **657** | **125** | **0** |

Other status details: None.

#### Parallel SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 59 | 11 | 12 | 0 |
| Medium | 361 | 237 | 67 | 57 | 0 |
| Hard | 306 | 155 | 78 | 73 | 0 |
| Advanced | 124 | 62 | 44 | 18 | 0 |
| Expert | 127 | 21 | 81 | 25 | 0 |
| **Overall** | **1000** | **534** | **281** | **185** | **0** |

Other status details: None.

#### DAIL-SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 64 | 7 | 11 | 0 |
| Medium | 361 | 267 | 33 | 59 | 2 |
| Hard | 306 | 158 | 51 | 94 | 3 |
| Advanced | 124 | 74 | 24 | 23 | 3 |
| Expert | 127 | 48 | 41 | 28 | 10 |
| **Overall** | **1000** | **611** | **156** | **215** | **18** |

Other status details: `OTHER`: 18.

## DeepSeek V3.2 685B

Model ID: `deepseek.v3.2`

### Model total across six pipelines

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 492 | 299 | 124 | 68 | 1 |
| Medium | 2166 | 1169 | 722 | 265 | 10 |
| Hard | 1836 | 683 | 731 | 411 | 11 |
| Advanced | 744 | 279 | 358 | 102 | 5 |
| Expert | 762 | 168 | 466 | 109 | 19 |
| **Overall** | **6000** | **2598** | **2401** | **955** | **46** |

### Pipeline detail

#### Base SPARQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 49 | 24 | 9 | 0 |
| Medium | 361 | 201 | 110 | 44 | 6 |
| Hard | 306 | 101 | 108 | 88 | 9 |
| Advanced | 124 | 27 | 68 | 25 | 4 |
| Expert | 127 | 27 | 80 | 7 | 13 |
| **Overall** | **1000** | **405** | **390** | **173** | **32** |

Other status details: `OTHER`: 32.

#### Base SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 61 | 12 | 9 | 0 |
| Medium | 361 | 251 | 48 | 62 | 0 |
| Hard | 306 | 166 | 41 | 99 | 0 |
| Advanced | 124 | 74 | 29 | 21 | 0 |
| Expert | 127 | 29 | 49 | 47 | 2 |
| **Overall** | **1000** | **581** | **179** | **238** | **2** |

Other status details: `OTHER`: 2.

#### GraphRAG Local

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 33 | 38 | 11 | 0 |
| Medium | 361 | 25 | 309 | 26 | 1 |
| Hard | 306 | 6 | 290 | 10 | 0 |
| Advanced | 124 | 1 | 110 | 13 | 0 |
| Expert | 127 | 2 | 122 | 3 | 0 |
| **Overall** | **1000** | **67** | **869** | **63** | **1** |

Other status details: `CRASH`: 1.

#### Parallel SPARQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 38 | 32 | 12 | 0 |
| Medium | 361 | 159 | 169 | 33 | 0 |
| Hard | 306 | 73 | 185 | 48 | 0 |
| Advanced | 124 | 15 | 98 | 11 | 0 |
| Expert | 127 | 18 | 107 | 2 | 0 |
| **Overall** | **1000** | **303** | **591** | **106** | **0** |

Other status details: None.

#### Parallel SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 55 | 15 | 12 | 0 |
| Medium | 361 | 238 | 69 | 54 | 0 |
| Hard | 306 | 147 | 90 | 69 | 0 |
| Advanced | 124 | 61 | 42 | 21 | 0 |
| Expert | 127 | 12 | 89 | 26 | 0 |
| **Overall** | **1000** | **513** | **305** | **182** | **0** |

Other status details: None.

#### DAIL-SQL

| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Easy | 82 | 63 | 3 | 15 | 1 |
| Medium | 361 | 295 | 17 | 46 | 3 |
| Hard | 306 | 190 | 17 | 97 | 2 |
| Advanced | 124 | 101 | 11 | 11 | 1 |
| Expert | 127 | 80 | 19 | 24 | 4 |
| **Overall** | **1000** | **729** | **67** | **193** | **11** |

Other status details: `OTHER`: 11.
