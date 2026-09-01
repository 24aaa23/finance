# Deterministic Grader Comparison: GPT-OSS 120B vs GPT-5.6 Sol

This report compares the same completed train-set pipeline outputs under two deterministic-grader helper models. The deterministic comparison code is the same; the differing helper LLM calls are grading-contract inference and column mapping.

- Dataset scope: combined train CSV, 442 rows per completed run
- Included completed train runs: 14
- Source labels are read from the graded CSV `New Status` column.
- Percentages are computed as `Match / Rows` and `(Match + Partial) / Rows`.
- Question category is derived from the `question_id` prefix.
- Model names omit owner suffixes such as `aman`, `abhinav`, and `aditya`.

## Question Category Mapping

| Question ID Prefix | Question Category |
| --- | --- |
| WM | Investor status checks |
| BSQ | Batch status queries |
| EC | Enrichment and context queries |
| ARC | At-risk and critical detection |
| SQA | Scoring and quantitative analysis |
| RC | Reference intelligence and rules |
| TT | Temporal and transaction queries |
| MC | Multi-step comparative queries |

## Overall Results: GPT-OSS 120B Grader

| Model | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deepseek.v3.2/all/train | 442 | 154 | 93 | 123 | 2 | 43 | 6 | 21 | 34.84% | 62.67% |
| google.gemini-3.6-flash/all/train | 442 | 186 | 76 | 159 | 0 | 0 | 0 | 21 | 42.08% | 78.05% |
| google.gemma-3-27b-it/all/train | 442 | 32 | 172 | 119 | 89 | 7 | 3 | 20 | 7.24% | 34.16% |
| mistral.mistral-large-3-675b-instruct/all/train | 442 | 98 | 102 | 118 | 4 | 95 | 6 | 19 | 22.17% | 48.87% |
| nvidia.nemotron-super-3-120b/all/train | 442 | 103 | 149 | 136 | 15 | 10 | 9 | 20 | 23.30% | 54.07% |
| openai.gpt-oss-120b/all/train | 442 | 190 | 95 | 136 | 0 | 0 | 0 | 21 | 42.99% | 73.76% |
| qwen.qwen3-coder-480b-a35b-instruct/all/train | 442 | 69 | 90 | 110 | 1 | 154 | 5 | 13 | 15.61% | 40.50% |
| qwen.qwen3-vl-235b-a22b-instruct/all/train | 442 | 77 | 69 | 85 | 2 | 198 | 0 | 11 | 17.42% | 36.65% |
| deepseek.v3.2/hybrid/train | 442 | 171 | 87 | 161 | 2 | 0 | 1 | 20 | 38.69% | 75.11% |
| google.gemma-3-27b-it/hybrid/train | 442 | 169 | 95 | 156 | 1 | 0 | 0 | 21 | 38.24% | 73.53% |
| mistral.mistral-large-3-675b-instruct/hybrid/train | 442 | 179 | 76 | 165 | 0 | 0 | 1 | 21 | 40.50% | 77.83% |
| nvidia.nemotron-super-3-120b/hybrid/train | 442 | 129 | 127 | 162 | 0 | 0 | 3 | 21 | 29.19% | 65.84% |
| qwen.qwen3-coder-480b-a35b-instruct/hybrid/train | 442 | 172 | 93 | 154 | 0 | 0 | 2 | 21 | 38.91% | 73.76% |
| qwen.qwen3-vl-235b-a22b-instruct/hybrid/train | 442 | 175 | 79 | 166 | 0 | 0 | 1 | 21 | 39.59% | 77.15% |

## Overall Results: GPT-5.6 Sol Grader

| Model | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deepseek.v3.2/all/train | 442 | 107 | 204 | 59 | 2 | 43 | 6 | 21 | 24.21% | 37.56% |
| google.gemini-3.6-flash/all/train | 442 | 130 | 206 | 85 | 0 | 0 | 0 | 21 | 29.41% | 48.64% |
| google.gemma-3-27b-it/all/train | 442 | 25 | 259 | 39 | 89 | 7 | 3 | 20 | 5.66% | 14.48% |
| mistral.mistral-large-3-675b-instruct/all/train | 442 | 59 | 199 | 60 | 4 | 95 | 6 | 19 | 13.35% | 26.92% |
| nvidia.nemotron-super-3-120b/all/train | 442 | 63 | 267 | 58 | 15 | 10 | 9 | 20 | 14.25% | 27.38% |
| openai.gpt-oss-120b/all/train | 442 | 134 | 201 | 86 | 0 | 0 | 0 | 21 | 30.32% | 49.77% |
| qwen.qwen3-coder-480b-a35b-instruct/all/train | 442 | 40 | 157 | 72 | 1 | 154 | 5 | 13 | 9.05% | 25.34% |
| qwen.qwen3-vl-235b-a22b-instruct/all/train | 442 | 49 | 134 | 48 | 2 | 198 | 0 | 11 | 11.09% | 21.95% |
| deepseek.v3.2/hybrid/train | 442 | 111 | 210 | 98 | 2 | 0 | 1 | 20 | 25.11% | 47.29% |
| google.gemma-3-27b-it/hybrid/train | 442 | 125 | 207 | 88 | 1 | 0 | 0 | 21 | 28.28% | 48.19% |
| mistral.mistral-large-3-675b-instruct/hybrid/train | 442 | 124 | 201 | 95 | 0 | 0 | 1 | 21 | 28.05% | 49.55% |
| nvidia.nemotron-super-3-120b/hybrid/train | 442 | 97 | 235 | 86 | 0 | 0 | 3 | 21 | 21.95% | 41.40% |
| qwen.qwen3-coder-480b-a35b-instruct/hybrid/train | 442 | 126 | 198 | 95 | 0 | 0 | 2 | 21 | 28.51% | 50.00% |
| qwen.qwen3-vl-235b-a22b-instruct/hybrid/train | 442 | 127 | 195 | 98 | 0 | 0 | 1 | 21 | 28.73% | 50.90% |

## deepseek.v3.2/all/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 27 | 15 | 16 | 1 | 2 | 1 | 4 | 40.91% | 65.15% |
| Batch status queries | 38 | 13 | 9 | 13 | 0 | 1 | 0 | 2 | 34.21% | 68.42% |
| Enrichment and context queries | 59 | 26 | 11 | 20 | 0 | 1 | 1 | 0 | 44.07% | 77.97% |
| At-risk and critical detection | 58 | 36 | 16 | 3 | 0 | 0 | 1 | 2 | 62.07% | 67.24% |
| Scoring and quantitative analysis | 53 | 9 | 14 | 22 | 1 | 4 | 1 | 2 | 16.98% | 58.49% |
| Reference intelligence and rules | 55 | 31 | 10 | 2 | 0 | 2 | 0 | 10 | 56.36% | 60.00% |
| Temporal and transaction queries | 37 | 11 | 11 | 13 | 0 | 1 | 0 | 1 | 29.73% | 64.86% |
| Multi-step comparative queries | 76 | 1 | 7 | 34 | 0 | 32 | 2 | 0 | 1.32% | 46.05% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 9 | 3 | 2 | 0 | 1 | 0 | 0 | 60.00% | 73.33% |
| Filtered List | 42 | 17 | 7 | 4 | 0 | 1 | 0 | 13 | 40.48% | 50.00% |
| Categorical Aggregation | 63 | 23 | 8 | 30 | 0 | 1 | 1 | 0 | 36.51% | 84.13% |
| Comparative | 58 | 3 | 7 | 34 | 0 | 14 | 0 | 0 | 5.17% | 63.79% |
| Ranking | 33 | 9 | 16 | 8 | 0 | 0 | 0 | 0 | 27.27% | 51.52% |
| Temporal | 16 | 5 | 1 | 3 | 1 | 3 | 1 | 2 | 31.25% | 50.00% |
| Multi-Relational | 79 | 41 | 23 | 7 | 1 | 1 | 1 | 5 | 51.90% | 60.76% |
| Rule-Based Detection | 41 | 25 | 11 | 4 | 0 | 0 | 1 | 0 | 60.98% | 70.73% |
| Composite Reasoning | 24 | 10 | 10 | 3 | 0 | 0 | 0 | 1 | 41.67% | 54.17% |
| Reference Compliance | 10 | 7 | 3 | 0 | 0 | 0 | 0 | 0 | 70.00% | 70.00% |
| Exception Detection | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 100.00% | 100.00% |
| Multi-step Comparative | 56 | 0 | 4 | 28 | 0 | 22 | 2 | 0 | 0.00% | 50.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 26 | 8 | 16 | 0 | 1 | 0 | 12 | 41.27% | 66.67% |
| Medium | 118 | 47 | 19 | 32 | 0 | 15 | 1 | 4 | 39.83% | 66.95% |
| Hard | 145 | 46 | 32 | 39 | 1 | 18 | 4 | 5 | 31.72% | 58.62% |
| Advanced | 102 | 32 | 32 | 32 | 1 | 4 | 1 | 0 | 31.37% | 62.75% |
| Expert | 14 | 3 | 2 | 4 | 0 | 5 | 0 | 0 | 21.43% | 50.00% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 16 | 34 | 8 | 1 | 2 | 1 | 4 | 24.24% | 36.36% |
| Batch status queries | 38 | 6 | 20 | 9 | 0 | 1 | 0 | 2 | 15.79% | 39.47% |
| Enrichment and context queries | 59 | 20 | 26 | 11 | 0 | 1 | 1 | 0 | 33.90% | 52.54% |
| At-risk and critical detection | 58 | 28 | 22 | 5 | 0 | 0 | 1 | 2 | 48.28% | 56.90% |
| Scoring and quantitative analysis | 53 | 4 | 28 | 13 | 1 | 4 | 1 | 2 | 7.55% | 32.08% |
| Reference intelligence and rules | 55 | 23 | 18 | 2 | 0 | 2 | 0 | 10 | 41.82% | 45.45% |
| Temporal and transaction queries | 37 | 9 | 20 | 6 | 0 | 1 | 0 | 1 | 24.32% | 40.54% |
| Multi-step comparative queries | 76 | 1 | 36 | 5 | 0 | 32 | 2 | 0 | 1.32% | 7.89% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 6 | 6 | 2 | 0 | 1 | 0 | 0 | 40.00% | 53.33% |
| Filtered List | 42 | 13 | 14 | 1 | 0 | 1 | 0 | 13 | 30.95% | 33.33% |
| Categorical Aggregation | 63 | 7 | 37 | 17 | 0 | 1 | 1 | 0 | 11.11% | 38.10% |
| Comparative | 58 | 0 | 16 | 28 | 0 | 14 | 0 | 0 | 0.00% | 48.28% |
| Ranking | 33 | 3 | 25 | 5 | 0 | 0 | 0 | 0 | 9.09% | 24.24% |
| Temporal | 16 | 3 | 4 | 2 | 1 | 3 | 1 | 2 | 18.75% | 31.25% |
| Multi-Relational | 79 | 35 | 34 | 2 | 1 | 1 | 1 | 5 | 44.30% | 46.84% |
| Rule-Based Detection | 41 | 19 | 19 | 2 | 0 | 0 | 1 | 0 | 46.34% | 51.22% |
| Composite Reasoning | 24 | 10 | 13 | 0 | 0 | 0 | 0 | 1 | 41.67% | 41.67% |
| Reference Compliance | 10 | 7 | 3 | 0 | 0 | 0 | 0 | 0 | 70.00% | 70.00% |
| Exception Detection | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 32 | 0 | 0 | 22 | 2 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 16 | 22 | 12 | 0 | 1 | 0 | 12 | 25.40% | 44.44% |
| Medium | 118 | 26 | 48 | 24 | 0 | 15 | 1 | 4 | 22.03% | 42.37% |
| Hard | 145 | 34 | 71 | 12 | 1 | 18 | 4 | 5 | 23.45% | 31.72% |
| Advanced | 102 | 28 | 58 | 10 | 1 | 4 | 1 | 0 | 27.45% | 37.25% |
| Expert | 14 | 3 | 5 | 1 | 0 | 5 | 0 | 0 | 21.43% | 28.57% |

## google.gemini-3.6-flash/all/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 34 | 11 | 17 | 0 | 0 | 0 | 4 | 51.52% | 77.27% |
| Batch status queries | 38 | 19 | 7 | 10 | 0 | 0 | 0 | 2 | 50.00% | 76.32% |
| Enrichment and context queries | 59 | 29 | 9 | 21 | 0 | 0 | 0 | 0 | 49.15% | 84.75% |
| At-risk and critical detection | 58 | 34 | 16 | 6 | 0 | 0 | 0 | 2 | 58.62% | 68.97% |
| Scoring and quantitative analysis | 53 | 16 | 11 | 24 | 0 | 0 | 0 | 2 | 30.19% | 75.47% |
| Reference intelligence and rules | 55 | 30 | 10 | 5 | 0 | 0 | 0 | 10 | 54.55% | 63.64% |
| Temporal and transaction queries | 37 | 21 | 3 | 12 | 0 | 0 | 0 | 1 | 56.76% | 89.19% |
| Multi-step comparative queries | 76 | 3 | 9 | 64 | 0 | 0 | 0 | 0 | 3.95% | 88.16% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 11 | 4 | 0 | 0 | 0 | 0 | 0 | 73.33% | 73.33% |
| Filtered List | 42 | 23 | 4 | 2 | 0 | 0 | 0 | 13 | 54.76% | 59.52% |
| Categorical Aggregation | 63 | 33 | 6 | 24 | 0 | 0 | 0 | 0 | 52.38% | 90.48% |
| Comparative | 58 | 5 | 6 | 47 | 0 | 0 | 0 | 0 | 8.62% | 89.66% |
| Ranking | 33 | 8 | 13 | 12 | 0 | 0 | 0 | 0 | 24.24% | 60.61% |
| Temporal | 16 | 8 | 1 | 5 | 0 | 0 | 0 | 2 | 50.00% | 81.25% |
| Multi-Relational | 79 | 51 | 13 | 10 | 0 | 0 | 0 | 5 | 64.56% | 77.22% |
| Rule-Based Detection | 41 | 26 | 10 | 5 | 0 | 0 | 0 | 0 | 63.41% | 75.61% |
| Composite Reasoning | 24 | 8 | 9 | 6 | 0 | 0 | 0 | 1 | 33.33% | 58.33% |
| Reference Compliance | 10 | 8 | 2 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Exception Detection | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 100.00% | 100.00% |
| Multi-step Comparative | 56 | 0 | 8 | 48 | 0 | 0 | 0 | 0 | 0.00% | 85.71% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 31 | 10 | 10 | 0 | 0 | 0 | 12 | 49.21% | 65.08% |
| Medium | 118 | 62 | 11 | 41 | 0 | 0 | 0 | 4 | 52.54% | 87.29% |
| Hard | 145 | 50 | 29 | 61 | 0 | 0 | 0 | 5 | 34.48% | 76.55% |
| Advanced | 102 | 40 | 25 | 37 | 0 | 0 | 0 | 0 | 39.22% | 75.49% |
| Expert | 14 | 3 | 1 | 10 | 0 | 0 | 0 | 0 | 21.43% | 92.86% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 20 | 30 | 12 | 0 | 0 | 0 | 4 | 30.30% | 48.48% |
| Batch status queries | 38 | 10 | 19 | 7 | 0 | 0 | 0 | 2 | 26.32% | 44.74% |
| Enrichment and context queries | 59 | 21 | 27 | 11 | 0 | 0 | 0 | 0 | 35.59% | 54.24% |
| At-risk and critical detection | 58 | 28 | 18 | 10 | 0 | 0 | 0 | 2 | 48.28% | 65.52% |
| Scoring and quantitative analysis | 53 | 12 | 23 | 16 | 0 | 0 | 0 | 2 | 22.64% | 52.83% |
| Reference intelligence and rules | 55 | 21 | 20 | 4 | 0 | 0 | 0 | 10 | 38.18% | 45.45% |
| Temporal and transaction queries | 37 | 17 | 10 | 9 | 0 | 0 | 0 | 1 | 45.95% | 70.27% |
| Multi-step comparative queries | 76 | 1 | 59 | 16 | 0 | 0 | 0 | 0 | 1.32% | 22.37% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 9 | 6 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Filtered List | 42 | 16 | 13 | 0 | 0 | 0 | 0 | 13 | 38.10% | 38.10% |
| Categorical Aggregation | 63 | 16 | 25 | 22 | 0 | 0 | 0 | 0 | 25.40% | 60.32% |
| Comparative | 58 | 2 | 15 | 41 | 0 | 0 | 0 | 0 | 3.45% | 74.14% |
| Ranking | 33 | 4 | 22 | 7 | 0 | 0 | 0 | 0 | 12.12% | 33.33% |
| Temporal | 16 | 5 | 4 | 5 | 0 | 0 | 0 | 2 | 31.25% | 62.50% |
| Multi-Relational | 79 | 43 | 24 | 7 | 0 | 0 | 0 | 5 | 54.43% | 63.29% |
| Rule-Based Detection | 41 | 17 | 22 | 2 | 0 | 0 | 0 | 0 | 41.46% | 46.34% |
| Composite Reasoning | 24 | 8 | 14 | 1 | 0 | 0 | 0 | 1 | 33.33% | 37.50% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 56 | 0 | 0 | 0 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 21 | 22 | 8 | 0 | 0 | 0 | 12 | 33.33% | 46.03% |
| Medium | 118 | 40 | 36 | 38 | 0 | 0 | 0 | 4 | 33.90% | 66.10% |
| Hard | 145 | 34 | 83 | 23 | 0 | 0 | 0 | 5 | 23.45% | 39.31% |
| Advanced | 102 | 32 | 55 | 15 | 0 | 0 | 0 | 0 | 31.37% | 46.08% |
| Expert | 14 | 3 | 10 | 1 | 0 | 0 | 0 | 0 | 21.43% | 28.57% |

## google.gemma-3-27b-it/all/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 7 | 24 | 15 | 14 | 2 | 0 | 4 | 10.61% | 33.33% |
| Batch status queries | 38 | 2 | 15 | 9 | 9 | 1 | 1 | 1 | 5.26% | 28.95% |
| Enrichment and context queries | 59 | 2 | 39 | 10 | 8 | 0 | 0 | 0 | 3.39% | 20.34% |
| At-risk and critical detection | 58 | 3 | 35 | 12 | 6 | 0 | 0 | 2 | 5.17% | 25.86% |
| Scoring and quantitative analysis | 53 | 2 | 16 | 24 | 9 | 0 | 0 | 2 | 3.77% | 49.06% |
| Reference intelligence and rules | 55 | 12 | 12 | 15 | 3 | 3 | 0 | 10 | 21.82% | 49.09% |
| Temporal and transaction queries | 37 | 3 | 19 | 5 | 9 | 0 | 0 | 1 | 8.11% | 21.62% |
| Multi-step comparative queries | 76 | 1 | 12 | 29 | 31 | 1 | 2 | 0 | 1.32% | 39.47% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 9 | 6 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Filtered List | 42 | 0 | 25 | 4 | 0 | 0 | 0 | 13 | 0.00% | 9.52% |
| Categorical Aggregation | 63 | 5 | 6 | 21 | 27 | 4 | 0 | 0 | 7.94% | 41.27% |
| Comparative | 58 | 0 | 9 | 38 | 8 | 2 | 1 | 0 | 0.00% | 65.52% |
| Ranking | 33 | 2 | 19 | 4 | 7 | 0 | 1 | 0 | 6.06% | 18.18% |
| Temporal | 16 | 0 | 3 | 0 | 12 | 0 | 0 | 1 | 0.00% | 0.00% |
| Multi-Relational | 79 | 5 | 56 | 12 | 1 | 0 | 0 | 5 | 6.33% | 21.52% |
| Rule-Based Detection | 41 | 3 | 23 | 13 | 2 | 0 | 0 | 0 | 7.32% | 39.02% |
| Composite Reasoning | 24 | 1 | 13 | 6 | 3 | 0 | 0 | 1 | 4.17% | 29.17% |
| Reference Compliance | 10 | 4 | 4 | 2 | 0 | 0 | 0 | 0 | 40.00% | 60.00% |
| Exception Detection | 5 | 3 | 1 | 1 | 0 | 0 | 0 | 0 | 60.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 7 | 18 | 29 | 1 | 1 | 0 | 0.00% | 32.14% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 10 | 15 | 15 | 9 | 2 | 0 | 12 | 15.87% | 39.68% |
| Medium | 118 | 16 | 36 | 37 | 21 | 2 | 2 | 4 | 13.56% | 44.92% |
| Hard | 145 | 4 | 62 | 42 | 29 | 3 | 1 | 4 | 2.76% | 31.72% |
| Advanced | 102 | 1 | 55 | 24 | 22 | 0 | 0 | 0 | 0.98% | 24.51% |
| Expert | 14 | 1 | 4 | 1 | 8 | 0 | 0 | 0 | 7.14% | 14.29% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 6 | 37 | 3 | 14 | 2 | 0 | 4 | 9.09% | 13.64% |
| Batch status queries | 38 | 2 | 22 | 2 | 9 | 1 | 1 | 1 | 5.26% | 10.53% |
| Enrichment and context queries | 59 | 1 | 47 | 3 | 8 | 0 | 0 | 0 | 1.69% | 6.78% |
| At-risk and critical detection | 58 | 0 | 44 | 6 | 6 | 0 | 0 | 2 | 0.00% | 10.34% |
| Scoring and quantitative analysis | 53 | 1 | 33 | 8 | 9 | 0 | 0 | 2 | 1.89% | 16.98% |
| Reference intelligence and rules | 55 | 11 | 22 | 6 | 3 | 3 | 0 | 10 | 20.00% | 30.91% |
| Temporal and transaction queries | 37 | 3 | 21 | 3 | 9 | 0 | 0 | 1 | 8.11% | 16.22% |
| Multi-step comparative queries | 76 | 1 | 33 | 8 | 31 | 1 | 2 | 0 | 1.32% | 11.84% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 7 | 8 | 0 | 0 | 0 | 0 | 0 | 46.67% | 46.67% |
| Filtered List | 42 | 0 | 29 | 0 | 0 | 0 | 0 | 13 | 0.00% | 0.00% |
| Categorical Aggregation | 63 | 2 | 17 | 13 | 27 | 4 | 0 | 0 | 3.17% | 23.81% |
| Comparative | 58 | 0 | 26 | 21 | 8 | 2 | 1 | 0 | 0.00% | 36.21% |
| Ranking | 33 | 0 | 24 | 1 | 7 | 0 | 1 | 0 | 0.00% | 3.03% |
| Temporal | 16 | 0 | 3 | 0 | 12 | 0 | 0 | 1 | 0.00% | 0.00% |
| Multi-Relational | 79 | 5 | 65 | 3 | 1 | 0 | 0 | 5 | 6.33% | 10.13% |
| Rule-Based Detection | 41 | 3 | 35 | 1 | 2 | 0 | 0 | 0 | 7.32% | 9.76% |
| Composite Reasoning | 24 | 1 | 19 | 0 | 3 | 0 | 0 | 1 | 4.17% | 4.17% |
| Reference Compliance | 10 | 4 | 6 | 0 | 0 | 0 | 0 | 0 | 40.00% | 40.00% |
| Exception Detection | 5 | 3 | 2 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Multi-step Comparative | 56 | 0 | 25 | 0 | 29 | 1 | 1 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 8 | 24 | 8 | 9 | 2 | 0 | 12 | 12.70% | 25.40% |
| Medium | 118 | 12 | 58 | 19 | 21 | 2 | 2 | 4 | 10.17% | 26.27% |
| Hard | 145 | 3 | 95 | 10 | 29 | 3 | 1 | 4 | 2.07% | 8.97% |
| Advanced | 102 | 1 | 77 | 2 | 22 | 0 | 0 | 0 | 0.98% | 2.94% |
| Expert | 14 | 1 | 5 | 0 | 8 | 0 | 0 | 0 | 7.14% | 7.14% |

## mistral.mistral-large-3-675b-instruct/all/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 12 | 20 | 22 | 0 | 8 | 1 | 3 | 18.18% | 51.52% |
| Batch status queries | 38 | 4 | 11 | 11 | 2 | 9 | 0 | 1 | 10.53% | 39.47% |
| Enrichment and context queries | 59 | 16 | 18 | 18 | 0 | 4 | 3 | 0 | 27.12% | 57.63% |
| At-risk and critical detection | 58 | 16 | 24 | 8 | 0 | 8 | 0 | 2 | 27.59% | 41.38% |
| Scoring and quantitative analysis | 53 | 16 | 4 | 23 | 0 | 6 | 2 | 2 | 30.19% | 73.58% |
| Reference intelligence and rules | 55 | 23 | 13 | 7 | 0 | 2 | 0 | 10 | 41.82% | 54.55% |
| Temporal and transaction queries | 37 | 10 | 8 | 13 | 0 | 5 | 0 | 1 | 27.03% | 62.16% |
| Multi-step comparative queries | 76 | 1 | 4 | 16 | 2 | 53 | 0 | 0 | 1.32% | 22.37% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 9 | 6 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Filtered List | 42 | 12 | 15 | 0 | 0 | 3 | 0 | 12 | 28.57% | 28.57% |
| Categorical Aggregation | 63 | 12 | 7 | 39 | 1 | 1 | 3 | 0 | 19.05% | 80.95% |
| Comparative | 58 | 1 | 9 | 29 | 1 | 18 | 0 | 0 | 1.72% | 51.72% |
| Ranking | 33 | 12 | 12 | 8 | 0 | 1 | 0 | 0 | 36.36% | 60.61% |
| Temporal | 16 | 3 | 1 | 5 | 1 | 4 | 0 | 2 | 18.75% | 50.00% |
| Multi-Relational | 79 | 24 | 24 | 10 | 0 | 16 | 1 | 4 | 30.38% | 43.04% |
| Rule-Based Detection | 41 | 12 | 15 | 5 | 0 | 9 | 0 | 0 | 29.27% | 41.46% |
| Composite Reasoning | 24 | 6 | 4 | 7 | 0 | 4 | 2 | 1 | 25.00% | 54.17% |
| Reference Compliance | 10 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 50.00% | 50.00% |
| Exception Detection | 5 | 2 | 2 | 1 | 0 | 0 | 0 | 0 | 40.00% | 60.00% |
| Multi-step Comparative | 56 | 0 | 2 | 14 | 1 | 39 | 0 | 0 | 0.00% | 25.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 19 | 15 | 16 | 1 | 1 | 0 | 11 | 30.16% | 55.56% |
| Medium | 118 | 28 | 22 | 37 | 2 | 26 | 0 | 3 | 23.73% | 55.08% |
| Hard | 145 | 27 | 35 | 37 | 1 | 38 | 2 | 5 | 18.62% | 44.14% |
| Advanced | 102 | 21 | 28 | 24 | 0 | 25 | 4 | 0 | 20.59% | 44.12% |
| Expert | 14 | 3 | 2 | 4 | 0 | 5 | 0 | 0 | 21.43% | 50.00% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 7 | 37 | 10 | 0 | 8 | 1 | 3 | 10.61% | 25.76% |
| Batch status queries | 38 | 2 | 18 | 6 | 2 | 9 | 0 | 1 | 5.26% | 21.05% |
| Enrichment and context queries | 59 | 10 | 34 | 8 | 0 | 4 | 3 | 0 | 16.95% | 30.51% |
| At-risk and critical detection | 58 | 13 | 28 | 7 | 0 | 8 | 0 | 2 | 22.41% | 34.48% |
| Scoring and quantitative analysis | 53 | 9 | 19 | 15 | 0 | 6 | 2 | 2 | 16.98% | 45.28% |
| Reference intelligence and rules | 55 | 11 | 29 | 3 | 0 | 2 | 0 | 10 | 20.00% | 25.45% |
| Temporal and transaction queries | 37 | 6 | 16 | 9 | 0 | 5 | 0 | 1 | 16.22% | 40.54% |
| Multi-step comparative queries | 76 | 1 | 18 | 2 | 2 | 53 | 0 | 0 | 1.32% | 3.95% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 7 | 8 | 0 | 0 | 0 | 0 | 0 | 46.67% | 46.67% |
| Filtered List | 42 | 8 | 19 | 0 | 0 | 3 | 0 | 12 | 19.05% | 19.05% |
| Categorical Aggregation | 63 | 3 | 38 | 17 | 1 | 1 | 3 | 0 | 4.76% | 31.75% |
| Comparative | 58 | 0 | 14 | 25 | 1 | 18 | 0 | 0 | 0.00% | 43.10% |
| Ranking | 33 | 4 | 25 | 3 | 0 | 1 | 0 | 0 | 12.12% | 21.21% |
| Temporal | 16 | 2 | 3 | 4 | 1 | 4 | 0 | 2 | 12.50% | 37.50% |
| Multi-Relational | 79 | 17 | 33 | 8 | 0 | 16 | 1 | 4 | 21.52% | 31.65% |
| Rule-Based Detection | 41 | 6 | 23 | 3 | 0 | 9 | 0 | 0 | 14.63% | 21.95% |
| Composite Reasoning | 24 | 5 | 12 | 0 | 0 | 4 | 2 | 1 | 20.83% | 20.83% |
| Reference Compliance | 10 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 50.00% | 50.00% |
| Exception Detection | 5 | 2 | 3 | 0 | 0 | 0 | 0 | 0 | 40.00% | 40.00% |
| Multi-step Comparative | 56 | 0 | 16 | 0 | 1 | 39 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 12 | 30 | 8 | 1 | 1 | 0 | 11 | 19.05% | 31.75% |
| Medium | 118 | 17 | 48 | 22 | 2 | 26 | 0 | 3 | 14.41% | 33.05% |
| Hard | 145 | 14 | 68 | 17 | 1 | 38 | 2 | 5 | 9.66% | 21.38% |
| Advanced | 102 | 14 | 46 | 13 | 0 | 25 | 4 | 0 | 13.73% | 26.47% |
| Expert | 14 | 2 | 7 | 0 | 0 | 5 | 0 | 0 | 14.29% | 14.29% |

## nvidia.nemotron-super-3-120b/all/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 19 | 22 | 18 | 2 | 0 | 1 | 4 | 28.79% | 56.06% |
| Batch status queries | 38 | 5 | 17 | 13 | 0 | 2 | 0 | 1 | 13.16% | 47.37% |
| Enrichment and context queries | 59 | 9 | 27 | 19 | 1 | 1 | 2 | 0 | 15.25% | 47.46% |
| At-risk and critical detection | 58 | 30 | 19 | 7 | 0 | 0 | 0 | 2 | 51.72% | 63.79% |
| Scoring and quantitative analysis | 53 | 10 | 16 | 20 | 2 | 1 | 2 | 2 | 18.87% | 56.60% |
| Reference intelligence and rules | 55 | 20 | 17 | 7 | 0 | 1 | 0 | 10 | 36.36% | 49.09% |
| Temporal and transaction queries | 37 | 9 | 17 | 8 | 1 | 0 | 1 | 1 | 24.32% | 45.95% |
| Multi-step comparative queries | 76 | 1 | 14 | 44 | 9 | 5 | 3 | 0 | 1.32% | 59.21% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 11 | 3 | 0 | 0 | 0 | 1 | 0 | 73.33% | 73.33% |
| Filtered List | 42 | 10 | 15 | 3 | 0 | 1 | 0 | 13 | 23.81% | 30.95% |
| Categorical Aggregation | 63 | 13 | 11 | 38 | 0 | 0 | 1 | 0 | 20.63% | 80.95% |
| Comparative | 58 | 1 | 11 | 38 | 1 | 5 | 2 | 0 | 1.72% | 67.24% |
| Ranking | 33 | 12 | 13 | 7 | 0 | 0 | 1 | 0 | 36.36% | 57.58% |
| Temporal | 16 | 2 | 6 | 4 | 1 | 1 | 0 | 2 | 12.50% | 37.50% |
| Multi-Relational | 79 | 20 | 45 | 7 | 2 | 1 | 0 | 4 | 25.32% | 34.18% |
| Rule-Based Detection | 41 | 16 | 19 | 4 | 1 | 0 | 1 | 0 | 39.02% | 48.78% |
| Composite Reasoning | 24 | 6 | 15 | 0 | 2 | 0 | 0 | 1 | 25.00% | 25.00% |
| Reference Compliance | 10 | 8 | 2 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Exception Detection | 5 | 4 | 0 | 1 | 0 | 0 | 0 | 0 | 80.00% | 100.00% |
| Multi-step Comparative | 56 | 0 | 9 | 34 | 8 | 2 | 3 | 0 | 0.00% | 60.71% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 20 | 10 | 19 | 0 | 0 | 2 | 12 | 31.75% | 61.90% |
| Medium | 118 | 38 | 28 | 42 | 1 | 6 | 0 | 3 | 32.20% | 67.80% |
| Hard | 145 | 25 | 59 | 46 | 5 | 4 | 1 | 5 | 17.24% | 48.97% |
| Advanced | 102 | 18 | 48 | 26 | 7 | 0 | 3 | 0 | 17.65% | 43.14% |
| Expert | 14 | 2 | 4 | 3 | 2 | 0 | 3 | 0 | 14.29% | 35.71% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 10 | 41 | 8 | 2 | 0 | 1 | 4 | 15.15% | 27.27% |
| Batch status queries | 38 | 2 | 25 | 8 | 0 | 2 | 0 | 1 | 5.26% | 26.32% |
| Enrichment and context queries | 59 | 4 | 43 | 8 | 1 | 1 | 2 | 0 | 6.78% | 20.34% |
| At-risk and critical detection | 58 | 22 | 27 | 7 | 0 | 0 | 0 | 2 | 37.93% | 50.00% |
| Scoring and quantitative analysis | 53 | 5 | 30 | 11 | 2 | 1 | 2 | 2 | 9.43% | 30.19% |
| Reference intelligence and rules | 55 | 13 | 29 | 2 | 0 | 1 | 0 | 10 | 23.64% | 27.27% |
| Temporal and transaction queries | 37 | 6 | 23 | 5 | 1 | 0 | 1 | 1 | 16.22% | 29.73% |
| Multi-step comparative queries | 76 | 1 | 49 | 9 | 9 | 5 | 3 | 0 | 1.32% | 13.16% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 7 | 7 | 0 | 0 | 0 | 1 | 0 | 46.67% | 46.67% |
| Filtered List | 42 | 5 | 23 | 0 | 0 | 1 | 0 | 13 | 11.90% | 11.90% |
| Categorical Aggregation | 63 | 2 | 41 | 19 | 0 | 0 | 1 | 0 | 3.17% | 33.33% |
| Comparative | 58 | 1 | 21 | 28 | 1 | 5 | 2 | 0 | 1.72% | 50.00% |
| Ranking | 33 | 7 | 21 | 4 | 0 | 0 | 1 | 0 | 21.21% | 33.33% |
| Temporal | 16 | 0 | 10 | 2 | 1 | 1 | 0 | 2 | 0.00% | 12.50% |
| Multi-Relational | 79 | 15 | 54 | 3 | 2 | 1 | 0 | 4 | 18.99% | 22.78% |
| Rule-Based Detection | 41 | 11 | 26 | 2 | 1 | 0 | 1 | 0 | 26.83% | 31.71% |
| Composite Reasoning | 24 | 5 | 16 | 0 | 2 | 0 | 0 | 1 | 20.83% | 20.83% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 43 | 0 | 8 | 2 | 3 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 10 | 29 | 10 | 0 | 0 | 2 | 12 | 15.87% | 31.75% |
| Medium | 118 | 21 | 58 | 29 | 1 | 6 | 0 | 3 | 17.80% | 42.37% |
| Hard | 145 | 16 | 101 | 13 | 5 | 4 | 1 | 5 | 11.03% | 20.00% |
| Advanced | 102 | 14 | 72 | 6 | 7 | 0 | 3 | 0 | 13.73% | 19.61% |
| Expert | 14 | 2 | 7 | 0 | 2 | 0 | 3 | 0 | 14.29% | 14.29% |

## openai.gpt-oss-120b/all/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 37 | 8 | 17 | 0 | 0 | 0 | 4 | 56.06% | 81.82% |
| Batch status queries | 38 | 17 | 8 | 11 | 0 | 0 | 0 | 2 | 44.74% | 73.68% |
| Enrichment and context queries | 59 | 27 | 15 | 17 | 0 | 0 | 0 | 0 | 45.76% | 74.58% |
| At-risk and critical detection | 58 | 42 | 9 | 5 | 0 | 0 | 0 | 2 | 72.41% | 81.03% |
| Scoring and quantitative analysis | 53 | 22 | 8 | 21 | 0 | 0 | 0 | 2 | 41.51% | 81.13% |
| Reference intelligence and rules | 55 | 28 | 12 | 5 | 0 | 0 | 0 | 10 | 50.91% | 60.00% |
| Temporal and transaction queries | 37 | 16 | 7 | 13 | 0 | 0 | 0 | 1 | 43.24% | 78.38% |
| Multi-step comparative queries | 76 | 1 | 28 | 47 | 0 | 0 | 0 | 0 | 1.32% | 63.16% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 12 | 1 | 2 | 0 | 0 | 0 | 0 | 80.00% | 93.33% |
| Filtered List | 42 | 22 | 7 | 0 | 0 | 0 | 0 | 13 | 52.38% | 52.38% |
| Categorical Aggregation | 63 | 24 | 9 | 30 | 0 | 0 | 0 | 0 | 38.10% | 85.71% |
| Comparative | 58 | 7 | 8 | 43 | 0 | 0 | 0 | 0 | 12.07% | 86.21% |
| Ranking | 33 | 15 | 11 | 7 | 0 | 0 | 0 | 0 | 45.45% | 66.67% |
| Temporal | 16 | 7 | 1 | 6 | 0 | 0 | 0 | 2 | 43.75% | 81.25% |
| Multi-Relational | 79 | 50 | 15 | 9 | 0 | 0 | 0 | 5 | 63.29% | 74.68% |
| Rule-Based Detection | 41 | 28 | 11 | 2 | 0 | 0 | 0 | 0 | 68.29% | 73.17% |
| Composite Reasoning | 24 | 13 | 5 | 5 | 0 | 0 | 0 | 1 | 54.17% | 75.00% |
| Reference Compliance | 10 | 7 | 3 | 0 | 0 | 0 | 0 | 0 | 70.00% | 70.00% |
| Exception Detection | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 100.00% | 100.00% |
| Multi-step Comparative | 56 | 0 | 24 | 32 | 0 | 0 | 0 | 0 | 0.00% | 57.14% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 25 | 9 | 17 | 0 | 0 | 0 | 12 | 39.68% | 66.67% |
| Medium | 118 | 60 | 14 | 40 | 0 | 0 | 0 | 4 | 50.85% | 84.75% |
| Hard | 145 | 56 | 39 | 45 | 0 | 0 | 0 | 5 | 38.62% | 69.66% |
| Advanced | 102 | 46 | 29 | 27 | 0 | 0 | 0 | 0 | 45.10% | 71.57% |
| Expert | 14 | 3 | 4 | 7 | 0 | 0 | 0 | 0 | 21.43% | 71.43% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 22 | 25 | 15 | 0 | 0 | 0 | 4 | 33.33% | 56.06% |
| Batch status queries | 38 | 9 | 18 | 9 | 0 | 0 | 0 | 2 | 23.68% | 47.37% |
| Enrichment and context queries | 59 | 21 | 26 | 12 | 0 | 0 | 0 | 0 | 35.59% | 55.93% |
| At-risk and critical detection | 58 | 33 | 14 | 9 | 0 | 0 | 0 | 2 | 56.90% | 72.41% |
| Scoring and quantitative analysis | 53 | 16 | 20 | 15 | 0 | 0 | 0 | 2 | 30.19% | 58.49% |
| Reference intelligence and rules | 55 | 19 | 21 | 5 | 0 | 0 | 0 | 10 | 34.55% | 43.64% |
| Temporal and transaction queries | 37 | 13 | 14 | 9 | 0 | 0 | 0 | 1 | 35.14% | 59.46% |
| Multi-step comparative queries | 76 | 1 | 63 | 12 | 0 | 0 | 0 | 0 | 1.32% | 17.11% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 11 | 4 | 0 | 0 | 0 | 0 | 0 | 73.33% | 73.33% |
| Filtered List | 42 | 15 | 14 | 0 | 0 | 0 | 0 | 13 | 35.71% | 35.71% |
| Categorical Aggregation | 63 | 10 | 30 | 23 | 0 | 0 | 0 | 0 | 15.87% | 52.38% |
| Comparative | 58 | 4 | 15 | 39 | 0 | 0 | 0 | 0 | 6.90% | 74.14% |
| Ranking | 33 | 6 | 21 | 6 | 0 | 0 | 0 | 0 | 18.18% | 36.36% |
| Temporal | 16 | 4 | 3 | 7 | 0 | 0 | 0 | 2 | 25.00% | 68.75% |
| Multi-Relational | 79 | 43 | 23 | 8 | 0 | 0 | 0 | 5 | 54.43% | 64.56% |
| Rule-Based Detection | 41 | 19 | 19 | 3 | 0 | 0 | 0 | 0 | 46.34% | 53.66% |
| Composite Reasoning | 24 | 12 | 11 | 0 | 0 | 0 | 0 | 1 | 50.00% | 50.00% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 56 | 0 | 0 | 0 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 20 | 23 | 8 | 0 | 0 | 0 | 12 | 31.75% | 44.44% |
| Medium | 118 | 36 | 40 | 38 | 0 | 0 | 0 | 4 | 30.51% | 62.71% |
| Hard | 145 | 38 | 78 | 24 | 0 | 0 | 0 | 5 | 26.21% | 42.76% |
| Advanced | 102 | 37 | 49 | 16 | 0 | 0 | 0 | 0 | 36.27% | 51.96% |
| Expert | 14 | 3 | 11 | 0 | 0 | 0 | 0 | 0 | 21.43% | 21.43% |

## qwen.qwen3-coder-480b-a35b-instruct/all/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 15 | 15 | 15 | 1 | 19 | 0 | 1 | 22.73% | 45.45% |
| Batch status queries | 38 | 3 | 9 | 12 | 0 | 13 | 0 | 1 | 7.89% | 39.47% |
| Enrichment and context queries | 59 | 8 | 16 | 18 | 0 | 16 | 1 | 0 | 13.56% | 44.07% |
| At-risk and critical detection | 58 | 8 | 5 | 7 | 0 | 38 | 0 | 0 | 13.79% | 25.86% |
| Scoring and quantitative analysis | 53 | 7 | 14 | 19 | 0 | 10 | 2 | 1 | 13.21% | 49.06% |
| Reference intelligence and rules | 55 | 19 | 17 | 5 | 0 | 4 | 0 | 10 | 34.55% | 43.64% |
| Temporal and transaction queries | 37 | 8 | 5 | 14 | 0 | 8 | 2 | 0 | 21.62% | 59.46% |
| Multi-step comparative queries | 76 | 1 | 9 | 20 | 0 | 46 | 0 | 0 | 1.32% | 27.63% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 8 | 5 | 1 | 0 | 1 | 0 | 0 | 53.33% | 60.00% |
| Filtered List | 42 | 5 | 7 | 1 | 0 | 22 | 0 | 7 | 11.90% | 14.29% |
| Categorical Aggregation | 63 | 18 | 11 | 33 | 0 | 1 | 0 | 0 | 28.57% | 80.95% |
| Comparative | 58 | 1 | 8 | 32 | 1 | 16 | 0 | 0 | 1.72% | 56.90% |
| Ranking | 33 | 5 | 18 | 9 | 0 | 1 | 0 | 0 | 15.15% | 42.42% |
| Temporal | 16 | 3 | 4 | 2 | 0 | 6 | 0 | 1 | 18.75% | 31.25% |
| Multi-Relational | 79 | 7 | 16 | 10 | 0 | 38 | 4 | 4 | 8.86% | 21.52% |
| Rule-Based Detection | 41 | 10 | 8 | 1 | 0 | 22 | 0 | 0 | 24.39% | 26.83% |
| Composite Reasoning | 24 | 4 | 4 | 3 | 0 | 11 | 1 | 1 | 16.67% | 29.17% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 2 | 0 | 1 | 0 | 2 | 0 | 0 | 40.00% | 60.00% |
| Multi-step Comparative | 56 | 0 | 5 | 17 | 0 | 34 | 0 | 0 | 0.00% | 30.36% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 19 | 15 | 14 | 0 | 9 | 0 | 6 | 30.16% | 52.38% |
| Medium | 118 | 22 | 22 | 32 | 0 | 39 | 1 | 2 | 18.64% | 45.76% |
| Hard | 145 | 16 | 34 | 43 | 0 | 47 | 0 | 5 | 11.03% | 40.69% |
| Advanced | 102 | 9 | 17 | 18 | 1 | 53 | 4 | 0 | 8.82% | 26.47% |
| Expert | 14 | 3 | 2 | 3 | 0 | 6 | 0 | 0 | 21.43% | 42.86% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 9 | 26 | 10 | 1 | 19 | 0 | 1 | 13.64% | 28.79% |
| Batch status queries | 38 | 0 | 17 | 7 | 0 | 13 | 0 | 1 | 0.00% | 18.42% |
| Enrichment and context queries | 59 | 7 | 21 | 14 | 0 | 16 | 1 | 0 | 11.86% | 35.59% |
| At-risk and critical detection | 58 | 3 | 8 | 9 | 0 | 38 | 0 | 0 | 5.17% | 20.69% |
| Scoring and quantitative analysis | 53 | 3 | 22 | 15 | 0 | 10 | 2 | 1 | 5.66% | 33.96% |
| Reference intelligence and rules | 55 | 9 | 26 | 6 | 0 | 4 | 0 | 10 | 16.36% | 27.27% |
| Temporal and transaction queries | 37 | 8 | 11 | 8 | 0 | 8 | 2 | 0 | 21.62% | 43.24% |
| Multi-step comparative queries | 76 | 1 | 26 | 3 | 0 | 46 | 0 | 0 | 1.32% | 5.26% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 8 | 6 | 0 | 0 | 1 | 0 | 0 | 53.33% | 53.33% |
| Filtered List | 42 | 3 | 9 | 1 | 0 | 22 | 0 | 7 | 7.14% | 9.52% |
| Categorical Aggregation | 63 | 2 | 34 | 26 | 0 | 1 | 0 | 0 | 3.17% | 44.44% |
| Comparative | 58 | 0 | 12 | 29 | 1 | 16 | 0 | 0 | 0.00% | 50.00% |
| Ranking | 33 | 4 | 24 | 4 | 0 | 1 | 0 | 0 | 12.12% | 24.24% |
| Temporal | 16 | 1 | 7 | 1 | 0 | 6 | 0 | 1 | 6.25% | 12.50% |
| Multi-Relational | 79 | 6 | 18 | 9 | 0 | 38 | 4 | 4 | 7.59% | 18.99% |
| Rule-Based Detection | 41 | 5 | 12 | 2 | 0 | 22 | 0 | 0 | 12.20% | 17.07% |
| Composite Reasoning | 24 | 4 | 7 | 0 | 0 | 11 | 1 | 1 | 16.67% | 16.67% |
| Reference Compliance | 10 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 50.00% | 50.00% |
| Exception Detection | 5 | 2 | 1 | 0 | 0 | 2 | 0 | 0 | 40.00% | 40.00% |
| Multi-step Comparative | 56 | 0 | 22 | 0 | 0 | 34 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 10 | 27 | 11 | 0 | 9 | 0 | 6 | 15.87% | 33.33% |
| Medium | 118 | 12 | 38 | 26 | 0 | 39 | 1 | 2 | 10.17% | 32.20% |
| Hard | 145 | 11 | 60 | 22 | 0 | 47 | 0 | 5 | 7.59% | 22.76% |
| Advanced | 102 | 4 | 27 | 13 | 1 | 53 | 4 | 0 | 3.92% | 16.67% |
| Expert | 14 | 3 | 5 | 0 | 0 | 6 | 0 | 0 | 21.43% | 21.43% |

## qwen.qwen3-vl-235b-a22b-instruct/all/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 13 | 13 | 18 | 1 | 21 | 0 | 0 | 19.70% | 46.97% |
| Batch status queries | 38 | 4 | 7 | 7 | 1 | 18 | 0 | 1 | 10.53% | 28.95% |
| Enrichment and context queries | 59 | 14 | 9 | 16 | 0 | 20 | 0 | 0 | 23.73% | 50.85% |
| At-risk and critical detection | 58 | 11 | 6 | 7 | 0 | 34 | 0 | 0 | 18.97% | 31.03% |
| Scoring and quantitative analysis | 53 | 6 | 14 | 14 | 0 | 17 | 0 | 2 | 11.32% | 37.74% |
| Reference intelligence and rules | 55 | 22 | 8 | 3 | 0 | 15 | 0 | 7 | 40.00% | 45.45% |
| Temporal and transaction queries | 37 | 6 | 9 | 11 | 0 | 10 | 0 | 1 | 16.22% | 45.95% |
| Multi-step comparative queries | 76 | 1 | 3 | 9 | 0 | 63 | 0 | 0 | 1.32% | 13.16% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 8 | 5 | 0 | 0 | 2 | 0 | 0 | 53.33% | 53.33% |
| Filtered List | 42 | 9 | 3 | 2 | 0 | 21 | 0 | 7 | 21.43% | 26.19% |
| Categorical Aggregation | 63 | 10 | 9 | 26 | 0 | 18 | 0 | 0 | 15.87% | 57.14% |
| Comparative | 58 | 1 | 5 | 25 | 1 | 26 | 0 | 0 | 1.72% | 44.83% |
| Ranking | 33 | 2 | 21 | 6 | 0 | 4 | 0 | 0 | 6.06% | 24.24% |
| Temporal | 16 | 2 | 2 | 1 | 0 | 10 | 0 | 1 | 12.50% | 18.75% |
| Multi-Relational | 79 | 18 | 5 | 12 | 1 | 41 | 0 | 2 | 22.78% | 37.97% |
| Rule-Based Detection | 41 | 13 | 8 | 2 | 0 | 18 | 0 | 0 | 31.71% | 36.59% |
| Composite Reasoning | 24 | 3 | 7 | 4 | 0 | 9 | 0 | 1 | 12.50% | 29.17% |
| Reference Compliance | 10 | 7 | 3 | 0 | 0 | 0 | 0 | 0 | 70.00% | 70.00% |
| Exception Detection | 5 | 4 | 0 | 0 | 0 | 1 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 1 | 7 | 0 | 48 | 0 | 0 | 0.00% | 12.50% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 17 | 10 | 11 | 0 | 19 | 0 | 6 | 26.98% | 44.44% |
| Medium | 118 | 27 | 14 | 22 | 2 | 52 | 0 | 1 | 22.88% | 41.53% |
| Hard | 145 | 20 | 21 | 34 | 0 | 66 | 0 | 4 | 13.79% | 37.24% |
| Advanced | 102 | 11 | 21 | 18 | 0 | 52 | 0 | 0 | 10.78% | 28.43% |
| Expert | 14 | 2 | 3 | 0 | 0 | 9 | 0 | 0 | 14.29% | 14.29% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 10 | 26 | 8 | 1 | 21 | 0 | 0 | 15.15% | 27.27% |
| Batch status queries | 38 | 1 | 13 | 4 | 1 | 18 | 0 | 1 | 2.63% | 13.16% |
| Enrichment and context queries | 59 | 12 | 18 | 9 | 0 | 20 | 0 | 0 | 20.34% | 35.59% |
| At-risk and critical detection | 58 | 4 | 12 | 8 | 0 | 34 | 0 | 0 | 6.90% | 20.69% |
| Scoring and quantitative analysis | 53 | 2 | 24 | 8 | 0 | 17 | 0 | 2 | 3.77% | 18.87% |
| Reference intelligence and rules | 55 | 13 | 18 | 2 | 0 | 15 | 0 | 7 | 23.64% | 27.27% |
| Temporal and transaction queries | 37 | 6 | 13 | 7 | 0 | 10 | 0 | 1 | 16.22% | 35.14% |
| Multi-step comparative queries | 76 | 1 | 10 | 2 | 0 | 63 | 0 | 0 | 1.32% | 3.95% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 8 | 5 | 0 | 0 | 2 | 0 | 0 | 53.33% | 53.33% |
| Filtered List | 42 | 5 | 7 | 2 | 0 | 21 | 0 | 7 | 11.90% | 16.67% |
| Categorical Aggregation | 63 | 2 | 28 | 15 | 0 | 18 | 0 | 0 | 3.17% | 26.98% |
| Comparative | 58 | 0 | 12 | 19 | 1 | 26 | 0 | 0 | 0.00% | 32.76% |
| Ranking | 33 | 0 | 26 | 3 | 0 | 4 | 0 | 0 | 0.00% | 9.09% |
| Temporal | 16 | 0 | 5 | 0 | 0 | 10 | 0 | 1 | 0.00% | 0.00% |
| Multi-Relational | 79 | 14 | 14 | 7 | 1 | 41 | 0 | 2 | 17.72% | 26.58% |
| Rule-Based Detection | 41 | 7 | 14 | 2 | 0 | 18 | 0 | 0 | 17.07% | 21.95% |
| Composite Reasoning | 24 | 3 | 11 | 0 | 0 | 9 | 0 | 1 | 12.50% | 12.50% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 4 | 0 | 0 | 0 | 1 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 8 | 0 | 0 | 48 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 13 | 19 | 6 | 0 | 19 | 0 | 6 | 20.63% | 30.16% |
| Medium | 118 | 16 | 31 | 16 | 2 | 52 | 0 | 1 | 13.56% | 27.12% |
| Hard | 145 | 10 | 49 | 16 | 0 | 66 | 0 | 4 | 6.90% | 17.93% |
| Advanced | 102 | 8 | 32 | 10 | 0 | 52 | 0 | 0 | 7.84% | 17.65% |
| Expert | 14 | 2 | 3 | 0 | 0 | 9 | 0 | 0 | 14.29% | 14.29% |

## deepseek.v3.2/hybrid/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 35 | 10 | 17 | 0 | 0 | 0 | 4 | 53.03% | 78.79% |
| Batch status queries | 38 | 14 | 12 | 10 | 1 | 0 | 0 | 1 | 36.84% | 63.16% |
| Enrichment and context queries | 59 | 25 | 15 | 19 | 0 | 0 | 0 | 0 | 42.37% | 74.58% |
| At-risk and critical detection | 58 | 29 | 17 | 10 | 0 | 0 | 0 | 2 | 50.00% | 67.24% |
| Scoring and quantitative analysis | 53 | 22 | 9 | 19 | 0 | 0 | 1 | 2 | 41.51% | 77.36% |
| Reference intelligence and rules | 55 | 32 | 7 | 6 | 0 | 0 | 0 | 10 | 58.18% | 69.09% |
| Temporal and transaction queries | 37 | 13 | 8 | 15 | 0 | 0 | 0 | 1 | 35.14% | 75.68% |
| Multi-step comparative queries | 76 | 1 | 9 | 65 | 1 | 0 | 0 | 0 | 1.32% | 86.84% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 12 | 3 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Filtered List | 42 | 21 | 8 | 0 | 0 | 0 | 0 | 13 | 50.00% | 50.00% |
| Categorical Aggregation | 63 | 23 | 9 | 31 | 0 | 0 | 0 | 0 | 36.51% | 85.71% |
| Comparative | 58 | 8 | 7 | 43 | 0 | 0 | 0 | 0 | 13.79% | 87.93% |
| Ranking | 33 | 12 | 9 | 11 | 0 | 0 | 1 | 0 | 36.36% | 69.70% |
| Temporal | 16 | 6 | 0 | 8 | 1 | 0 | 0 | 1 | 37.50% | 87.50% |
| Multi-Relational | 79 | 41 | 22 | 11 | 0 | 0 | 0 | 5 | 51.90% | 65.82% |
| Rule-Based Detection | 41 | 27 | 11 | 3 | 0 | 0 | 0 | 0 | 65.85% | 73.17% |
| Composite Reasoning | 24 | 9 | 9 | 5 | 0 | 0 | 0 | 1 | 37.50% | 58.33% |
| Reference Compliance | 10 | 7 | 3 | 0 | 0 | 0 | 0 | 0 | 70.00% | 70.00% |
| Exception Detection | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 100.00% | 100.00% |
| Multi-step Comparative | 56 | 0 | 6 | 49 | 1 | 0 | 0 | 0 | 0.00% | 87.50% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 24 | 11 | 16 | 0 | 0 | 0 | 12 | 38.10% | 63.49% |
| Medium | 118 | 58 | 14 | 42 | 0 | 0 | 0 | 4 | 49.15% | 84.75% |
| Hard | 145 | 56 | 28 | 56 | 1 | 0 | 0 | 4 | 38.62% | 77.24% |
| Advanced | 102 | 30 | 31 | 40 | 0 | 0 | 1 | 0 | 29.41% | 68.63% |
| Expert | 14 | 3 | 3 | 7 | 1 | 0 | 0 | 0 | 21.43% | 71.43% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 22 | 26 | 14 | 0 | 0 | 0 | 4 | 33.33% | 54.55% |
| Batch status queries | 38 | 9 | 16 | 11 | 1 | 0 | 0 | 1 | 23.68% | 52.63% |
| Enrichment and context queries | 59 | 16 | 28 | 15 | 0 | 0 | 0 | 0 | 27.12% | 52.54% |
| At-risk and critical detection | 58 | 22 | 24 | 10 | 0 | 0 | 0 | 2 | 37.93% | 55.17% |
| Scoring and quantitative analysis | 53 | 13 | 20 | 17 | 0 | 0 | 1 | 2 | 24.53% | 56.60% |
| Reference intelligence and rules | 55 | 18 | 21 | 6 | 0 | 0 | 0 | 10 | 32.73% | 43.64% |
| Temporal and transaction queries | 37 | 10 | 14 | 12 | 0 | 0 | 0 | 1 | 27.03% | 59.46% |
| Multi-step comparative queries | 76 | 1 | 61 | 13 | 1 | 0 | 0 | 0 | 1.32% | 18.42% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 10 | 5 | 0 | 0 | 0 | 0 | 0 | 66.67% | 66.67% |
| Filtered List | 42 | 12 | 16 | 1 | 0 | 0 | 0 | 13 | 28.57% | 30.95% |
| Categorical Aggregation | 63 | 10 | 27 | 26 | 0 | 0 | 0 | 0 | 15.87% | 57.14% |
| Comparative | 58 | 4 | 14 | 40 | 0 | 0 | 0 | 0 | 6.90% | 75.86% |
| Ranking | 33 | 6 | 18 | 8 | 0 | 0 | 1 | 0 | 18.18% | 42.42% |
| Temporal | 16 | 4 | 2 | 8 | 1 | 0 | 0 | 1 | 25.00% | 75.00% |
| Multi-Relational | 79 | 33 | 32 | 9 | 0 | 0 | 0 | 5 | 41.77% | 53.16% |
| Rule-Based Detection | 41 | 14 | 24 | 3 | 0 | 0 | 0 | 0 | 34.15% | 41.46% |
| Composite Reasoning | 24 | 8 | 12 | 3 | 0 | 0 | 0 | 1 | 33.33% | 45.83% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 55 | 0 | 1 | 0 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 19 | 24 | 8 | 0 | 0 | 0 | 12 | 30.16% | 42.86% |
| Medium | 118 | 37 | 38 | 39 | 0 | 0 | 0 | 4 | 31.36% | 64.41% |
| Hard | 145 | 31 | 78 | 31 | 1 | 0 | 0 | 4 | 21.38% | 42.76% |
| Advanced | 102 | 21 | 60 | 20 | 0 | 0 | 1 | 0 | 20.59% | 40.20% |
| Expert | 14 | 3 | 10 | 0 | 1 | 0 | 0 | 0 | 21.43% | 21.43% |

## google.gemma-3-27b-it/hybrid/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 31 | 15 | 16 | 0 | 0 | 0 | 4 | 46.97% | 71.21% |
| Batch status queries | 38 | 13 | 12 | 11 | 0 | 0 | 0 | 2 | 34.21% | 63.16% |
| Enrichment and context queries | 59 | 25 | 13 | 21 | 0 | 0 | 0 | 0 | 42.37% | 77.97% |
| At-risk and critical detection | 58 | 40 | 11 | 5 | 0 | 0 | 0 | 2 | 68.97% | 77.59% |
| Scoring and quantitative analysis | 53 | 19 | 11 | 21 | 0 | 0 | 0 | 2 | 35.85% | 75.47% |
| Reference intelligence and rules | 55 | 25 | 14 | 6 | 0 | 0 | 0 | 10 | 45.45% | 56.36% |
| Temporal and transaction queries | 37 | 15 | 3 | 18 | 0 | 0 | 0 | 1 | 40.54% | 89.19% |
| Multi-step comparative queries | 76 | 1 | 16 | 58 | 1 | 0 | 0 | 0 | 1.32% | 77.63% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 10 | 5 | 0 | 0 | 0 | 0 | 0 | 66.67% | 66.67% |
| Filtered List | 42 | 19 | 10 | 0 | 0 | 0 | 0 | 13 | 45.24% | 45.24% |
| Categorical Aggregation | 63 | 21 | 10 | 32 | 0 | 0 | 0 | 0 | 33.33% | 84.13% |
| Comparative | 58 | 6 | 9 | 43 | 0 | 0 | 0 | 0 | 10.34% | 84.48% |
| Ranking | 33 | 15 | 9 | 9 | 0 | 0 | 0 | 0 | 45.45% | 72.73% |
| Temporal | 16 | 7 | 1 | 6 | 0 | 0 | 0 | 2 | 43.75% | 81.25% |
| Multi-Relational | 79 | 43 | 19 | 12 | 0 | 0 | 0 | 5 | 54.43% | 69.62% |
| Rule-Based Detection | 41 | 26 | 11 | 4 | 0 | 0 | 0 | 0 | 63.41% | 73.17% |
| Composite Reasoning | 24 | 11 | 6 | 6 | 0 | 0 | 0 | 1 | 45.83% | 70.83% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 100.00% | 100.00% |
| Multi-step Comparative | 56 | 0 | 11 | 44 | 1 | 0 | 0 | 0 | 0.00% | 78.57% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 26 | 13 | 12 | 0 | 0 | 0 | 12 | 41.27% | 60.32% |
| Medium | 118 | 52 | 19 | 43 | 0 | 0 | 0 | 4 | 44.07% | 80.51% |
| Hard | 145 | 53 | 36 | 51 | 0 | 0 | 0 | 5 | 36.55% | 71.72% |
| Advanced | 102 | 36 | 23 | 43 | 0 | 0 | 0 | 0 | 35.29% | 77.45% |
| Expert | 14 | 2 | 4 | 7 | 1 | 0 | 0 | 0 | 14.29% | 64.29% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 20 | 27 | 15 | 0 | 0 | 0 | 4 | 30.30% | 53.03% |
| Batch status queries | 38 | 7 | 21 | 8 | 0 | 0 | 0 | 2 | 18.42% | 39.47% |
| Enrichment and context queries | 59 | 18 | 27 | 14 | 0 | 0 | 0 | 0 | 30.51% | 54.24% |
| At-risk and critical detection | 58 | 34 | 16 | 6 | 0 | 0 | 0 | 2 | 58.62% | 68.97% |
| Scoring and quantitative analysis | 53 | 13 | 22 | 16 | 0 | 0 | 0 | 2 | 24.53% | 54.72% |
| Reference intelligence and rules | 55 | 21 | 20 | 4 | 0 | 0 | 0 | 10 | 38.18% | 45.45% |
| Temporal and transaction queries | 37 | 11 | 10 | 15 | 0 | 0 | 0 | 1 | 29.73% | 70.27% |
| Multi-step comparative queries | 76 | 1 | 64 | 10 | 1 | 0 | 0 | 0 | 1.32% | 14.47% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 7 | 8 | 0 | 0 | 0 | 0 | 0 | 46.67% | 46.67% |
| Filtered List | 42 | 12 | 17 | 0 | 0 | 0 | 0 | 13 | 28.57% | 28.57% |
| Categorical Aggregation | 63 | 15 | 24 | 24 | 0 | 0 | 0 | 0 | 23.81% | 61.90% |
| Comparative | 58 | 4 | 18 | 36 | 0 | 0 | 0 | 0 | 6.90% | 68.97% |
| Ranking | 33 | 7 | 21 | 5 | 0 | 0 | 0 | 0 | 21.21% | 36.36% |
| Temporal | 16 | 4 | 3 | 7 | 0 | 0 | 0 | 2 | 25.00% | 68.75% |
| Multi-Relational | 79 | 38 | 25 | 11 | 0 | 0 | 0 | 5 | 48.10% | 62.03% |
| Rule-Based Detection | 41 | 17 | 19 | 5 | 0 | 0 | 0 | 0 | 41.46% | 53.66% |
| Composite Reasoning | 24 | 11 | 12 | 0 | 0 | 0 | 0 | 1 | 45.83% | 45.83% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 55 | 0 | 1 | 0 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 19 | 23 | 9 | 0 | 0 | 0 | 12 | 30.16% | 44.44% |
| Medium | 118 | 36 | 44 | 34 | 0 | 0 | 0 | 4 | 30.51% | 59.32% |
| Hard | 145 | 38 | 80 | 22 | 0 | 0 | 0 | 5 | 26.21% | 41.38% |
| Advanced | 102 | 30 | 50 | 22 | 0 | 0 | 0 | 0 | 29.41% | 50.98% |
| Expert | 14 | 2 | 10 | 1 | 1 | 0 | 0 | 0 | 14.29% | 21.43% |

## mistral.mistral-large-3-675b-instruct/hybrid/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 30 | 14 | 18 | 0 | 0 | 0 | 4 | 45.45% | 72.73% |
| Batch status queries | 38 | 13 | 11 | 12 | 0 | 0 | 0 | 2 | 34.21% | 65.79% |
| Enrichment and context queries | 59 | 21 | 16 | 22 | 0 | 0 | 0 | 0 | 35.59% | 72.88% |
| At-risk and critical detection | 58 | 43 | 7 | 6 | 0 | 0 | 0 | 2 | 74.14% | 84.48% |
| Scoring and quantitative analysis | 53 | 23 | 5 | 22 | 0 | 0 | 1 | 2 | 43.40% | 84.91% |
| Reference intelligence and rules | 55 | 33 | 8 | 4 | 0 | 0 | 0 | 10 | 60.00% | 67.27% |
| Temporal and transaction queries | 37 | 16 | 5 | 15 | 0 | 0 | 0 | 1 | 43.24% | 83.78% |
| Multi-step comparative queries | 76 | 0 | 10 | 66 | 0 | 0 | 0 | 0 | 0.00% | 86.84% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 9 | 5 | 1 | 0 | 0 | 0 | 0 | 60.00% | 66.67% |
| Filtered List | 42 | 23 | 5 | 1 | 0 | 0 | 0 | 13 | 54.76% | 57.14% |
| Categorical Aggregation | 63 | 22 | 7 | 34 | 0 | 0 | 0 | 0 | 34.92% | 88.89% |
| Comparative | 58 | 7 | 7 | 44 | 0 | 0 | 0 | 0 | 12.07% | 87.93% |
| Ranking | 33 | 15 | 7 | 11 | 0 | 0 | 0 | 0 | 45.45% | 78.79% |
| Temporal | 16 | 10 | 0 | 4 | 0 | 0 | 0 | 2 | 62.50% | 87.50% |
| Multi-Relational | 79 | 42 | 19 | 12 | 0 | 0 | 1 | 5 | 53.16% | 68.35% |
| Rule-Based Detection | 41 | 27 | 11 | 3 | 0 | 0 | 0 | 0 | 65.85% | 73.17% |
| Composite Reasoning | 24 | 12 | 5 | 6 | 0 | 0 | 0 | 1 | 50.00% | 75.00% |
| Reference Compliance | 10 | 7 | 3 | 0 | 0 | 0 | 0 | 0 | 70.00% | 70.00% |
| Exception Detection | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 100.00% | 100.00% |
| Multi-step Comparative | 56 | 0 | 7 | 49 | 0 | 0 | 0 | 0 | 0.00% | 87.50% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 24 | 10 | 17 | 0 | 0 | 0 | 12 | 38.10% | 65.08% |
| Medium | 118 | 57 | 13 | 44 | 0 | 0 | 0 | 4 | 48.31% | 85.59% |
| Hard | 145 | 56 | 23 | 61 | 0 | 0 | 0 | 5 | 38.62% | 80.69% |
| Advanced | 102 | 41 | 25 | 35 | 0 | 0 | 1 | 0 | 40.20% | 74.51% |
| Expert | 14 | 1 | 5 | 8 | 0 | 0 | 0 | 0 | 7.14% | 64.29% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 18 | 30 | 14 | 0 | 0 | 0 | 4 | 27.27% | 48.48% |
| Batch status queries | 38 | 7 | 17 | 12 | 0 | 0 | 0 | 2 | 18.42% | 50.00% |
| Enrichment and context queries | 59 | 14 | 30 | 15 | 0 | 0 | 0 | 0 | 23.73% | 49.15% |
| At-risk and critical detection | 58 | 37 | 12 | 7 | 0 | 0 | 0 | 2 | 63.79% | 75.86% |
| Scoring and quantitative analysis | 53 | 16 | 19 | 15 | 0 | 0 | 1 | 2 | 30.19% | 58.49% |
| Reference intelligence and rules | 55 | 21 | 20 | 4 | 0 | 0 | 0 | 10 | 38.18% | 45.45% |
| Temporal and transaction queries | 37 | 11 | 12 | 13 | 0 | 0 | 0 | 1 | 29.73% | 64.86% |
| Multi-step comparative queries | 76 | 0 | 61 | 15 | 0 | 0 | 0 | 0 | 0.00% | 19.74% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 7 | 8 | 0 | 0 | 0 | 0 | 0 | 46.67% | 46.67% |
| Filtered List | 42 | 15 | 13 | 1 | 0 | 0 | 0 | 13 | 35.71% | 38.10% |
| Categorical Aggregation | 63 | 13 | 25 | 25 | 0 | 0 | 0 | 0 | 20.63% | 60.32% |
| Comparative | 58 | 4 | 13 | 41 | 0 | 0 | 0 | 0 | 6.90% | 77.59% |
| Ranking | 33 | 7 | 19 | 7 | 0 | 0 | 0 | 0 | 21.21% | 42.42% |
| Temporal | 16 | 6 | 2 | 6 | 0 | 0 | 0 | 2 | 37.50% | 75.00% |
| Multi-Relational | 79 | 35 | 28 | 10 | 0 | 0 | 1 | 5 | 44.30% | 56.96% |
| Rule-Based Detection | 41 | 16 | 21 | 4 | 0 | 0 | 0 | 0 | 39.02% | 48.78% |
| Composite Reasoning | 24 | 11 | 11 | 1 | 0 | 0 | 0 | 1 | 45.83% | 50.00% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 56 | 0 | 0 | 0 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 17 | 25 | 9 | 0 | 0 | 0 | 12 | 26.98% | 41.27% |
| Medium | 118 | 37 | 33 | 44 | 0 | 0 | 0 | 4 | 31.36% | 68.64% |
| Hard | 145 | 36 | 82 | 22 | 0 | 0 | 0 | 5 | 24.83% | 40.00% |
| Advanced | 102 | 33 | 49 | 19 | 0 | 0 | 1 | 0 | 32.35% | 50.98% |
| Expert | 14 | 1 | 12 | 1 | 0 | 0 | 0 | 0 | 7.14% | 14.29% |

## nvidia.nemotron-super-3-120b/hybrid/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 21 | 22 | 19 | 0 | 0 | 0 | 4 | 31.82% | 60.61% |
| Batch status queries | 38 | 10 | 14 | 12 | 0 | 0 | 0 | 2 | 26.32% | 57.89% |
| Enrichment and context queries | 59 | 19 | 22 | 18 | 0 | 0 | 0 | 0 | 32.20% | 62.71% |
| At-risk and critical detection | 58 | 28 | 21 | 7 | 0 | 0 | 0 | 2 | 48.28% | 60.34% |
| Scoring and quantitative analysis | 53 | 16 | 15 | 17 | 0 | 0 | 3 | 2 | 30.19% | 62.26% |
| Reference intelligence and rules | 55 | 25 | 11 | 9 | 0 | 0 | 0 | 10 | 45.45% | 61.82% |
| Temporal and transaction queries | 37 | 9 | 10 | 17 | 0 | 0 | 0 | 1 | 24.32% | 70.27% |
| Multi-step comparative queries | 76 | 1 | 12 | 63 | 0 | 0 | 0 | 0 | 1.32% | 84.21% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 12 | 3 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Filtered List | 42 | 13 | 15 | 1 | 0 | 0 | 0 | 13 | 30.95% | 33.33% |
| Categorical Aggregation | 63 | 16 | 8 | 39 | 0 | 0 | 0 | 0 | 25.40% | 87.30% |
| Comparative | 58 | 5 | 10 | 43 | 0 | 0 | 0 | 0 | 8.62% | 82.76% |
| Ranking | 33 | 8 | 17 | 7 | 0 | 0 | 1 | 0 | 24.24% | 45.45% |
| Temporal | 16 | 7 | 2 | 5 | 0 | 0 | 0 | 2 | 43.75% | 75.00% |
| Multi-Relational | 79 | 32 | 30 | 11 | 0 | 0 | 1 | 5 | 40.51% | 54.43% |
| Rule-Based Detection | 41 | 17 | 22 | 2 | 0 | 0 | 0 | 0 | 41.46% | 46.34% |
| Composite Reasoning | 24 | 7 | 10 | 5 | 0 | 0 | 1 | 1 | 29.17% | 50.00% |
| Reference Compliance | 10 | 7 | 3 | 0 | 0 | 0 | 0 | 0 | 70.00% | 70.00% |
| Exception Detection | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 100.00% | 100.00% |
| Multi-step Comparative | 56 | 0 | 7 | 49 | 0 | 0 | 0 | 0 | 0.00% | 87.50% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 22 | 11 | 18 | 0 | 0 | 0 | 12 | 34.92% | 63.49% |
| Medium | 118 | 46 | 22 | 46 | 0 | 0 | 0 | 4 | 38.98% | 77.97% |
| Hard | 145 | 31 | 52 | 57 | 0 | 0 | 0 | 5 | 21.38% | 60.69% |
| Advanced | 102 | 27 | 38 | 34 | 0 | 0 | 3 | 0 | 26.47% | 59.80% |
| Expert | 14 | 3 | 4 | 7 | 0 | 0 | 0 | 0 | 21.43% | 71.43% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 15 | 36 | 11 | 0 | 0 | 0 | 4 | 22.73% | 39.39% |
| Batch status queries | 38 | 7 | 19 | 10 | 0 | 0 | 0 | 2 | 18.42% | 44.74% |
| Enrichment and context queries | 59 | 11 | 34 | 14 | 0 | 0 | 0 | 0 | 18.64% | 42.37% |
| At-risk and critical detection | 58 | 25 | 23 | 8 | 0 | 0 | 0 | 2 | 43.10% | 56.90% |
| Scoring and quantitative analysis | 53 | 12 | 20 | 16 | 0 | 0 | 3 | 2 | 22.64% | 52.83% |
| Reference intelligence and rules | 55 | 17 | 22 | 6 | 0 | 0 | 0 | 10 | 30.91% | 41.82% |
| Temporal and transaction queries | 37 | 9 | 18 | 9 | 0 | 0 | 0 | 1 | 24.32% | 48.65% |
| Multi-step comparative queries | 76 | 1 | 63 | 12 | 0 | 0 | 0 | 0 | 1.32% | 17.11% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 8 | 7 | 0 | 0 | 0 | 0 | 0 | 53.33% | 53.33% |
| Filtered List | 42 | 9 | 20 | 0 | 0 | 0 | 0 | 13 | 21.43% | 21.43% |
| Categorical Aggregation | 63 | 9 | 26 | 28 | 0 | 0 | 0 | 0 | 14.29% | 58.73% |
| Comparative | 58 | 3 | 15 | 40 | 0 | 0 | 0 | 0 | 5.17% | 74.14% |
| Ranking | 33 | 5 | 23 | 4 | 0 | 0 | 1 | 0 | 15.15% | 27.27% |
| Temporal | 16 | 4 | 6 | 4 | 0 | 0 | 0 | 2 | 25.00% | 50.00% |
| Multi-Relational | 79 | 29 | 37 | 7 | 0 | 0 | 1 | 5 | 36.71% | 45.57% |
| Rule-Based Detection | 41 | 13 | 26 | 2 | 0 | 0 | 0 | 0 | 31.71% | 36.59% |
| Composite Reasoning | 24 | 7 | 14 | 1 | 0 | 0 | 1 | 1 | 29.17% | 33.33% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 56 | 0 | 0 | 0 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 16 | 27 | 8 | 0 | 0 | 0 | 12 | 25.40% | 38.10% |
| Medium | 118 | 30 | 45 | 39 | 0 | 0 | 0 | 4 | 25.42% | 58.47% |
| Hard | 145 | 24 | 93 | 23 | 0 | 0 | 0 | 5 | 16.55% | 32.41% |
| Advanced | 102 | 24 | 59 | 16 | 0 | 0 | 3 | 0 | 23.53% | 39.22% |
| Expert | 14 | 3 | 11 | 0 | 0 | 0 | 0 | 0 | 21.43% | 21.43% |

## qwen.qwen3-coder-480b-a35b-instruct/hybrid/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 29 | 14 | 19 | 0 | 0 | 0 | 4 | 43.94% | 72.73% |
| Batch status queries | 38 | 16 | 11 | 9 | 0 | 0 | 0 | 2 | 42.11% | 65.79% |
| Enrichment and context queries | 59 | 23 | 18 | 18 | 0 | 0 | 0 | 0 | 38.98% | 69.49% |
| At-risk and critical detection | 58 | 40 | 10 | 6 | 0 | 0 | 0 | 2 | 68.97% | 79.31% |
| Scoring and quantitative analysis | 53 | 21 | 8 | 20 | 0 | 0 | 2 | 2 | 39.62% | 77.36% |
| Reference intelligence and rules | 55 | 29 | 9 | 7 | 0 | 0 | 0 | 10 | 52.73% | 65.45% |
| Temporal and transaction queries | 37 | 13 | 8 | 15 | 0 | 0 | 0 | 1 | 35.14% | 75.68% |
| Multi-step comparative queries | 76 | 1 | 15 | 60 | 0 | 0 | 0 | 0 | 1.32% | 80.26% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 14 | 1 | 0 | 0 | 0 | 0 | 0 | 93.33% | 93.33% |
| Filtered List | 42 | 23 | 6 | 0 | 0 | 0 | 0 | 13 | 54.76% | 54.76% |
| Categorical Aggregation | 63 | 22 | 7 | 34 | 0 | 0 | 0 | 0 | 34.92% | 88.89% |
| Comparative | 58 | 6 | 9 | 43 | 0 | 0 | 0 | 0 | 10.34% | 84.48% |
| Ranking | 33 | 10 | 12 | 10 | 0 | 0 | 1 | 0 | 30.30% | 60.61% |
| Temporal | 16 | 8 | 1 | 5 | 0 | 0 | 0 | 2 | 50.00% | 81.25% |
| Multi-Relational | 79 | 40 | 26 | 8 | 0 | 0 | 0 | 5 | 50.63% | 60.76% |
| Rule-Based Detection | 41 | 27 | 10 | 4 | 0 | 0 | 0 | 0 | 65.85% | 75.61% |
| Composite Reasoning | 24 | 11 | 6 | 5 | 0 | 0 | 1 | 1 | 45.83% | 66.67% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 100.00% | 100.00% |
| Multi-step Comparative | 56 | 0 | 11 | 45 | 0 | 0 | 0 | 0 | 0.00% | 80.36% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 26 | 9 | 16 | 0 | 0 | 0 | 12 | 41.27% | 66.67% |
| Medium | 118 | 53 | 18 | 43 | 0 | 0 | 0 | 4 | 44.92% | 81.36% |
| Hard | 145 | 52 | 38 | 50 | 0 | 0 | 0 | 5 | 35.86% | 70.34% |
| Advanced | 102 | 39 | 22 | 39 | 0 | 0 | 2 | 0 | 38.24% | 76.47% |
| Expert | 14 | 2 | 6 | 6 | 0 | 0 | 0 | 0 | 14.29% | 57.14% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 19 | 27 | 16 | 0 | 0 | 0 | 4 | 28.79% | 53.03% |
| Batch status queries | 38 | 10 | 17 | 9 | 0 | 0 | 0 | 2 | 26.32% | 50.00% |
| Enrichment and context queries | 59 | 17 | 27 | 15 | 0 | 0 | 0 | 0 | 28.81% | 54.24% |
| At-risk and critical detection | 58 | 32 | 14 | 10 | 0 | 0 | 0 | 2 | 55.17% | 72.41% |
| Scoring and quantitative analysis | 53 | 16 | 15 | 18 | 0 | 0 | 2 | 2 | 30.19% | 64.15% |
| Reference intelligence and rules | 55 | 20 | 20 | 5 | 0 | 0 | 0 | 10 | 36.36% | 45.45% |
| Temporal and transaction queries | 37 | 11 | 15 | 10 | 0 | 0 | 0 | 1 | 29.73% | 56.76% |
| Multi-step comparative queries | 76 | 1 | 63 | 12 | 0 | 0 | 0 | 0 | 1.32% | 17.11% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 11 | 4 | 0 | 0 | 0 | 0 | 0 | 73.33% | 73.33% |
| Filtered List | 42 | 15 | 13 | 1 | 0 | 0 | 0 | 13 | 35.71% | 38.10% |
| Categorical Aggregation | 63 | 13 | 20 | 30 | 0 | 0 | 0 | 0 | 20.63% | 68.25% |
| Comparative | 58 | 5 | 16 | 37 | 0 | 0 | 0 | 0 | 8.62% | 72.41% |
| Ranking | 33 | 7 | 17 | 8 | 0 | 0 | 1 | 0 | 21.21% | 45.45% |
| Temporal | 16 | 5 | 4 | 5 | 0 | 0 | 0 | 2 | 31.25% | 62.50% |
| Multi-Relational | 79 | 34 | 31 | 9 | 0 | 0 | 0 | 5 | 43.04% | 54.43% |
| Rule-Based Detection | 41 | 16 | 21 | 4 | 0 | 0 | 0 | 0 | 39.02% | 48.78% |
| Composite Reasoning | 24 | 11 | 10 | 1 | 0 | 0 | 1 | 1 | 45.83% | 50.00% |
| Reference Compliance | 10 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 50.00% | 50.00% |
| Exception Detection | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 56 | 0 | 0 | 0 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 20 | 20 | 11 | 0 | 0 | 0 | 12 | 31.75% | 49.21% |
| Medium | 118 | 39 | 42 | 33 | 0 | 0 | 0 | 4 | 33.05% | 61.02% |
| Hard | 145 | 33 | 80 | 27 | 0 | 0 | 0 | 5 | 22.76% | 41.38% |
| Advanced | 102 | 32 | 45 | 23 | 0 | 0 | 2 | 0 | 31.37% | 53.92% |
| Expert | 14 | 2 | 11 | 1 | 0 | 0 | 0 | 0 | 14.29% | 21.43% |

## qwen.qwen3-vl-235b-a22b-instruct/hybrid/train

### GPT-OSS 120B Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 31 | 10 | 21 | 0 | 0 | 0 | 4 | 46.97% | 78.79% |
| Batch status queries | 38 | 13 | 13 | 10 | 0 | 0 | 0 | 2 | 34.21% | 60.53% |
| Enrichment and context queries | 59 | 26 | 12 | 21 | 0 | 0 | 0 | 0 | 44.07% | 79.66% |
| At-risk and critical detection | 58 | 39 | 11 | 6 | 0 | 0 | 0 | 2 | 67.24% | 77.59% |
| Scoring and quantitative analysis | 53 | 21 | 9 | 20 | 0 | 0 | 1 | 2 | 39.62% | 77.36% |
| Reference intelligence and rules | 55 | 29 | 11 | 5 | 0 | 0 | 0 | 10 | 52.73% | 61.82% |
| Temporal and transaction queries | 37 | 15 | 5 | 16 | 0 | 0 | 0 | 1 | 40.54% | 83.78% |
| Multi-step comparative queries | 76 | 1 | 8 | 67 | 0 | 0 | 0 | 0 | 1.32% | 89.47% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 10 | 4 | 1 | 0 | 0 | 0 | 0 | 66.67% | 73.33% |
| Filtered List | 42 | 24 | 5 | 0 | 0 | 0 | 0 | 13 | 57.14% | 57.14% |
| Categorical Aggregation | 63 | 19 | 10 | 34 | 0 | 0 | 0 | 0 | 30.16% | 84.13% |
| Comparative | 58 | 6 | 6 | 46 | 0 | 0 | 0 | 0 | 10.34% | 89.66% |
| Ranking | 33 | 13 | 8 | 12 | 0 | 0 | 0 | 0 | 39.39% | 75.76% |
| Temporal | 16 | 9 | 0 | 5 | 0 | 0 | 0 | 2 | 56.25% | 87.50% |
| Multi-Relational | 79 | 45 | 17 | 12 | 0 | 0 | 0 | 5 | 56.96% | 72.15% |
| Rule-Based Detection | 41 | 27 | 10 | 4 | 0 | 0 | 0 | 0 | 65.85% | 75.61% |
| Composite Reasoning | 24 | 11 | 8 | 3 | 0 | 0 | 1 | 1 | 45.83% | 58.33% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 100.00% | 100.00% |
| Multi-step Comparative | 56 | 0 | 7 | 49 | 0 | 0 | 0 | 0 | 0.00% | 87.50% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 23 | 11 | 17 | 0 | 0 | 0 | 12 | 36.51% | 63.49% |
| Medium | 118 | 54 | 16 | 44 | 0 | 0 | 0 | 4 | 45.76% | 83.05% |
| Hard | 145 | 55 | 27 | 58 | 0 | 0 | 0 | 5 | 37.93% | 77.93% |
| Advanced | 102 | 41 | 21 | 39 | 0 | 0 | 1 | 0 | 40.20% | 78.43% |
| Expert | 14 | 2 | 4 | 8 | 0 | 0 | 0 | 0 | 14.29% | 71.43% |

### GPT-5.6 Sol Grader

#### Question Category

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Investor status checks | 66 | 23 | 23 | 16 | 0 | 0 | 0 | 4 | 34.85% | 59.09% |
| Batch status queries | 38 | 7 | 18 | 11 | 0 | 0 | 0 | 2 | 18.42% | 47.37% |
| Enrichment and context queries | 59 | 20 | 26 | 13 | 0 | 0 | 0 | 0 | 33.90% | 55.93% |
| At-risk and critical detection | 58 | 30 | 19 | 7 | 0 | 0 | 0 | 2 | 51.72% | 63.79% |
| Scoring and quantitative analysis | 53 | 17 | 15 | 18 | 0 | 0 | 1 | 2 | 32.08% | 66.04% |
| Reference intelligence and rules | 55 | 17 | 23 | 5 | 0 | 0 | 0 | 10 | 30.91% | 40.00% |
| Temporal and transaction queries | 37 | 12 | 11 | 13 | 0 | 0 | 0 | 1 | 32.43% | 67.57% |
| Multi-step comparative queries | 76 | 1 | 60 | 15 | 0 | 0 | 0 | 0 | 1.32% | 21.05% |

#### Query Type

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct Retrieval | 15 | 10 | 5 | 0 | 0 | 0 | 0 | 0 | 66.67% | 66.67% |
| Filtered List | 42 | 14 | 14 | 1 | 0 | 0 | 0 | 13 | 33.33% | 35.71% |
| Categorical Aggregation | 63 | 9 | 26 | 28 | 0 | 0 | 0 | 0 | 14.29% | 58.73% |
| Comparative | 58 | 4 | 13 | 41 | 0 | 0 | 0 | 0 | 6.90% | 77.59% |
| Ranking | 33 | 6 | 19 | 8 | 0 | 0 | 0 | 0 | 18.18% | 42.42% |
| Temporal | 16 | 6 | 2 | 6 | 0 | 0 | 0 | 2 | 37.50% | 75.00% |
| Multi-Relational | 79 | 40 | 25 | 9 | 0 | 0 | 0 | 5 | 50.63% | 62.03% |
| Rule-Based Detection | 41 | 18 | 19 | 4 | 0 | 0 | 0 | 0 | 43.90% | 53.66% |
| Composite Reasoning | 24 | 10 | 11 | 1 | 0 | 0 | 1 | 1 | 41.67% | 45.83% |
| Reference Compliance | 10 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 60.00% | 60.00% |
| Exception Detection | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 80.00% | 80.00% |
| Multi-step Comparative | 56 | 0 | 56 | 0 | 0 | 0 | 0 | 0 | 0.00% | 0.00% |

#### Difficulty

| Group | Rows | Match | Mismatch | Partial | Scan Error | Crash | Pre Scan Error | Other | Match % | Match+Partial % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 63 | 20 | 19 | 12 | 0 | 0 | 0 | 12 | 31.75% | 50.79% |
| Medium | 118 | 37 | 41 | 36 | 0 | 0 | 0 | 4 | 31.36% | 61.86% |
| Hard | 145 | 34 | 77 | 29 | 0 | 0 | 0 | 5 | 23.45% | 43.45% |
| Advanced | 102 | 34 | 47 | 20 | 0 | 0 | 1 | 0 | 33.33% | 52.94% |
| Expert | 14 | 2 | 11 | 1 | 0 | 0 | 0 | 0 | 14.29% | 21.43% |
