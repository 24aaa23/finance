# Completed v5 raw and graded run

**Update after retrying the four grader API errors:** all four now receive MATCH. The final recorded result is **811/1,000 MATCH (81.1%)**, 61 PARTIAL, 126 MISMATCH and two PRE_SCAN_ERROR, with zero grader API errors. Exactly those four grade statuses changed; raw answers and traces remain unchanged. The affected questions are WM125-1T-003, ARC125-1T-004, SQA125-3T-002 and SQA125-3T-004. Refreshed `summary.json`, `row_diagnostics.csv`, `nonmatches.json` and `full_result_checks.json` reflect the final grades. `summary_before_grader_retry.json` preserves the initial summary. The following audit narrative describes the original 807-match snapshot; its pipeline-error diagnoses remain applicable.

The latest v5 reports contain 1,000 unique, identical sample IDs and consistently record `generic-contract-recovery-v5`. Every graded row preserves its raw question, reference, generated answer, trace and version. Questions and references are identical to v2/v4. The grader records `strict_v1`, `grader_2` and `gpt-5.6-terra` throughout. Both logs confirm completion.

This audit creates analysis artifacts only. Pipeline code, grader, source assets and all saved reports remain unchanged. Read-only SQL/RDF probes below diagnose errors; their expressions and reference comparisons are not fed into runtime prompts or rules.

## The measured 80% target is reached

| Measurement | v2 | v4 | v5 |
|---|---:|---:|---:|
| MATCH | 721 / 72.1% | 646 / 64.6% | **807 / 80.7%** |
| PARTIAL | 57 | 44 | 61 |
| MISMATCH | 215 | 303 | 126 |
| Grader API errors | 2 | 0 | 4 |
| Other grades | 1 | 2 | 0 |
| Raw successful executions | 825 | 717 | **912** |
| QuerySpec contract failures | 167 | 269 | **85** |
| Other DAG failures | 4 bindings | 9 bindings | 1 model-context exception |
| Pre-scan errors | 2 | 5 | 2 |
| Scan errors | 2 | 0 | 0 |

The denominator is the full 1,000 questions; API errors and partials are not counted as matches. MATCH+PARTIAL is 86.8%, which is a different metric. V5 improves MATCH by 16.1 percentage points over v4 and 8.6 points over v2. This is a result on the already inspected benchmark, not an independent unseen-query generalization result.

## What produced the improvement

Against v4, 598 prior matches survive, 209 prior non-matches become MATCH, and 48 prior matches become non-matches. The net gain is 161. Against v2, 671 prior matches survive, 136 non-matches become MATCH and 50 old matches are lost, giving a net gain of 86.

235 previously failed v4 raw questions now execute successfully: 190 MATCH, 25 PARTIAL, 19 MISMATCH and one grader API error. Conversely, 40 prior v4 raw successes no longer execute successfully. This explains the net raw-success increase of 195.

On the 677 questions that execute successfully in both v4 and v5, MATCH rises only from 614 to 617. Thus the strongest evidence is **restored execution coverage**, rather than a large improvement in answer semantics among unchanged successful executions. Against v2, the shared-success subset contains 771 questions and improves from 687 to 704 matches.

The contract failure count drops by 184 from v4. The original physical-source token and owning-aggregate alias/stage clusters are absent from the detected v5 contract errors. V5 records structural repairs on 866 questions, totaling 1,796 records; this includes ordinary derived operand typing, so it must not be interpreted as 866 formerly failed questions or as a causal ablation.

The v4-to-v5 48 lost matches consist of 30 contract failures, one pre-scan failure, one context exception and 16 completed raw executions that did not receive MATCH. Those 16 include three grader API errors, eight partials and five executed mismatches. Improvements remain stochastic and there are still regressions to inspect.

## Performance by question family

Each family has 125 questions.

| Family | v2 MATCH | v4 MATCH | v5 MATCH | v5 accuracy | v5 PARTIAL |
|---|---:|---:|---:|---:|---:|
| General | 111 | 110 | 121 | 96.8% | 0 |
| At-risk/critical | 107 | 76 | 111 | 88.8% | 1 |
| Batch/cohort | 108 | 105 | 115 | 92.0% | 0 |
| Enrichment/context | 83 | 83 | 99 | 79.2% | 5 |
| Multi-step comparative | 39 | 36 | **42** | **33.6%** | **38** |
| Reference/compliance | 94 | 77 | 106 | 84.8% | 10 |
| Scoring/quantitative | 92 | 84 | 109 | 87.2% | 6 |
| Temporal/transaction | 87 | 75 | 104 | 83.2% | 1 |

Every family improves, but multi-step comparative remains the clear bottleneck: 44 mismatches, 38 partials and one pre-scan failure. Its 83 non-matches account for 43.0% of all 193 non-matches; 38 of 61 partials come from this family. Adding business rules indiscriminately would not fix its generic grain, NULL-join, expression and binding issues.

## Remaining failures before answering

85 questions fail QuerySpec contracts. Detected overlapping row incidences include 40 unresolved requirements, 14 derived measures without expressions, seven empty/missing output schemas, six unknown sources, five unknown bases, six invalid alias operands, five unparsed specifications, three failed measure recoveries and one missing consumer output.

Unresolved requirements are concentrated in comparative questions (23), temporal questions (seven), at-risk questions (four), cohort questions (four) and reference questions (two). Text-based overlapping subclusters include 20 sign/net-definition uncertainties, four field-comparison cases, four band/cohort cases, two invented zero-usage enumeration requirements, one gain/return-definition case and one component-eligibility case.

Not every unresolved clause represents missing business knowledge:

- ARC125-4T-002/025 and ARC125-5T-016/019 say a comparison such as current value versus cost cannot be represented. The runtime already supports `value_type: field`; the model is failing to use the available representation. Related cases supply nested comparison objects instead of the required field-name string. This is an interface/capability communication problem.
- Several cohort questions already state a numerical threshold, yet the model also demands a separate definition of the descriptive band. Distinguish a descriptive label accompanying an explicit criterion from a genuinely undefined additional criterion.
- RC125-044/047 invent a requirement to return zero-count categories, although the questions ask which values are actually in use. The pipeline must not silently treat an invented requirement as user intent.
- Composite normalization plans sometimes reference population min/max aliases that were never declared or emit placeholder derived measures without expressions. Population statistics need an explicit typed representation, rather than guessed alias names.

Other unresolved requests genuinely require source-authored metric definitions or clearer questions. A generic pipeline should preserve these uncertainties rather than embed benchmark-specific sign/category/formula rules.

The two pre-scan failures are different:

- **RC125-002:** validator oscillation. A correct `NOT IN` query is first rejected because it excludes NULL; the revised `OR ... IS NULL` query is then rejected for widening the population; the final plain `NOT IN` is rejected again. A read-only SELECT using the plain predicate returns zero rows, exactly matching the full reference. This is validator inconsistency, not a missing source rule.
- **MC125-045:** malformed SQL-generation JSON, not an aggregate semantics rejection. All three attempts record an unterminated string, no SQL is recovered, and pre-scan consequently reports `No SQL provided`. The upstream KG node succeeds, but the bound multi-stage workflow fails to complete.

The remaining DAG exception is **SQA125-1T-010**: the provider rejects input length 136,094 tokens against a 131,072-token limit. The unnecessarily decomposed first node emits 4,600 goal rows before the second node fails. The saved exception does not retain the complete rejected request, so it cannot establish exactly which payload component caused the expansion.

## Executed wrong answers and partials

Of 126 MISMATCH grades, 86 are failed DAGs and **40 are wrong answers after successful raw execution**. There are also 61 executed partials. Important recurring mechanisms are supported by saved queries and read-only probes:

### Attribute ownership and population filters

EC125-2T-029 groups the holding table's `segment` instead of the investor profile's segment. A diagnostic profile-to-holding join produces all 65 reference groups and counts exactly. EC125-3T-010 tests the profile's stated Growth goal instead of existence of a Growth goal record; a goal-record EXISTS condition gives the exact four reference counts. Similar source-owner mistakes recur across enrichment questions.

WM125-2T-027 correctly filters investor profiles to Wealth Preservation, but additionally restricts the goals being averaged to Wealth Preservation. The question asks for all goal progress of that investor cohort, averaging within each investor first. Removing the additional goal-record filter gives 38.785979..., which rounds to the reference 38.79, versus the saved answer 17.646831....

### Metric definitions, units and grain

EC125-2T-018 uses stored `returns_pct` and returns 40.0; the reference is 50.0. The diagnostic valid-cost/current-value return expression gives 50.0. Several other cases compute a decimal ratio where the reference uses percentage units, or average stored return fields where the reference recomputes returns. These observations identify reference semantics, not a justification for hardcoding a universal return formula. Obtain a source definition or an explicit formula in the question.

MC125-004 averages sector rows directly rather than computing investor totals first. MC125-038 uses AVG of rebalance amounts within investors where the evaluated metric uses a different entity aggregation. Comparable grain differences recur in holdings, cash amounts, dividends and shortfalls. Grain must be explicit per measure; similarly worded metrics may require different row/entity/group operations.

TT125-053 wraps stored amounts in a type-based sign CASE and reports 801,574,168 instead of 914,448. The direct signed SUM returns the exact reference. This demonstrates double interpretation of an already signed measure. TT125-068 instead returns the negative stored Withdrawal sum where the reference uses a positive total magnitude. Consistent units/sign definitions must come from the source contract; adding an ungrounded cash-type mapping to a generic prompt would recreate the earlier problem.

### NULLs, projections and distinctness

MC125-028 joins grouped nullable dimensions with `=`, losing the NULL group's metrics. RC125-007 adds `OR sector IS NULL` to a set non-membership check and returns 755 rows instead of zero. RC125-075 returns a NULL identifier as a referential-integrity violation. Several reference coverage partials contain an extra NULL group, while SQA125-1T-007 incorrectly omits a required NULL group. There is no safe universal “always include” or “always exclude” NULL rule: the contract must distinguish missingness, set membership and grouped population semantics.

RC125-059 emits 1,473 per-investor rows instead of three distinct risk values. SQA125-1T-015 aggregates goals by their label and returns only seven category representatives, instead of ranking individual goal records. Row identity and category labels are different grains.

BSQ125-1T-011 filters progress below 30 but omits the underfunded criterion, returning 2,420 rows versus 2,251. A diagnostic predicate including positive shortfall exactly matches all reference goal/shortfall pairs. This explains the extra records; it is not an RDF identifier-normalization issue.

### Confirmed RDF population loss from extra mandatory fields

SQA125-1T-008 requires `rdfs:label` even though the question only requests the goals above a volatility threshold. It returns 323 of 336 required goal IDs. A minimal read-only RDF query removing the unrequested label returns exactly all 336 IDs.

TT125-020 makes notes, labels, source metadata and relationship properties mandatory while selecting qualifying transactions. It returns 105 of 120 reference transactions. A minimal typed query retaining the actual date/type/amount predicates returns exactly the 120 required investor/date/amount rows as a multiset. Unrequested display metadata must not restrict eligibility; use OPTIONAL when such fields are useful, or omit them.

### Composite ranking and reference precision

Several composite cases have incorrect component populations or signs. **MC125-095 is a separate precision-contract issue:** the saved query sorts precise scores correctly, but the reference rounds three scores to 82.05 and orders those entries by investor ID. Actual saved scores are INV-661: 82.049194536..., INV-541: 82.046855775..., INV-1541: 82.046679901.... These are not equal before rounding. The question does not explicitly state that ranking happens after two-decimal rounding. The PARTIAL ordering penalty therefore reflects an ambiguous evaluation precision convention; blindly rounding all ranking metrics to imitate the reference would be inappropriate.

## Grading artifacts must stay separate

All four grader API failures occur after successful raw execution: WM125-1T-003, ARC125-1T-004, SQA125-3T-002 and SQA125-3T-004. Three are request timeouts and one is a connection error. The first answer exactly equals the reference JSON; the other three have exactly the reference investor-ID sets. ID agreement alone does not establish every metric/projection requirement, so their saved grades remain API errors. The recorded accuracy remains 80.7%.

**ARC125-1T-013 has a demonstrably misleading PARTIAL reason.** It alleges extra underfunded goals, particularly GOAL-prefixed IDs. The full saved answer and reference each contain the same 4,013 goal IDs, with zero extra or missing IDs, including the same 998 GOAL-prefixed IDs. Answer text is 339,184 characters and reference text is 404,547 characters. The unchanged grader truncates each input to 60,000 characters; different row orders/widths expose different subsets. Truncation is the likely cause of the false extra-record conclusion. No saved grade is changed, and excluding GOAL-prefixed IDs to satisfy that reason would damage the correct answer.

Other large-result cases examined are genuinely problematic: BSQ125-1T-011 lacks a predicate; ARC125-1T-018 returns category averages instead of records; RC125-059 lacks DISTINCT; RC125-007/074 widen NULL populations. Large input alone does not invalidate a grade.

## What the decomposition evidence supports

994 questions use one node; five use two nodes and one uses three. None of the six multi-node runs achieves MATCH: four MISMATCH, one PARTIAL and one PRE_SCAN_ERROR. V5 avoids the old binding-failure label, but that does not establish that mixed-backend decomposition works reliably. Context expansion, malformed generated queries, incompatible source/output representations and wrong intermediate grain still matter.

The 80.7% result validates this implementation's aggregate benchmark outcome. It does not isolate a decomposition benefit: nearly all questions are single-node executions. A decomposition ablation and independently held-out questions are needed for the paper's stronger architectural/generalization claims.

## Runtime cost and next priorities

Raw wall time is 151.89 minutes, with mean per-question elapsed time 36.38 seconds, median 23.06 seconds, p95 57.33 seconds and p99 626.17 seconds. Sixteen questions exceed 300 seconds and consume 10,284.77 seconds, or 28.3% of cumulative query time. Compared with v4's mean 33.06 seconds, broader successful execution has not made the average query faster. Long-tail request/repair budgets and oversized bound contexts deserve attention.

Recommended order of further work:

1. Preserve this completed v5 baseline. Resume the unchanged grader to retry its four API failures; do not rerun raw generation merely for those failures.
2. Correct generic interface failures: explicit field-to-field comparison examples/normalization, valid structured response recovery, stored-field classification and declared population-statistic operands. Keep ambiguous source/metric definitions explicit.
3. Enforce the question's source ownership, output grain and required predicates. Separate shared population restrictions from metric-local restrictions; make unrequested RDF attributes nonrestricting.
4. Encode NULL and unit/precision decisions in the computation contract, based on question/source evidence. Do not infer global policies from the reference answers.
5. Bound multi-node payloads and avoid splitting a single-source aggregation into full-row retrieval followed by another model step. Pass typed references or compact intermediate aggregates rather than duplicating entire row lists.
6. Supply optional independently authored metric/identity metadata where needed. Do not turn this audit's counterfactual queries into benchmark-derived production rules.

No further pipeline/grader modifications or paid calls were made during this audit. Evidence: `analyze.py`, `summary.json`, `row_diagnostics.csv`, `nonmatches.json`, `replay_checks.py`, `read_only_replays.json`, `large_result_checks.py` and `full_result_checks.json`. The previous `analysis/generic_no_rules_v5` directory remains the pre-run implementation/revalidation record, not the measured v5 run audit.
