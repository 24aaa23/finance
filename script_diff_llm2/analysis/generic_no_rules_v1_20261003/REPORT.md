# Completed generic run audit — 3 October 2026

## Result and coverage

The raw and graded files each contain 1,000 rows with 1,000 unique matching Sample Row IDs. All raw rows use `generic-contract-fix-v1-20261003`. The grader log confirms completion. This is a full-run result, unlike the 865-row stopped grader from the preceding run.

| Grade | Rows | Percentage of all questions |
| --- | ---: | ---: |
| MATCH | 579 | 57.9% |
| PARTIAL | 45 | 4.5% |
| MISMATCH | 365 | 36.5% |
| OTHER | 5 | 0.5% |
| PRE_SCAN_ERROR | 4 | 0.4% |
| SCAN_ERROR | 1 | 0.1% |
| GRADER_API_ERROR | 1 | 0.1% |

Raw execution: 698 PIPELINE_SUCCESS, 297 DAG_NODE_ERROR, 4 PRE_SCAN_ERROR, and 1 SCAN_ERROR. Among the 698 successful executions, 579 grade MATCH, 45 PARTIAL, 69 MISMATCH, 4 OTHER, and 1 GRADER_API_ERROR. Thus 83.0% of successfully executed questions match. This conditional rate selects a different, easier subset than the older run and does not establish better overall reasoning.

296 of the 365 mismatches came from DAG failures. The other 69 executed successfully but returned wrong answers. There are 295 Query_Spec contract failures, 2 downstream binding failures, 4 pre-scan failures, and 1 scan failure. Raw execution errors are the largest remaining obstacle; successful execution itself does not establish semantic correctness.

## Paired comparison

The older completed rerun had 637 MATCH, 137 PARTIAL and 202 MISMATCH, with 24 other outcomes. It successfully executed 979 questions. The current run is lower by 58 MATCH questions, or 5.8 percentage points. All paired question texts and reference-answer texts are identical between these two saved reports; changed reference content does not explain the drop.

Of the older 637 MATCH questions, 437 remain MATCH, 180 become MISMATCH, 16 become PARTIAL, 3 become OTHER and 1 has a grader API error. Of the 180 MATCH-to-MISMATCH regressions, 169 are Query_Spec contract failures and 11 are successful but wrong answers. One additional formerly MATCH question fails the contract and grades OTHER. Conversely, 142 formerly non-MATCH questions are now MATCH: 76 old mismatches, 54 old partials, 10 old pre-scan failures, 1 old grader error and 1 old OTHER. The net is 142 gained minus 200 lost = -58.

Against the intervening failed raw run, successful executions increased from 411 to 698. Of its DAG failures, 342 now execute: 290 MATCH, 14 PARTIAL and 38 MISMATCH. However, 57 questions that previously executed now fail at DAG level. Regeneration is variable and several components changed, so these differences do not isolate any single fix. Never compare the old 865-row grader's prefix percentage with the current complete run as if both covered the same 1,000 questions.

## Where the remaining contract rejects plans

These are row-level incidences; categories overlap and must not be added together or treated as projected accuracy gains.

| Error family | Affected rows | Interpretation |
| --- | ---: | --- |
| Unknown source/base entity | 136 | 120 mention the logical source `investor`; multi-table plans remain ambiguous to current cleanup |
| Planned measure missing from final output | 70 | Intermediate calculations and final projections are conflated |
| Unsupported requirement vocabulary | 56 | Includes ordinary planning words such as count, distinct, identifier and normalize |
| Unknown physical field or formula operand | 35 | Includes actual wrong fields and derived aliases treated as physical operands |
| Invalid requirement path | 28 | Models use alias-based paths such as `measures.composite_score` instead of numeric list indexes |
| Explicit unresolved requirement | 25 | Mix of real missing business definitions and representation/schema limitations |
| Unsupported filter operator | 19 | Includes spelling variants such as `not_null` and `is not` |
| Empty output schema | 11 | Much reduced from the previous 146 empty-spec traces |
| Literal/quotation coverage | 10 | Some genuine misattributions, plus inferred numeric zero rejected for the word negative |
| Requirement without implementation | 5 | Annotation omission, not always a missing executable condition |

Examples:

- **WM125-2T-002:** exact profile and health tables, fields and predicates are present, but `base_entity='investor'` is rejected. Both tables carry `investor_id`, so the deliberately conservative unique-source cleanup cannot choose. The prompt's logical entity language and the validator's physical-source requirement need an explicit distinction.
- **WM125-2T-003:** the ledger says count/distinct for “How many”; the lexical checker rejects those words. **WM125-1T-004** rejects “string,” and other rows reject “identifier.” Lexical overlap is not a reliable semantic hallucination detector.
- **MC125-052:** a normalized composite requires component measures and min/max intermediates. Its alias-based requirement references and derived operands are rejected. Across composite questions the validator also demands hidden intermediate aliases in `output_schema`. A typed computation graph should distinguish physical columns, derived aliases, aggregate predicates and final projections.
- **ARC125-3T-001:** the model marks a supported null-check spelling as unresolved and also represents an aggregate predicate as a derived physical filter. This is partly a plan-language/prompt issue, not necessarily absent financial knowledge.

Warnings were present in 257 successful executions: 224 MATCH, 24 MISMATCH and 9 PARTIAL. This supports treating missing quotation links as visible diagnostics; it does not justify removing schema or meaning checks. Of the 295 contract failures, 170 were MATCH in the older run, making contract compatibility the first priority.

## Successful queries with wrong answers

### Wrong categorical field, value or owning source

**Gold holdings:** a read-only SQLite probe finds 1,028 rows with `investment_type='Gold'` and zero with `investment_name='Gold'`. Fourteen successful-but-MISMATCH plans explicitly use the latter filter in Query_Spec, with further failures in generated SPARQL or other categorical predicates. **WM125-3T-006** invents `investment_type='Bond'` plus a name pattern for Government Bond. **TT125-012** uses lowercase `deposit` when the data uses `Deposit`; **TT125-056** uses `DIVIDEND_REINVESTMENT` when the data uses `Dividend Reinvestment`. These mistakes call for source-scoped value lookup and schema descriptions, rather than a global financial mapping added to prompts.

**Dimension ownership:** **EC125-2T-029** groups by holdings.segment, while the reference's dimension is the investor profile's segment. Holdings and profile fields with the same name are not interchangeable. Read-only replay using profile.segment and holding.sector reproduces all 65 reference rows exactly. **EC125-2T-043** similarly matches all 78 reference rows when category comes from the profile. **EC125-3T-022** filters profile.investment_goal instead of qualifying records in the goal table; replay using goal-table Growth records matches all four reference rows exactly. These three diagnostic replays are evidence for source attribution, not runtime answer fixes.

### Financial metric meaning, units and aggregation population

**Stored field versus formula:** **SQA125-1T-016** averages `returns_pct`. For eligible Gold holdings, that stored-field average is 103.01075, while `AVG(100*(current_value-cost)/cost)` is 109.11162, matching the reference's 109.112. This shows those interpretations differ; the intended definition should come from independently verified source metadata. **EC125-4T-007** uses `(current_value-cost)/cost` without multiplying by 100, returning ratios where percentage units are expected.

**Zero-event entities:** **EC125-4T-003** preaggregates event counts, left joins them, and averages a nullable count. Investors with no rebalancing records are omitted from the average instead of contributing zero. A count's absence policy needs explicit representation; coalescing all financial measures to zero would introduce other errors.

**Per-entity totals versus averages:** **MC125-003** uses AVG(amount) within investor then AVG across investors for rebalance amount, whereas the reference uses a different amount definition; the count component also excludes zero-event entities. Many MC partials have correct groups and some correct measures but wrong inner operations, common population, count absence or formula units. Twenty-seven of the 45 partials are in this family. Rule metadata must state inner grain, outer grain, weighting, eligible population and missing-input behavior for each metric. There is no universally correct SUM/AVG choice for an ambiguous financial name.

**Cash-flow signs:** **TT125-061** computes `SUM(CASE WHEN type='inflow' THEN amount ELSE -amount END)`. There is no `inflow` enum in the database, so it negates the stored amounts. A read-only replay returns 101,046,869 for SUM(amount), matching the reference, versus -101,046,869 for the generated CASE. Similar sign inversions occur in TT125-065/067/069. Avoid inventing category values or signing a value twice; a source catalog should document storage and presentation conventions.

### SQL/SPARQL semantics and identity

**Typed dates:** **TT125-006** compares `xsd:date` values against untyped string constants and returns zero. A read-only Fuseki replay with typed date constants returns 502,078,427, exactly the reference total. **TT125-084** has the same date issue. Backend-specific type validation should detect this before a valid-looking zero reaches the final answer.

**Missing class scope:** **WM125-1T-032** matches `wm:investorId` without restricting subjects to the Investor class. The live KG has 29 subjects carrying that ID: one Investor plus holdings, cash flows, goals and other facts. This explains the extra optional-only rows; it is not evidence of 29 duplicate Investor records. Query compilation should preserve declared source-class scope.

**Explicit NULL semantics:** **RC125-072** asks for profile segment outside a listed set. Generated SQL adds `p.segment IS NULL OR ... NOT IN ...`, while Query_Spec only had `not_in`. The reference is empty; the extra NULL disjunct creates many unwanted holdings. Preserve the declared NULL treatment rather than guessing it at generation time.

**Missing/incorrect identity and extra rows:** ARC and BSQ partials include health IDs instead of requested investor identities, and goal sets with IDs/coverage that disagree with the SQL reference. Inspect source-declared identity and SQL/KG coverage before treating these as cosmetic aliases. Do not restore suffix-based guessing.

### Evaluation coverage limits

Four successful RC outputs grade OTHER because the unchanged grader truncates answer text above 60,000 characters. They are RC125-049, RC125-052, RC125-055 and RC125-061. Their complete entity sets were not evaluated by the model, so their correctness is undetermined. The fifth OTHER is a contract failure. One grader API error is separate from pipeline correctness. No grader modification was made.

## Performance and architecture

The raw log reports 9,360.19 seconds wall time (156 minutes), 36.05 seconds average cumulative time per question, and 36,052.83 cumulative question-seconds. Median is 22.354 seconds, p95 54.243 and p99 631.719. Eighteen questions exceed 300 seconds and account for 11,402.20 cumulative seconds, or 31.6% of total question time. The installed client SDK has a 600-second read timeout and two default retries; the current client builder does not configure either explicitly. The roughly 600-second tails are consistent with an API wait/retry, but current logs lack per-request timing and cannot prove the cause. Add operator/request timings and explicit bounded client settings before attributing the delay to SQL or the model's reasoning. Reducing retries blindly can harm completion.

993 questions execute one subquery node; seven execute two. SQL-only rows have 488/858 MATCH, KG-only 90/138 and mixed 1/4. These differently routed subsets are not controlled backend comparisons. This run does not isolate a decomposition advantage; the paper needs a same-question ablation with decomposition disabled and all other conditions fixed.

## Priorities for the next implementation

1. Repair generic contract compatibility: distinguish logical entity from exact physical base source, keep intermediate aliases separate from final output, resolve legitimate alias references, and normalize supported operator spellings. Preserve genuine unknown-field and unresolved-definition rejection.
2. Replace the lexical requirement-word gate with reliable coverage checks. Stylistic annotations should not prevent execution; added predicates and metric definitions need question/catalog evidence.
3. Ground source ownership and literals through schema descriptions, relationships and scoped enum/value lookup. Check computed formulas for units, alias dependencies and storage conventions. Use the source catalog for independently authored financial meanings.
4. Represent measure-scoped eligibility, zero-event counts, common population and aggregation grain explicitly; strengthen compilation/validation for supported plans. Fix generic SPARQL date typing, class restrictions and NULL predicate fidelity.
5. Instrument slow model calls and use an explicitly configured timeout/retry policy. Keep accuracy changes and throughput changes as separate experiments.

These are priorities, not promises that all affected rows will become MATCH. No category count should be added to the current score. A source rule catalog helps financial definitions but cannot repair plan parsing, alias resolution, date typing or rejected annotations. MCP would standardize access and would not fix these errors by itself.

## Artifacts and reproduction

`summary.json` contains counts, paired transitions, file hashes and read-only SQL replay evidence. `row_diagnostics.csv` contains all 1,000 rows with raw status, grade, previous grade, failures, warnings, queries and grader reasons. `kg_replay.json` records the read-only live Fuseki diagnostics. These files are offline analysis and are not loaded by the runtime pipeline.

Reproduce statistics and bounded SQLite diagnostics from the repository root:

```bash
/usr/bin/python3 script_diff_llm2/analysis/generic_no_rules_v1_20261003/analyze.py --replay-sql
```

The source database may change later; the replay evidence describes the current source and is not a claim that the run pinned a database snapshot. All changes in this analysis are under `script_diff_llm2/analysis/generic_no_rules_v1_20261003`. The pipeline, grader, saved output files and databases were not edited. This benchmark has been used for debugging and is development evidence; use a fresh source/domain-separated held-out set for final generalization claims.
