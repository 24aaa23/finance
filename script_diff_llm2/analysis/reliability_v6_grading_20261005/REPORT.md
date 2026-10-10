# Completed reliability v6 grading: GPT-OSS without context

This report analyzes existing saved CSVs only. It makes no grading/model calls and does not change pipeline code, grader behavior, or saved run outputs. Counts are a snapshot; ongoing grading is recorded separately in `summary.json`. Reproduce the snapshot with `/usr/bin/python3 script_diff_llm2/analysis/reliability_v6_grading_20261005/analyze.py` from the finance repository root.

## Completed coverage and headline result

Only `gpt_oss_120b/without_context/reliability_v6_01` currently has all 1,000 grader rows. Its raw run also contains all 1,000 questions. Six grading timeouts remain unresolved, so row coverage is complete but final judgments are not complete for every question.

| Saved status | Count | Share of 1,000 |
|---|---:|---:|
| MATCH | 784 | 78.4% |
| PARTIAL | 108 | 10.8% |
| MISMATCH | 101 | 10.1% |
| PRE_SCAN_ERROR | 1 | 0.1% |
| GRADER_API_ERROR | 6 | 0.6% |

The unchanged GPT-5 Mini grader uses `strict_v1` policy for all rows. Excluding its six API failures gives 784/994 = **78.87%**, while the benchmark-wide saved match rate remains **78.4%**. Retrying only those six failures could raise the saved match count to at most 790, or 79.0%, if all six become matches. It cannot alone achieve 80%.

The raw pipeline executed successfully for **933 questions (93.3%)**. The execution/grade breakdown is:

| Execution outcome | MATCH | PARTIAL | MISMATCH | Pre-scan error | Grader API error |
|---|---:|---:|---:|---:|---:|
| Successful execution | 784 | 108 | 35 | 0 | 6 |
| Execution failed | 0 | 0 | 66 | 1 | 0 |

Thus 67 cases are execution failures, while 143 successfully executed cases receive PARTIAL or MISMATCH judgments. Among successful executions with a resolved judgment, 784/927 = **84.57%** are matches. These denominators answer different questions and must not be substituted for the 1,000-question benchmark score.

## Where performance is weakest

### Benchmark sheet

Each sheet has 125 questions.

| Sheet | MATCH | PARTIAL | MISMATCH | Other | Match rate |
|---|---:|---:|---:|---:|---:|
| General benchmark | 115 | 4 | 6 | 0 | 92.0% |
| At-risk / critical | 101 | 10 | 13 | 1 | 80.8% |
| Batch status | 113 | 0 | 9 | 3 | 90.4% |
| Enrichment / context | 102 | 10 | 13 | 0 | 81.6% |
| Multi-step comparative | 49 | 44 | 32 | 0 | **39.2%** |
| Reference / compliance | 96 | 27 | 1 | 1 | 76.8% |
| Scoring / quantitative | 102 | 10 | 11 | 2 | 81.6% |
| Temporal / transaction | 106 | 3 | 16 | 0 | 84.8% |

The multi-step comparative sheet accounts for **76 of the 209 PARTIAL/MISMATCH rows**, approximately 36.4%, despite containing only 12.5% of the questions. This is the dominant concentration of remaining problems. Outside that sheet, the saved match rate is 735/875 = 84.0%.

### Difficulty and query type

Difficulty match rates are Easy 72/82 = 87.8%, Medium 307/361 = 85.0%, Hard 245/306 = 80.1%, Advanced 101/124 = 81.5%, and Expert 59/127 = **46.5%**. The degradation is concentrated at Expert difficulty rather than increasing uniformly through every difficulty label.

Direct Retrieval has 34/34 matches; Multi-Relational 197/212 = 92.9%; Ranking 58/65 = 89.2%; Exception Detection 48/53 = 90.6%. Comparative has only 5/15 = 33.3%, and Multi-step Comparative 13/55 = **23.6%**. Sheet and query-type classifications are different groupings; their counts should not be interchanged.

## Evidence-backed failure mechanisms

### 1. QuerySpec contracts account for nearly all execution failures

There are **66 QuerySpec contract failures** and one SQL pre-scan failure. Sixty-four contract failures occur at Q1, one at Q2, and one at Q3. This is primarily a specification/grounding problem rather than a database availability problem.

Examples in node diagnostics include unknown physical sources such as `investor`, unresolved named metrics, malformed specifications, invalid aggregate-filter references, derived expressions referring to physical columns as aliases, and missing output contracts. Some failures are legitimate refusals of unsupported definitions; others are unnecessary ambiguity declarations or malformed representations of explicit questions.

For example, `ARC125-1T-014` asks for shortfall exceeding a supplied numerical threshold, but the model treats the adjective “severe” as an additional undefined condition. Blocking every such case preserves caution at the cost of rejecting a question whose explicit comparison can be implemented. Any future repair should preserve explicit numerical conditions without inventing a separate severity rule.

An unresolved named composite score without an independently provided definition is different: the generic pipeline should not acquire a formula from benchmark answers merely to remove the failure. The error audit must distinguish model contract mistakes from missing source semantics.

### 2. Attribute ownership and unwanted extra predicates alter populations

`WM125-2T-026` asks for average goal progress among investors whose **stated goal** is Retirement Planning, averaging per investor first. Generated SQL filters both `InvestorProfile.investment_goal` and each `InvestmentGoal.investment_goal`. The second predicate is not requested and changes the observations included in each investor's average.

The saved answer is **18.052175**, versus reference **41.34**. A read-only diagnostic calculation selecting the stated-goal cohort from the profile alone, then averaging each investor's goals, returns **41.341819**, consistent with the question and reference. This verifies a source-ownership/extra-filter defect rather than an arithmetic rounding issue.

The same source label can occur on profile and event/detail tables with different ownership. Identical field names do not justify applying a literal to every source. This remains an important weakness even though SQL and KG contain the same underlying records.

### 3. Cash-flow signs are being reinterpreted during generation

Several generated queries use a category-based CASE expression or subtract sums of stored withdrawal values. Since source amounts are already signed, these transformations can turn outflows into positive inflows or subtract negatives twice.

Verified examples:

| Question | Saved behavior | Read-only source check |
|---|---|---|
| TT125-004: negative net cash flow during 2024 | CASE-based re-signing yields no rows | Grouped SUM of stored amount finds 212 negative-net entities. |
| TT125-059: signed net transaction amount through Cheque | 101,669,776 | SUM of source amount is **-98,895,230**, matching reference. |
| TT125-088: Large Cap cohort net cash flow during 2025 | Inflow-minus-outflow calculation and required participation in both branches yield 145,867 | Cohort SUM of source amount is **100,407,459**, matching reference. |

The last example also excludes investors who have only one transaction category branch, so population and sign errors coexist. These diagnostic calculations are analysis evidence, not runtime query templates or benchmark-derived rules installed in the pipeline.

Questions asking explicitly for a magnitude, net signed sum, or category-based sign transform must remain distinct. The proposed generic correction is stronger preservation of the question/source-defined expression through specification and generation, not unconditional assumptions based on financial wording.

### 4. Grain, grouping, normalization, and population remain difficult

The weak comparative groups involve entity summaries, final grouped metrics, several source populations, formula dependencies, and filter stages. A query can execute yet average the wrong observations or combine different eligible populations. The detailed `nonmatches.csv` preserves all reported discrepancies for review.

Do not interpret 933 successful executions as evidence that these computations are correct. The 108 PARTIAL and 35 successful-execution MISMATCH cases show the remaining semantic gap. Conversely, not every numerical disagreement establishes a pipeline defect until the question, source semantics, and reference calculation are checked.

### 5. Duplicate entity rows and output identity

Several PARTIAL judgments explicitly identify duplicate investors in membership/list queries, including `WM125-3T-023`, `WM125-3T-026`, and `WM125-4T-007`. Model-generated multi-source joins can repeat an entity when several child rows meet the conditions. A one-source compiler's distinct projection does not cover arbitrary generated joins.

Some portfolio questions instead return portfolio-health UUIDs where the reference requires investor identities and score values, including `ARC125-1T-009`, `ARC125-1T-011`, and `ARC125-1T-012`. UUIDs are not intrinsically wrong: the defect is selecting an output identity or projection that does not meet the intended answer contract. Question ambiguity and reference assumptions still deserve review.

The SQL→KG audit established intact source records and verified identity relationships. These failures concern how the model projects and uses those identities, not missing source keys in the KG.

### 6. Some large-list judgments are inconsistent with full saved rows

The original grader truncates answer and reference strings to 60,000 characters in its prompt. Several large-result PARTIAL cases have identical complete identifier multisets, despite reasons claiming missing or extra identifiers:

| Question | Matching complete key count | Reference characters | Answer characters |
|---|---:|---:|---:|
| ARC125-1T-013 | 4,013 goal IDs | 404,547 | 339,184 |
| ARC125-1T-015 | 2,420 goal IDs | 234,216 | 260,742 |
| ARC125-1T-016 | 2,665 goal IDs | 262,309 | 291,480 |
| ARC125-1T-019 | 656 holding IDs | 90,179 | 102,691 |

Equal identifier multisets refute those particular missing/extra-key claims but do not prove all requested attributes match. They are evidence for further grading review, not automatic relabeling.

More decisively, **RC125-118 and RC125-122 have identical complete row multisets** between answer and reference, differing only in order, with 573 rows each. The grader labels both PARTIAL and says the answer is incomplete. These are apparent grading errors; neither exceeds the 60,000-character bound, so truncation does not explain all grading discrepancies.

The saved CSV and official match rate remain unchanged. The audit records discrepancies separately in `identity_checks.csv`; it does not award additional matches or revise grader policy.

## Context and comparison limits

The GPT-OSS with-context grader is still incomplete. At this analysis snapshot it contains 165 rows: 150 MATCH, nine MISMATCH, six PARTIAL. Its 90.9% prefix match rate must not be compared with the complete 78.4% score: the prefix covers a different difficulty/category mix and execution order.

The current GPT-OSS context state contains **four active terminology entries**, with no active computational definitions. The Phase 0 business-rules document is quarantined as evaluation-scoped. This is therefore a terminology-context condition, not an ablation applying the full financial rule document. Claims that the current run tests all business rules would be inaccurate.

No current reliability v6 DeepSeek, Gemma, or Kimi grader CSV is complete at this snapshot. Their raw completion does not establish a graded score. Likewise, the earlier approximately 81% score used another grader and another raw generation run; a direct accuracy-regression claim would confound both changes.

## Recommended order of work

1. Finish GPT-5 Mini grading for the planned conditions and retry the six timeouts without concurrent writers to the same graded CSV.
2. Compare conditions on the same 1,000 row IDs using the same grader. Retain raw execution failures and grader failures as separate outcomes.
3. In a new revision/run tag, address unnecessary unresolved requirements, exact source ownership, duplicate entity output, and preservation of specified signs and aggregate stages.
4. For named metrics requiring business definitions, use independently authored, reviewed source context. Do not convert evaluation corrections into inference rules.
5. Keep a separate audit of large-result grading discrepancies. Do not change the grader or saved labels during this comparison.

These observations support targeted changes after current runs finish. They do not establish that any untested change will achieve a particular match percentage.

## Artifacts

- `summary.json`: counts, execution/grade cross-tabulation, sheet/difficulty/query-type breakdowns, input hashes, and snapshot time.
- `nonmatches.csv`: every non-MATCH row from completed grading coverage, with question, status, stage, and grader reason.
- `identity_checks.csv`: full saved identifier comparisons and exact row-multiset checks for parsable structured nonmatches.
- `analyze.py`: reproducible snapshot analysis without model calls or output mutations.
