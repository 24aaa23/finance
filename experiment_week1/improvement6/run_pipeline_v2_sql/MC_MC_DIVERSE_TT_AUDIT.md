# Improvement5 v2: MC, MC_diverse and TT audit

Audit date: 2026-09-27. Statistics snapshot: 02:34:55 local time.

## Main conclusion

The business-rule pack is connected to v2, but putting rules in prompts does not ensure that generated plans obey them. The failures have several distinct causes: incorrect source/aggregation choices, contradictory comparison filters, missing or extra NULL groups, incomplete domain coverage, and some reference SQL that disagrees with the new rules.

This audit reviewed saved outputs and execution traces, checked source code, ran the existing offline tests, and reproduced selected calculations against the local SQLite database. No pipeline code, benchmark answers, or existing results were changed. No paid model runs were started.

## Results at the snapshot

| Dataset | Source questions | Saved raw results | Graded | Match | Partial | Mismatch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MC | 105 | 87 | 78 | 18 (23.08%) | 38 (48.72%) | 22 (28.21%) |
| MC_diverse | 70 | 70 | 70 | 13 (18.57%) | 40 (57.14%) | 17 (24.29%) |
| TT | 65 | 65 | 65 | 32 (49.23%) | 18 (27.69%) | 15 (23.08%) |

MC raw and graded files changed during this audit. Its figures are a snapshot, not a completed-run result. The run manifest also records query_limit=100, so the current window does not include all 105 MC questions. Use a new output/manifest when changing the window; the runner intentionally rejects resumes with a different run identity.

Comparison on exactly the same graded question IDs:

| Dataset | v1 match | v2 match | Change |
| --- | ---: | ---: | ---: |
| MC, same 78 questions | 18/78 (23.08%) | 18/78 (23.08%) | 0.00 percentage points |
| MC_diverse | 10/70 (14.29%) | 13/70 (18.57%) | +4.29 percentage points |
| TT | 34/65 (52.31%) | 32/65 (49.23%) | -3.08 percentage points |

This is an observed comparison, not proof that the added rules caused every changed answer. Decompose uses temperature 0.2, and this is not a repeated controlled ablation.

## Confirmed findings

### 1. High priority: comparison alternatives become impossible AND conditions

MC-229 asks for the difference between Short-term and Medium-term investors. Its saved SPARQL contains both:

```sparql
FILTER(?timeHorizon = "Short-term")
FILTER(?timeHorizon = "Medium-term")
```

One investor cannot satisfy both. The profile scan returns zero rows and the final difference becomes NULL. MC-230 has the same problem with Conservative and Aggressive. The saved decomposition also assigns incompatible equalities to one branch for MC-226 and MC-231; MC-231 ultimately stops with a Query_Spec error.

The error starts in Decompose's predicate list. Query_Spec's preservation checks can then insist on retaining both erroneous predicates. See [decompose.py](llm_operators/decompose.py), [query_spec.py](llm_operators/query_spec.py), and [query_spec_validate.py](llm_operators/query_spec_validate.py).

Required correction: represent the compared populations with an IN/OR condition or separate branches. Validate contradictory equalities before generating a query, and route an invalid decomposition back to Decompose rather than preserving it as authoritative.

### 2. High priority: MC plans use the wrong aggregation and sometimes the wrong source

MC-005 should average each investor's goal metrics first, then average those investor summaries by risk tolerance (R5). Its plan instead joins raw goals to profiles and averages all goal rows directly.

Independent SQLite calculations reproduce both answers. For Conservative investors:

- Reference per-investor average shortfall: 23,686,380.49.
- Pipeline shortfall: 22,066,148.55.
- A raw-row pooled AVG reproduces the pipeline value.

Other confirmed examples:

| Question | Saved plan | Required reference calculation |
| --- | --- | --- |
| MC-006 | Holding-category totals | Profile-category average of per-investor holding totals |
| MC-010 | Per-investor AVG(action amount); gap from ScenarioRebalancing | Per-investor SUM(action amount); gap from RebalancingAction target minus current allocation |
| MC-023 | SUM of investor totals/counts across a risk group | AVG of those investor totals/counts |
| MC-268 | Average of investor-level shortfall/progress ratios | Ratio of the group average shortfall to group average progress |

MC-005 and MC-268 show definite calculation mistakes. Some older MC wording, such as "Across category, how do holding value and holding gain compare", does not specify the source owner or averaging explicitly even though the reference does. Those questions need an explicit, public definition; the planner should not need access to reference SQL to infer it.

The planner has general guidance but the executable compiler checks fields/operators rather than enforcing R5 or source-specific metric definitions. See [final_spec.py](llm_operators/final_spec.py) and [spec_runtime.py](spec_runtime.py).

Required correction: carry a structured metric contract with source, operands, inner aggregation, outer aggregation, group owner, population, and NULL policy. Validate that the executable plan implements that contract.

### 3. High priority: TT-026 discards every row using an invalid NULL-presence test

TT-026 successfully calculates 62 month groups, including one NULL month. Its final filter is `month != null`. Under the runtime's SQL-style NULL semantics, every comparison is unknown, and every row is removed.

An offline reproduction using the actual compiler, executor, and filter operator confirmed:

| Filter | Result | Compile/execution error |
| --- | --- | --- |
| `month != null` | Empty list | None |
| `month is_not_null` | Both dated example rows retained | None |

MC-022 also contains a comparison to literal NULL in its saved final plan.

The SQL-style runtime behavior is intentional; the missing protection is a planner-contract check that rejects this as an attempted presence test. See [spec_runtime.py](spec_runtime.py) and [filter_aggregate.py](llm_operators/filter_aggregate.py).

Required correction: require explicit is_null/is_not_null operations and repair invalid generated presence tests before executing them.

### 4. High impact: NULL-group policy differs across benchmarks and is not made explicit

For MC_diverse, grader explanations identify extra NULL-group rows as the principal issue in 31 of its 40 PARTIAL answers. This count is based on reviewing the grader explanations, not on regrading modified answers.

Example MC-244: all three named risk groups have correct denominators and shares. The pipeline adds a fourth NULL-risk group. Reference SQL explicitly excludes NULL risk labels, but the question wording does not state that exclusion.

MC-201 computes valid per-investor return averages but ranks the NULL-risk group first at 93.46. The reference excludes that group and returns Moderate at 86.03. Running the SQL with and without the NULL-label exclusion confirms this difference. The saved plan incorrectly assumes ORDER BY/LIMIT will exclude a NULL label even though the numeric score is non-NULL.

In TT, the opposite policy is often required. TT-002 must include the missing-type group: 391 transactions and net amount 947,448. Its raw cash-flow scan retrieves all 7,828 rows, but an INNER JOIN to the eight named CashFlowType labels removes the missing-type transactions. Similar missing-group errors appear in TT-003, TT-006, TT-011, TT-042, TT-054, and others.

There are also split NULL groups: MC-023 independently groups two sources and outer-joins their labels with nulls_equal=false, producing two incomplete NULL rows.

Required correction: distinguish a missing metric from a missing group label. Specify whether unnamed groups belong in each question, preserve nullable labels through LEFT JOIN when required, and merge equivalent aggregate NULL groups explicitly. A blanket "remove every NULL group" fix would improve some MC_diverse grades while breaking MC and TT.

### 5. High priority for evaluation: at least one reference disagrees with the new rules

TT-043 groups by investor risk tolerance. R5 says averaged metrics must be calculated per investor first; R6 supports preserving optional child metrics through LEFT JOIN.

The pipeline follows that approach. The reference SQL instead computes SUM(per-investor sums)/SUM(row counts) and requires investors to have both action and scenario records through INNER JOINs. These differ in both weighting and population. Its COUNT(*) denominator also includes records with missing operands.

For Moderate investors:

| Metric | Saved reference | Pipeline and independent R5/R6 SQL |
| --- | ---: | ---: |
| Average action allocation gap | -2.12 | -1.76026856 |
| Average scenario allocation change | -1.07 | 0.06820878 |

The independent R5/R6 query reproduces the pipeline result across all groups. Therefore this MISMATCH cannot honestly be described only as a pipeline formula error.

TT-059 also uses row-count-weighted averages in its reference while the saved plan uses investor averages. R5's stated scope is investor-attribute grouping, so its extension to month/scenario grouping should be specified explicitly rather than assumed.

Required correction: agree on weighting, eligibility, and missing-value denominators; make the questions, business rules, reference SQL, and regenerated ground truth consistent. Keep old reference versions for comparison. Do not silently change the pipeline to violate the ratified rules just to match a conflicting reference.

### 6. Medium priority: full domain knowledge was not integrated

[business_context.py](business_context.py) opens only business_rule_pack.json. The two paths under source_documents are provenance strings; the loader does not read either document at runtime.

The pack is a manually condensed subset. One directly relevant omission is the goal_match_pct bands from [domain_intro_latest.prompt](../domain_intro_latest.prompt): below 60, 60 to below 80, and at least 80. MC-002 invents 0-20/20-40/40-60/60-80/80-100 bands, and its assumptions confirm the invented definition.

Other incomplete coverage includes the full R8.0 operand-to-source definitions and R8.2 normalization details, including complete-component population handling and the constant-component case. Many domain validation rules are also not represented. Their applicability to benchmark analytics must be decided before adding automatic exclusions.

Required correction: inventory the domain definitions needed by these questions, encode them with exact source/field mappings and boundaries, and test coverage. Do not assume naming the source documents imports their contents.

### 7. Medium priority: semantic review was disabled and is not a repair gate

All three run manifests contain final_semantic_review=0. Successful raw rows show Answer Review Status=not_requested.

[validate.py](llm_operators/validate.py) returns after execution/shape checks when review is disabled. [executor.py](executor.py) records semantic acceptance/rejection separately; even enabling review does not currently trigger automatic semantic-plan repair. PIPELINE_SUCCESS means execution completed, not that the answer is correct.

The raw Query_Spec_Validate stage exists, but its prompt does not directly include the shared business-rule pack. It did not prevent the comparison-predicate failures shown above.

Required correction: add deterministic checks for known contract failures. Enable semantic review for a focused diagnostic run; if automatic repair is desired, implement and test it explicitly rather than assuming the flag performs repair.

### 8. Additional source and join mistakes

- TT-012 uses Investor.investmentGoal. Reference SQL uses distinct investor/goal pairs from InvestmentGoal, a different population definition.
- TT-055 joins hasTriggeredAction to hasRebalancingDecision, two different identity domains. The trace reports zero matched keys and zero result rows.
- TT-051 and TT-064 stop because actual duplicate join keys violate the plan's declared cardinality. Those guards are catching invalid plans; suppressing the checks would risk fan-out and incorrect totals.
- MC-009, MC-086, and TT-021 stop after Query_Spec changes a branch's assigned source class.

Required correction: bind each requested metric/group to its owning source and validate relationship targets and cardinality before execution.

### 9. Reproducibility gap: the run identity omits the rule-pack contents

[run_identity.py](run_identity.py) hashes Python source files; main.py adds the question CSV, schema and KG files. It does not hash business_rule_pack.json or the resolved BUSINESS_RULE_PACK_FILE override.

Changing rules without changing Python could therefore evade resume identity checks. The present Python files match the hashes in all three run manifests, but those manifests cannot prove the exact JSON pack used at run time. This is a provenance risk, not evidence that a mixed-rule run already occurred.

Required correction: include the resolved rule-pack path and content hash in the run identity. Include additional prompt documents if the runtime starts reading them.

## Verification and limits

- All 184 existing v2 tests passed. Their mocked grader error messages are test fixtures, not live API failures.
- Selected reference SQL for MC-005, MC-201, MC-244, TT-002, and TT-043 was executed read-only against wealth_management_diverse.db and reproduced the stored ground truth.
- Alternative calculations reproduced MC-005's pooled average, MC-201's NULL-group winner, and TT-043's R5/R6-compliant result.
- An offline runtime reproduction confirmed that a literal NULL comparison can return an empty answer with no execution error.
- At the alignment check, saved graded answers matched the corresponding raw answers; MC had additional ungraded rows. The files continued updating afterward.
- TT-057 and TT-063 both grade MATCH. TT-057 changed from non-MATCH in v1 to MATCH in v2. The rule-pack addition is not uniformly harmful.
- Existing tests exercise operator/runtime behavior, but no dedicated business-rule-pack coverage tests were found.
- The grader uses a universal absolute numeric tolerance of 1.5. That is unsuitable as a universal rule for counts, 0-1 shares, percentages and currency. It is a separate evaluation-quality issue, not the demonstrated cause of the failures above.

## Recommended order

Implementation follow-up: the direct grader now has a reviewed MC_diverse-only exception for harmless extra unnamed groups. See [grader changes and pipeline plan](GRADER_NULL_POLICY_AND_PIPELINE_PLAN.md). The pipeline fixes below remain recommendations, and the audit statistics above are the original strict-grading snapshot.

1. Reconcile benchmark definitions: especially TT-043, unnamed-group inclusion, and vague MC metrics. Do this before judging rule compliance by match percentage.
2. Add domain definitions missing from the compact pack, plus structured metric/source/population contracts.
3. Reject contradictory comparison predicates and invalid NULL-presence tests; validate joins, aggregation grain, ratios, and output completeness.
4. Record the rule-pack hash and add focused regression cases from the confirmed failures, with expected results independently derived from agreed rules.
5. Run a small diagnostic set into new output files: MC-002, MC-005, MC-010, MC-022, MC-201, MC-229, MC-244, MC-268, TT-002, TT-026, TT-043, TT-055, and TT-059. Review exact values as well as grader labels before a full rerun.

## Evidence files

Each saved CSV can be joined by Sample Row ID; question IDs in this report are the suffix after the colon. Use a CSV parser because fields contain JSON and embedded newlines.

- [MC graded](../pipeline_output_v2/graded/MC_v2_graded.csv), [MC execution traces](../pipeline_output_v2/MC_v2_debug.csv), [MC questions and reference SQL](../dataset/MC.csv).
- [MC_diverse graded](../pipeline_output_v2/graded/MC_diverse_v2_graded.csv), [MC_diverse execution traces](../pipeline_output_v2/MC_diverse_v2_debug.csv), [MC_diverse questions and reference SQL](../dataset/MC_diverse.csv).
- [TT graded](../pipeline_output_v2/graded/TT_v2_graded.csv), [TT execution traces](../pipeline_output_v2/TT_v2_debug.csv), [TT questions and reference SQL](../dataset/TT.csv).
- [Business rules](../business_rules_addendum.md), [domain document](../domain_intro_latest.prompt), [runtime rule pack](business_rule_pack.json).
