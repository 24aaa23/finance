# Latest raw and graded run: generic no-rules v4

The latest run is `outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v4`. Both reports contain 1,000 unique and identical sample IDs; every row uses `generic-grounding-repair-v4`. The graded answers, question strings, references, node traces and versions exactly match the raw report. Questions and references are unchanged from v2. Grading uses the same recorded `strict_v1` policy, `grader_2` label and `gpt-5.6-terra` model. There are no grader API exceptions in this run.

Only analysis artifacts were created. Pipeline code, grader, saved outputs and databases were not changed during this audit. Reference answers are used for offline diagnosis only.

## Main result: the latest revision regressed

| Metric | v2 | v4 | Change |
|---|---:|---:|---:|
| MATCH | 721 (72.1%) | 646 (64.6%) | -75 / -7.5 percentage points |
| PARTIAL | 57 | 44 | -13 |
| MISMATCH | 215 | 303 | +88 |
| Successful raw executions | 825 | 717 | -108 |
| Query_Spec contract failures | 167 | 269 | +102 |
| Binding failures | 4 | 9 | +5 |
| Scan errors | 2 | 0 | -2 |
| Pre-scan errors | 2 | 5 | +3 |

V4 additionally has 2 OTHER grades, both caused by truncated grading inputs. MATCH + PARTIAL is 69.0%, but PARTIAL must not count as a match. There is no completed v3 benchmark here, so the comparison measures the combined v3/v4 changes relative to v2; it cannot isolate the last v4 edits alone.

Paired grades: 545 v2 matches remain matches; 176 v2 matches become non-matches; 101 prior non-matches become matches. Net change: 101 - 176 = -75. Of the 176 lost matches, 151 fail the Query_Spec contract, 3 fail binding, 4 fail pre-scan and 18 execute but receive another grade.

Among 303 mismatches, 278 are failed DAG executions and only 25 are wrong answers after successful execution. Thus 91.7% of mismatches come from blocked plans/bindings. The raw-success-to-MATCH rate increases from 721/825 = 87.4% to 646/717 = 90.1%, but those populations differ. On the 628 questions that successfully execute in both revisions, matches increase from 563 to 574. This narrower comparison supports some execution/semantic improvement while exposing a larger loss of execution coverage.

## The principal regression is the plan interface

Incidences below overlap:

| Contract failure pattern | v4 rows | Previously MATCH in v2 |
|---|---:|---:|
| `physical` used as a source name | 79 | 45 |
| Aggregate predicate does not name its owning alias using the expected key | 53 | 38 |
| Missing aggregate predicate stage | 11 | 6 |
| Unsupported operand-kind spelling | 15 | 5 |
| Any unknown source/base label | 131 | 74 |
| Explicit unresolved requirements | 48 | 22 |
| Derived measure lacks an expression | 29 | 15 |
| Formula operands misclassified as aggregate aliases | 24 | 1 |

The first four interface clusters cover **150 distinct questions, including 90 former matches**. They are not proof that all those plans would answer correctly if accepted, but many contain readily identifiable structural defects rather than missing financial knowledge.

### Operand labels are being confused with actual sources

WM125-2T-028 declares a real holding base table but gives both its filter and measure `source_class: physical`. ARC125-1T-012 declares the real health table but marks its score filters and projections `physical`. Runtime cleanup then adds that invalid label to required_classes, and validation stops execution.

The new `operand_kind` vocabulary appears to have increased confusion between operand categories and physical source identifiers. This is an inference from the saved plans and prompt changes, not an isolated causal experiment. More prompt instructions alone are unlikely to solve the interface problem. Prefer a smaller model-facing schema and derive redundant typing internally from validated source/operand bindings. If a reserved label appears in source_class, repair it only when an explicit valid source and every referenced field make ownership unambiguous; never use a dataset-specific name mapping or choose among multiple owners by convenience.

### Nested aggregate predicates are over-specified

WM125-4T-016 contains a COUNT measure named `rebalance_count` and an aggregate predicate with `output_name: rebalance_count`, stage `entity` and value `>= 1`. The validator requires the key `field`, so it rejects the plan even though the intended alias is explicit. WM125-4T-018 nests a threshold inside its owning count measure without repeating an alias key and is rejected for the same reason. WM125-4T-017 references valid owning aliases but omits stage.

Safe structural compatibility would accept an explicitly matching alias under an alternative key, or infer the alias from its enclosing measure when omitted. Stage can be derived only when exactly one aggregation level is possible; genuinely ambiguous two-level predicates must still be repaired or rejected. Do not simply convert all these errors to warnings: population versus metric scope still changes semantics.

### The earlier formula issue improved, but remains

V2 had 83 distinct rows with expression/operand stage failures; v4 has 44. That repair helped some cases, but the model now sometimes marks physical COUNT projections `source_class: derived` with no formula, or calls row arithmetic `operand_kind: derived` instead of an accepted physical/alias kind. ARC125-4T-001 shows physical operands `current_value` and `cost` inside a row CASE expression, yet declares a derived source. Normalization must distinguish row expressions over source columns from formulas over already computed aliases.

The increase in unresolved plans (48 versus 29) also needs clause-level review. Preserve true missing metric definitions; do not let newly complicated JSON requirements turn straightforward physical computations into artificial uncertainty.

## Four valid RDF queries are falsely rejected before execution

RC125-089, RC125-092, RC125-103 and RC125-107 all contain an explicit typed carrier subject and project its literal investor identifier. The validator rejects them on the grounds that the returned ID itself is not typed. Literal identifiers are not RDF subjects that should receive rdf:type; the relevant check is whether their carrier is typed and has the correct source/relationship semantics.

Read-only SELECT replays of the exact rejected queries confirm:

| Sample | Returned rows | Reference rows | Exact investor-ID set |
|---|---:|---:|---|
| RC125-089 | 180 | 180 | Yes |
| RC125-092 | 573 | 573 | Yes |
| RC125-103 | 573 | 573 | Yes |
| RC125-107 | 573 | 573 | Yes |

This is confirmed validator over-rejection. Clarify typed carrier versus projected literal; retain checks against untyped carrier subjects. The fifth pre-scan error, SQA125-2T-018, concerns entity-first AVG versus direct row AVG and requires separate grain/type review; it is not automatically another false positive.

## Improvements that should be retained

- SQA125-2T-014 now computes the per-investor mean over all eligible goal records and applies HAVING afterward. Its grade changes MISMATCH -> MATCH.
- TT125-072 remains a KG query and now uses typed xsd:date constants. It changes MISMATCH -> MATCH, supporting the metadata/date fix. TT125-084 also becomes MATCH, but switches to SQL; it is not an isolated demonstration of the RDF fix.
- WM125-3T-017 and WM125-5T-011 become MATCH. The first now selects the correct category field in SQL instead of filtering the investment-name field in KG; backend and model choices changed, so this cannot be attributed solely to RDF enum profiling.
- MC125-060 changes SCAN_ERROR -> MATCH. There are no SQL scan errors in v4. TT125-119, however, changes SCAN_ERROR -> a contract-blocked MISMATCH; absence of a scan error does not mean it was fixed.
- TT125-094 records one SQL scan-error repair and becomes MATCH. This is the one observed use of the new scan repair counter in the saved traces, not evidence that every repaired query uses that path.
- RC125-072 changes MISMATCH -> MATCH. Some prior null-membership mistakes are resolved, although other null cases remain.

These targeted benefits coexist with the much larger interface regression. A full rollback would discard demonstrated fixes. The preferred next change is smaller, compatible model output contracts while keeping the runtime groundwork.

## Remaining incorrect executed answers

The 25 executed mismatches and 44 partials still show:

1. **Dimension ownership:** EC125-2T-029 and EC125-2T-043 continue using holding dimensions where the reference uses investor-profile dimensions. Other EC counts show related eligibility/source errors.
2. **Stored versus computed return definitions:** EC125-2T-018/028 and several EC/MC partials disagree on return formulas. These definitions must be supplied by explicit question semantics or independent source metadata, not copied from reference answers.
3. **Wrong inner aggregation:** MC125-004/011/041/042 retain correct group/allocation outputs but use the wrong computation for average total investment. Rebalance amount and goal shortfall metrics have similar grain errors.
4. **Signed net flow versus magnitude:** TT125-029/068 return negative totals when the requested withdrawal magnitude is positive. TT125-053/083/096 and multiple MC cash metrics still disagree on signed-flow definitions.
5. **Null preservation/membership:** MC125-001/028/036/047/097 lose null-group metrics; RC125-074/076 include wrong extra records. Correct nullable aggregate joins and predicate semantics are still needed. Twelve RC partials from v2 shrink to two in v4, but several formerly partial queries now fail contracts, so this is not evidence of a general null-policy fix.
6. **Composite scoring and ranking:** MC125-056/057/058/082/085/109/112/115/120 contain correct components or investors alongside incorrect scores, eligibility or ordering. Verify the eligible normalization population, arithmetic types and tie-breaks together.
7. **RDF entity-set differences:** ARC125-1T-013 and BSQ125-1T-011 include extra GOAL-style identifiers; SQA125-1T-008 omits qualifying goals. Investigate instance/source identity semantics, not display-name guessing.

## Breakdown by question family

All families contain 125 questions:

| Family | v2 MATCH | v4 MATCH | Change |
|---|---:|---:|---:|
| General wealth management | 111 | 110 | -1 |
| At-risk/critical | 107 | 76 | -31 |
| Batch/status | 108 | 105 | -3 |
| Enrichment/context | 83 | 83 | 0 |
| Multi-step/comparative | 39 | 36 | -3 |
| Reference/compliance | 94 | 77 | -17 |
| Scoring/quantitative | 92 | 84 | -8 |
| Temporal/transaction | 87 | 75 | -12 |

At-risk and reference/compliance together lose 48 matches, accounting for 64% of the net 75-match decline. MC remains the weakest family: 36 MATCH, 29 PARTIAL and 60 MISMATCH. It contributes 29 of all 44 partials.

There are 989 single-node runs and 11 multi-node runs. Two multi-node/mixed-backend questions match (WM125-4T-004/006); the other nine fail binding. V2 had no matched multi-node execution. This is progress but far too little evidence for a general decomposition benefit. The run still overwhelmingly exercises the single-node workflow.

## Runtime and grader limitations

Mean per-question time is 33.06 seconds, median 22.52, p95 52.58 and p99 614.38. Twelve questions exceed 300 seconds and consume 7,617.08 seconds, about 23% of cumulative runtime. Mean latency is essentially unchanged from v2; the long tail remains. Wall time is roughly 152 minutes. More contract failures can shorten individual runs, so latency alone cannot establish efficiency improvement.

RC125-034 and RC125-061 are OTHER because grading inputs are truncated, not demonstrated semantic failures. There are no grader API errors. The same recorded grading policy and model support the paired comparison, but model stochasticity and simultaneous pipeline changes remain limitations.

## Next priorities

1. Simplify the model-facing Query_Spec and normalize redundant structural fields internally. Explicitly prevent operand labels being used as sources; bind only unambiguous real sources.
2. Support equivalent aggregate alias keys and owning-measure shorthand; derive stage only when structurally unambiguous. Retain semantic checks for threshold placement and population scope.
3. Correct the RDF typed-carrier validation rule. Keep datatype extraction, date checks, enum grounding and SQL preparation/repair.
4. Add synthetic end-to-end tests for the model's actual JSON variations, not only the one canonical representation. The prior passing tests did not establish robustness to these emitted formats.
5. Reevaluate on a fresh version after targeted fixes. Use independent metric/source metadata for business definitions and separate ablations for decomposition and grounding; do not restore benchmark-specific prompt mappings to improve this test score.

Artifacts: [summary.json](summary.json), [row_diagnostics.csv](row_diagnostics.csv), [read_only_replays.json](read_only_replays.json). Recompute statistics with `/usr/bin/python3 script_diff_llm2/analysis/generic_no_rules_v4/analyze.py`; reproduce the four live read-only RDF checks with `/usr/bin/python3 script_diff_llm2/analysis/generic_no_rules_v4/replay_kg.py` while the configured Fuseki dataset is running. Legacy summary keys containing v1/v2 refer to previous/latest here; the report explicitly identifies those as v2/v4.
