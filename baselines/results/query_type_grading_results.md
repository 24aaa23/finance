# Grading results by query type

GPT-5.6 TERA grading counts grouped by the CSV `Query Type` field. Each pipeline is reported independently.

Each table reports `MATCH`, `MISMATCH`, and `PARTIAL` counts and reconciles to 1,000 queries.

## Base SPARQL

| Query Type | Total | MATCH | MISMATCH | PARTIAL |
|---|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 102 | 65 | 45 |
| Comparative | 15 | 1 | 9 | 5 |
| Composite Reasoning | 143 | 56 | 68 | 19 |
| Direct Retrieval | 34 | 25 | 1 | 8 |
| Exception Detection | 53 | 53 | 0 | 0 |
| Filtered List | 103 | 91 | 9 | 3 |
| Multi-Relational | 212 | 148 | 41 | 23 |
| Multi-step Comparative | 55 | 0 | 35 | 20 |
| Ranking | 65 | 54 | 11 | 0 |
| Reference Compliance | 39 | 30 | 8 | 1 |
| Rule-Based Detection | 29 | 27 | 1 | 1 |
| Temporal | 40 | 31 | 9 | 0 |
| **Overall** | **1000** | **618** | **257** | **125** |

## Base SQL

| Query Type | Total | MATCH | MISMATCH | PARTIAL |
|---|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 176 | 25 | 11 |
| Comparative | 15 | 5 | 3 | 7 |
| Composite Reasoning | 143 | 117 | 1 | 25 |
| Direct Retrieval | 34 | 34 | 0 | 0 |
| Exception Detection | 53 | 50 | 2 | 1 |
| Filtered List | 103 | 87 | 9 | 7 |
| Multi-Relational | 212 | 183 | 14 | 15 |
| Multi-step Comparative | 55 | 14 | 8 | 33 |
| Ranking | 65 | 55 | 8 | 2 |
| Reference Compliance | 39 | 30 | 1 | 8 |
| Rule-Based Detection | 29 | 26 | 2 | 1 |
| Temporal | 40 | 38 | 2 | 0 |
| **Overall** | **1000** | **815** | **75** | **110** |

## GraphRAG Local

| Query Type | Total | MATCH | MISMATCH | PARTIAL |
|---|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 1 | 209 | 2 |
| Comparative | 15 | 0 | 15 | 0 |
| Composite Reasoning | 143 | 2 | 139 | 2 |
| Direct Retrieval | 34 | 30 | 4 | 0 |
| Exception Detection | 53 | 3 | 48 | 2 |
| Filtered List | 103 | 2 | 93 | 8 |
| Multi-Relational | 212 | 13 | 183 | 16 |
| Multi-step Comparative | 55 | 0 | 55 | 0 |
| Ranking | 65 | 0 | 64 | 1 |
| Reference Compliance | 39 | 9 | 27 | 3 |
| Rule-Based Detection | 29 | 0 | 27 | 2 |
| Temporal | 40 | 0 | 40 | 0 |
| **Overall** | **1000** | **60** | **904** | **36** |

## Parallel SPARQL

| Query Type | Total | MATCH | MISMATCH | PARTIAL |
|---|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 82 | 76 | 54 |
| Comparative | 15 | 0 | 13 | 2 |
| Composite Reasoning | 143 | 36 | 95 | 12 |
| Direct Retrieval | 34 | 19 | 14 | 1 |
| Exception Detection | 53 | 45 | 4 | 4 |
| Filtered List | 103 | 46 | 53 | 4 |
| Multi-Relational | 212 | 78 | 109 | 25 |
| Multi-step Comparative | 55 | 0 | 54 | 1 |
| Ranking | 65 | 21 | 42 | 2 |
| Reference Compliance | 39 | 28 | 11 | 0 |
| Rule-Based Detection | 29 | 16 | 13 | 0 |
| Temporal | 40 | 11 | 29 | 0 |
| **Overall** | **1000** | **382** | **513** | **105** |

## Parallel SQL

| Query Type | Total | MATCH | MISMATCH | PARTIAL |
|---|---:|---:|---:|---:|
| Categorical Aggregation | 212 | 167 | 42 | 3 |
| Comparative | 15 | 4 | 9 | 2 |
| Composite Reasoning | 143 | 117 | 5 | 21 |
| Direct Retrieval | 34 | 34 | 0 | 0 |
| Exception Detection | 53 | 50 | 3 | 0 |
| Filtered List | 103 | 87 | 12 | 4 |
| Multi-Relational | 212 | 183 | 22 | 7 |
| Multi-step Comparative | 55 | 17 | 27 | 11 |
| Ranking | 65 | 52 | 13 | 0 |
| Reference Compliance | 39 | 33 | 1 | 5 |
| Rule-Based Detection | 29 | 24 | 5 | 0 |
| Temporal | 40 | 38 | 2 | 0 |
| **Overall** | **1000** | **806** | **141** | **53** |
