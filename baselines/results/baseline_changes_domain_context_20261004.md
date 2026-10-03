# Domain-context baseline changes — 2026-10-04

## Scope

This snapshot reran and graded all five 1,000-question baselines after adding two shared reference documents to every generation prompt:

- `domain_intro.prompt` — SHA-256 `949546f7d36d89a79c20f39c8fc00bf7e60d15634c8f9915381aa56dd0dbeece`
- `phase0_business_rules.md` — SHA-256 `4820bfd42c2c69231669027420d10eab0cf5493e6c46193914806c5c33e072b2`

Both files were passed verbatim under a `Reference context` section. The existing runtime schema/DDL or retrieved RDF facts, benchmark question, and output-only constraint remained in each prompt. SQL and SPARQL generators still receive the instruction to return only the query, with no reasoning, prose, comments, or Markdown.

The business-rules document itself states that its intended scope is the 442 disputed rows and that it does not change the 1,000-question corpus. It was nevertheless supplied verbatim to all five baselines for this experiment, as requested.

## Pipeline changes

| Pipeline | Published version | Added context | Execution route |
|---|---|---|---|
| Base SPARQL | `base-sparql-domain-intro-phase0-rules-v1` | Both reference files | Generated SPARQL executed on Fuseki |
| Base SQL | `base-sql-domain-intro-phase0-rules-v1` | Both reference files | Generated SQL executed read-only on SQLite |
| GraphRAG Local | `graph-rag-local-domain-intro-phase0-rules-v1` | Both reference files | Local SQLite/FTS graph-neighborhood retrieval only |
| Parallel SPARQL | `parallel-sparql-domain-intro-phase0-rules-v1` | Both reference files in every branch | Three generated/executed SPARQL branches with result consensus |
| Parallel SQL | `parallel-sql-domain-intro-phase0-rules-v1` | Both reference files in every branch | Three generated/executed SQL branches with result consensus |

Only the local GraphRAG implementation is included. No GraphRAG hybrid code or hybrid result is published.

## Run and grading procedure

- Each pipeline processed all 1,000 questions.
- The existing external grader prompt was not changed.
- All result files were graded with `gpt-5-mini`.
- The two parallel raw reports required a mechanical grading-input adapter that copied `Processed Rows` to `Scan Raw Rows`; this did not alter the grader prompt or the pipeline answers.

## Operational results before external grading

| Pipeline | Operational result |
|---|---|
| Base SPARQL | 957 successful executions, 42 execution errors, 1 empty SPARQL output |
| Base SQL | 998 successful executions, 2 execution errors |
| GraphRAG Local | 374 answered, 622 insufficient-evidence outputs, 4 crashes |
| Parallel SPARQL | 774 consensus results, 226 no-consensus failures |
| Parallel SQL | 852 consensus results, 148 no-consensus failures |

## GPT-5 Mini grade totals

`OTHER / ERROR` includes every status other than `MATCH`, `MISMATCH`, and `PARTIAL`.

| Pipeline | MATCH | MISMATCH | PARTIAL | OTHER / ERROR | Total |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 452 | 253 | 288 | 7 | 1,000 |
| Base SQL | 681 | 92 | 226 | 1 | 1,000 |
| GraphRAG Local | 62 | 875 | 58 | 5 | 1,000 |
| Parallel SPARQL | 401 | 386 | 212 | 1 | 1,000 |
| Parallel SQL | 600 | 233 | 166 | 1 | 1,000 |

Non-semantic status details are: Base SPARQL `OTHER` 7; Base SQL `TOKEN_OUTPUT_ERROR` 1; GraphRAG Local `CRASH` 4 and `TOKEN_OUTPUT_ERROR` 1; Parallel SPARQL `OTHER` 1; Parallel SQL `OTHER` 1.

## Change from the preceding schema-only/domain-neutral snapshot

The table shows `MATCH / MISMATCH / PARTIAL / OTHER-or-error`. Both snapshots use the same grader model, but the generation context changed. Model and service nondeterminism may still contribute to differences.

| Pipeline | Previous snapshot | Domain-context snapshot | MATCH change |
|---|---:|---:|---:|
| Base SPARQL | 495 / 182 / 311 / 12 | 452 / 253 / 288 / 7 | -43 |
| Base SQL | 662 / 105 / 228 / 5 | 681 / 92 / 226 / 1 | +19 |
| GraphRAG Local | 68 / 876 / 54 / 2 | 62 / 875 / 58 / 5 | -6 |
| Parallel SPARQL | 454 / 326 / 220 / 0 | 401 / 386 / 212 / 1 | -53 |
| Parallel SQL | 632 / 168 / 198 / 2 | 600 / 233 / 166 / 1 | -32 |

## Reports

- `query_type_grading_results_domain_context_gpt_5_mini.md`
- `category_grading_results_125_each_domain_context_gpt_5_mini.md`
- `baseline_metrics_domain_context_gpt_5_mini.md`
