# DAIL-SQL baseline implementation and run notes

## Upstream basis

- Repository: [BeachWang/DAIL-SQL](https://github.com/BeachWang/DAIL-SQL)
- Pinned commit: `2061f68112222083134a0c9e2877961ff315ff44`
- Upstream license: Apache License 2.0

## Adaptation for this benchmark

- Replaced the upstream target datasets with the existing 1,000-question wealth-management benchmark and SQLite database.
- Replaced the upstream generation model with `openai.gpt-oss-120b-1:0`.
- Used the separate validated 300-question SQL training workbook as the demonstration bank. Evaluation SQL and answers were not used as demonstrations.
- Retained two-stage DAIL selection: nine masked-question examples, preliminary SQL, SQL-skeleton reselection at threshold `0.85`, and nine final examples.
- Replaced Stanford CoreNLP and `all-mpnet-base-v2` with local schema-aware masking and normalized TF-IDF Euclidean distance to fit the established baseline environment.
- Added `domain_intro.prompt` (SHA-256 `949546f7d36d89a79c20f39c8fc00bf7e60d15634c8f9915381aa56dd0dbeece`) and `phase0_business_rules.md` (SHA-256 `4820bfd42c2c69231669027420d10eab0cf5493e6c46193914806c5c33e072b2`) verbatim to both generation stages.
- Added the output-only instruction: return only the complete SQLite query with no reasoning, explanations, Markdown, comments, or prose.
- Executed generated SQL through a read-only SQLite connection and recorded tokens, generation latency, total elapsed time, selections, SQL, and raw rows.

## Run and grading

- Pipeline rows: 1,000
- Successful SQL executions before grading: 998
- SQL execution errors before grading: 2
- Grading: eight parallel 125-question shards using the unchanged grader prompt and `gpt-5-mini`.
- The shard merge validated 1,000 unique IDs and restored original benchmark order.

## GPT-5 Mini results

| MATCH | MISMATCH | PARTIAL | OTHER / ERROR | Total |
|---:|---:|---:|---:|---:|
| 736 | 61 | 202 | 1 | 1000 |

Other status details: `OTHER`: 1.

## Published artifacts

- Raw 1,000-question pipeline CSV
- GPT-5 Mini graded 1,000-question CSV
- Query-type grading report
- Eight-category grading report
- Accuracy, token-latency, inference-cost, and execution-efficiency report
