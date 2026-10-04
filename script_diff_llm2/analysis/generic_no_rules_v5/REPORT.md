# Paired v2/v4 audit and implemented v5

Both raw reports and both graded reports contain 1,000 unique sample IDs. Raw and graded questions, references, traces and versions agree within each run. The same IDs, questions and references occur across v2/v4. The unchanged grader records the same policy/model settings. Revalidation independently checks those invariants and saves SHA256 hashes of all four reports in `summary.json`.

## Observed results

| Measurement | v2 | v4 |
|---|---:|---:|
| MATCH | 721 / 72.1% | 646 / 64.6% |
| PARTIAL | 57 | 44 |
| MISMATCH | 215 | 303 |
| Raw successful executions | 825 | 717 |
| QuerySpec contract failures | 167 | 269 |
| Binding failures | 4 | 9 |
| Scan errors | 2 | 0 |
| Pre-scan errors | 2 | 5 |

V2 additionally has two grader API errors and one OTHER; v4 has two OTHER. PARTIAL is not MATCH. There is no completed v3 benchmark, so this is a combined v3/v4 versus v2 comparison.

545 v2 matches survive. V4 loses 176 prior matches and gains 101 prior non-matches, giving a net loss of 75. Of the 176 losses, 151 fail the contract, three fail bindings, four fail pre-scan validation and 18 execute but do not match. Of v4's 303 mismatches, 278 are DAG failures; 25 are executed wrong answers. The principal regression is therefore coverage lost at the plan interface.

The execution changes are not uniformly harmful: among 628 questions with successful raw executions in both versions, v2 has 563 matches and v4 has 574. V4 fixes some aggregation thresholds, source value grounding, date literals and SQL scan defects. Retaining those improvements while repairing the plan interface is better supported by the evidence than a wholesale v2 rollback.

V4 family match counts out of 125 are: general 110, at-risk 76, batch 105, enrichment 83, multi-step comparative 36, reference/compliance 77, scoring 84, temporal 75. At-risk and reference/compliance account for 48 of the 75 net lost matches. Multi-step comparative remains weak in both versions; v4 has 29 of its 44 partials in that family.

## Why plans fail

V4's overlapping original contract clusters include 79 questions using `physical` as a source, 53 with aggregate predicate alias syntax rejected, 11 missing aggregate stages and 15 with unsupported operand-kind spellings. Their union covers 150 questions, including 90 prior v2 matches. Other failures include logical source labels, physical formulas confused with aggregate aliases, duplicated projection aliases and real unresolved definitions.

For example, WM125-2T-028 supplies a valid holding base table but labels its filter and count source `physical`. WM125-4T-016 explicitly supplies an owning aggregate alias under `output_name`, while the validator expects `field`. WM125-4T-018 nests the predicate inside its owning count measure without repeating the alias or stage. These are representations the runtime can normalize when the physical owner and aggregation level are unambiguous.

Some apparently similar cases cannot be repaired mechanically. A field shared by several declared sources does not identify its owner. A threshold under a measure with both entity and final-group aggregation does not identify its stage. A named financial metric without a question/source definition does not identify a formula. V5 leaves these cases visible for model repair or as explicit unresolved requirements.

Four v4 RDF queries were rejected because the projected literal identifier was considered untyped, despite correctly typed carrier subjects. The earlier exact read-only replays for RC125-089/092/103/107 return the reference identifier sets. V5 clarifies this distinction and supplies parsed mandatory-carrier evidence. It does not bypass semantic validation merely because some typed triple exists. The separate SQA125-2T-018 AVG-grain rejection is not treated as the same error.

## V5 changes

1. **Normalize supported syntax before contract validation.** `spec_normalization.py` resolves physical placeholders using operand ownership, binds logical source labels only when all references identify one owner, and binds a logical base using explicit entity-key projection or distinct-count ownership. A shared foreign key alone is insufficient.
2. **Separate physical row formulas from aggregate-alias formulas.** Operand names resolve against the declared schema or already planned aliases. Row formulas mislabeled derived are repaired only with unique physical ownership. Legacy final-group alias expressions carrying a physical source label are normalized when all operands are independent aliases, not physical columns.
3. **Normalize aggregate predicates conservatively.** An omitted alias or an explicitly matching `output_name` can resolve to its owning measure. Missing stage resolves only with one aggregation level. Explicit conflicting aliases, scopes and stages are not rewritten.
4. **Preserve projection provenance.** An identical plain physical projection duplicated in grouping and measures is consolidated; requirement references and later measure indices are updated. Distinct computations sharing one alias remain errors.
5. **Improve model contracts and repair.** The template drops redundant operand_kind; the runtime derives it. Prompts distinguish stored attributes from requested aggregates, entity totals from raw-row averages, and explicitly requested magnitude from signed values. A corrected stored-field classification can exit unnecessary measure recovery. Candidate repair recomputes validator diagnostics rather than inheriting stale errors.
6. **Connect decomposition outputs to QuerySpec.** Upstream subqueries receive the output names/types their consumers require. Missing output names trigger repair before execution. This addresses a missing interface; it does not invent cross-backend identity mappings or coerce categories into identifiers.
7. **Correct RDF carrier validation.** Parsed evidence is scoped to direct projected variables with mandatory typed carriers. OPTIONAL, UNION, subquery boundaries and negative expressions do not establish those bindings. Generation and validation agree that identifier literals are not typed subjects, and an unnecessary profile join must not change eligibility.

Existing schema text-domain profiling, SQL read-only preparation, datatype checks and bounded scan repair are retained. The grader, outputs and source assets are unchanged. No question IDs, answer-derived formulas or financial category mappings were added to runtime prompts or normalization.

## Offline revalidation of every saved plan

This uses the actual read-only SQL schema and Fuseki metadata. References and grades are used only to compare reports, never as normalization inputs. Previous validator diagnostics are removed from private copies and recomputed. It performs no new generation, answer execution or grading.

| Saved-plan contract outcome | v2 | v4 |
|---|---:|---:|
| Previously clear, still clear | 833 | 731 |
| Previously blocked, now clear | 76 | 155 |
| Previously blocked, still blocked | 91 | 114 |
| Previously clear, newly blocked | 0 | 0 |

The clear category includes questions with later execution/binding failures; it is not raw success. V5 recovers 57.6% of v4's contract-blocked questions (155/269). All 155 had a v4 MISMATCH grade. In v2, those same questions had 101 MATCH, 39 MISMATCH, 14 PARTIAL and one SCAN_ERROR. Earlier matches establish that many recovered questions were answerable; they do not prove the v5 answer will match.

Recovered v4 contract failures by family: general 10, at-risk 33, batch 13, enrichment 15, comparative 14, reference/compliance 24, scoring 18, temporal 28. Recovery is distributed across all eight families, rather than based on a family-specific rewrite.

The 114 still-blocked questions include overlapping incidences of 48 unresolved requirements, 39 unknown sources, 23 derived measures lacking expressions, eight alias-operand failures, seven unknown physical fields, three population-filter failures and three missing output schemas. The detailed old/new errors and repair evidence for every node are saved in `plan_diagnostics.json`.

## Remaining answer semantics and the 80% target

V4's 25 executed mismatches and 44 partials require more than permissive validation. The detailed v4 audit identifies requested attribute ownership, stored versus computed ratios, per-entity versus raw-row averages, positive magnitudes versus signed amounts, nullable grouped joins, missing-member/null semantics and composite populations/ranking as recurring issues. Extra RDF identifier representations and missing cross-backend mappings also affect entity-set comparisons. Source-authored metric and identity definitions may resolve genuine ambiguity; schema profiling cannot infer their business meaning reliably.

To reach 80% from v4's 646 matches requires **154 net additional matches** while retaining the current ones. Recovering 155 blocked contracts does not establish 155 correct answers: downstream generation, execution and grading may still fail. Likewise prompt changes can change previously successful behavior. No measured v5 accuracy exists yet, and neither 80% nor a flaw-free pipeline can be promised from offline tests.

A fresh full v5 raw run and unchanged grading are necessary to measure the target. Compare paired gains/losses and failure stages, not just the headline score. Since v5 was developed after inspecting this benchmark, a separate untouched evaluation set is needed for a credible claim about unseen-query generalization.

## Verification and running

The unit suite passes 128 active tests with 37 historical skips. Ten regression tests and one integration test also pass: **139 active passing tests**. New tests use synthetic schemas/data and fake model replies, including ambiguous ownership, conflicting/two-stage predicates, row-formula execution without integer truncation, stale diagnostics, required downstream outputs, stored-field classification, duplicate-projection provenance and RDF scope boundaries. The launcher passes Bash syntax checks; repository diff whitespace checks pass.

Run instructions: [generic_pipeline_v5_run.md](../../docs/generic_pipeline_v5_run.md). The launcher runs raw generation and then the unchanged grader, uses a fresh v5 report folder, disables the optional rules catalog and supports resuming either stage.

Evidence files: `summary.json`, `plan_diagnostics.json`, `revalidate.py`. The earlier exhaustive execution/answer diagnosis and exact RDF replays are retained in [the v4 audit](../generic_no_rules_v4/REPORT.md); [the v2 audit](../generic_no_rules_v2_20261003/REPORT.md) documents the preceding failure patterns.
