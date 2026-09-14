# V4 review and implementation plan

Planning only. Production pipeline files were not changed. The review uses the latest three saved reports, their debug CSVs, the 442-question reference workbook, current V4 source, and offline tests. Supporting scripts and review documents live only in this review directory.

## Verified result and limits

| Same question subset | Earlier result supplied by user | Latest saved V4 MATCH |
|---|---:|---:|
| Success — 55 | 35 | 29 |
| Part 1 — 69 | 34 | 27 |
| Part 2 — 68 | 1 | 1 |
| Total — 192 | 70 (36.46%) | 57 (29.69%) |

The decline is 13 answers, or 6.77 percentage points. The earlier column is the user's supplied baseline; the latest V4 column is verified from saved grades. This establishes a result difference, not a causal attribution to an individual commit.

All 192 IDs are unique, have debug evidence, and match the workbook's question and ground-truth text. Execution succeeded for 189; there are two FinalSpec errors and one decomposition error. Saved grades are 57 MATCH, 75 PARTIAL, 55 MISMATCH, 2 OTHER, and 3 skipped execution failures.

The 76 comparative questions have 3 MATCH, 36 PARTIAL, 35 MISMATCH, and 2 execution failures. MC-105 is an empty MATCH with an incorrect plan. Therefore “all comparative questions are wrong” is not the literal saved outcome, but its three matches also need semantic scrutiny.

Current inference files agree with the three latest inference manifests. The current grader file differs from its saved hash. No live graph replay or new model calls were made. Debug traces include samples rather than all underlying scan rows; some nested model-response excerpts are truncated even when the containing CSV fields are complete. Numerical root causes below are supported by SQL/plan divergence, not a new execution against the entire source database.

## What is already implemented

V4 already preserves nullable selected fields through OPTIONAL, carries RDF datatype information, retains declared connection keys, uses strict relational operators, and passes raw branch rows to one final planner. The existing 156 offline tests pass. The remaining failures arise because a valid executable plan can still select the wrong property, put a predicate in the wrong scope, calculate the wrong metric, or join the wrong population. Adding OPTIONAL everywhere or changing every join to left is not a valid general fix.

Additional offline reproduction used the actual pre_scan_validate function and a two-record local RDF graph. The correct outer filter returned one record; moving that filter inside OPTIONAL returned both records; a malformed expanded class URI returned zero; selecting an unbound field returned rows without that field. Current pre-scan validation accepted all four queries. These examples isolate the pre-scan guard only, not a complete pipeline replay. See reproduce_query_gaps.py and query_gap_reproductions.json.

## P0 — Make evaluation trustworthy

Six workbook answer cells are exactly 32,767 characters and end mid-JSON: BSQ-2T-006, WM-1T-008, WM-1T-009, WM-2T-011, WM-2T-017, and BSQ-3T-009. Their saved report strings exactly reproduce this truncation. Restore full reference SQL outputs into JSON/CSV artifacts outside Excel cells; store an artifact path, row count, and hash in the workbook. Mark incomplete references explicitly instead of grading a prefix. Some affected rows are currently marked MATCH.

Replace broad semantic-only grading with deterministic comparison of declared group keys, required columns, entity sets, counts, rounded numerics, nulls, and ranking. Counts must be exact; use metric-specific numeric tolerance rather than a universal absolute 1.5. Do not send truncated head/tail arrays to a model as if complete. Keep semantic alias judgement optional and inspectable. BSQ-1T-007's omitted null row was waived by the grader; MC-035's wrong weighting can fit within tolerance. WM-1T-019 needs tie-aware top-k evaluation because the reference lacks a secondary ordering key.

Separate execution status, plan validation, semantic review, and answer grade. Preserve the original 57/192 baseline and publish corrected evaluation under a new version. Record inference source, grader source, input cohort, and graph snapshot separately. Fix the external grade_v4_3_files_terra.py wrapper so --latest combination uses selected latest files.

Acceptance: every reference parses fully or is explicitly ungradable; exact group/count mismatches cannot receive MATCH; full arrays are compared without prompt truncation; old and new grading protocols are not mixed.

## P1 — Ground source meaning and preserve the question contract

Targets: schema_loader.py, retrieve.py, decompose.py, connections.py, query_spec.py, query_spec_validate.py, spec_contracts.py.

Use source descriptions, property ownership, entity ranges, and categorical values when choosing fields. Conservative/Aggressive/Moderate belong to risk tolerance in these references; Long-term belongs to time horizon; Gold is an investment type; Automated Trigger/Manual Override/Tactical are rebalancing logic values. Several empty answers come from confusing these concepts with category, asset, action, or scenario. MC-076 invents InvestorProfile; MC-025 omits the Investor connector.

Build a schema path resolver that expands the retrieved shortlist when a required connection is missing. Repair attempts must see the newly needed class. Maintain original question requirements independently from model-generated branch wording, so repairing an incorrect requirement does not merely enforce it more strongly.

Extend requirements to cover each output metric's source, expression, unit, inner grouping/aggregate, outer grouping/aggregate, row predicates, post-aggregate predicates, required participant population, null policy, and ranking. Reject extra invented filters as well as missing ones. Validate operator/value shape and datatype; cross-branch strings such as an IN value of q2.investorId are not executable literal lists.

Some reference semantics are absent from question wording: MC band boundaries, comparative inner/outer aggregation choices, health eligibility, type-dependent cash sign formulas, and TT-063 shortfall aggregation. Record these as explicit benchmark definitions or clarify the dataset questions. Do not claim a general system should infer hidden SQL perfectly or feed ground truth into inference.

Acceptance: named source-confusion regressions resolve to their intended properties; missing connectors are repaired; no unsupported classes, numeric comparisons on category labels, invented literals, or missing requested metrics pass the contract.

## P2 — Enforce QuerySpec-to-SPARQL fidelity

Targets: generate.py, pre_scan_validate.py, utils.py, scan.py, refine.py.

Prefer a deterministic renderer for the supported raw retrieval contract. The model chooses a typed contract; code renders class/field bindings, OPTIONAL blocks, and predicates. A model fallback must pass the same structural equivalence checks.

Current pre-scan checks validate syntax, selected names and prohibited aggregation, but do not establish predicate scope or property origin. TT-039 and TT-061 put timeToGoalMonths <=12 inside OPTIONAL and still retrieve all 4,865 goals. BSQ-3T-003 similarly retains non-underfunded goals. WM-3T-013 leaves both date predicates inside OPTIONAL, admitting all years. Move row predicates to the appropriate scope; simply detecting the word FILTER is insufficient.

Resolve all prefixes and full IRIs before checking class/property ownership. MC-064 declares a prefix ending in TimeHorizon, then uses th:TimeHorizon, expanding to TimeHorizonTimeHorizon and returning zero rows. The wm:-only term regex misses such alternate-prefix errors. Check that selected variables are actually bound to the declared properties, optionality matches intent, and no undeclared graph path changes the candidate population.

Avoid projecting multiple multivalued reverse fact relations into the Investor branch; MC-064's investor scan expands to 101,104 rows. Record one-to-many relationships in metadata and retrieve facts independently.

Acceptance: malformed expanded URI, filtered OPTIONAL without row exclusion, missing predicate, changed literal, unbound projection and undeclared mandatory relation fixtures all fail before a service call. Valid nullable retrieval and explicit row exclusion continue to pass.

## P3 — Compile and validate the intended calculation

Targets: final_spec.py, spec_contracts.py, spec_runtime.py, connections.py, relational.py. Detailed comparative work is in MULTISTEP_COMPARATIVE_PLAN.md.

Propagate column origin, entity/composite grain and metric lineage through each step. Give display fields explicit source aliases before joins. MC-039 groups on investor names instead of category; BSQ-2T-010 copies cash type into category. MC-016 joins unrelated record identifiers. WM-1T-005 creates aliases on separate branches instead of chaining them. Existing runtime collision suffixing is useful, but cannot decide which source the model intended.

Summarize independent facts before joining whenever required by the metric. Verify key uniqueness at each summary and expected join cardinality. Differentiate raw AVG from AVG(per-investor AVG), SUM holdings per investor from AVG holdings per investor, and MAX concentration from AVG/SUM allocation. Require each requested comparison output and eligibility condition to reach the final result; an unused optional dimension is not the same as an omitted required health population.

Acceptance: unequal fact-count fixtures expose weighted means and multiplication; source-label collisions are rejected; invalid record-key joins fail; MC-030/083 use holding SUM and allocation MAX where specified; omitted delta/health/goal metrics cannot compile as complete answers.

## P4 — Nulls, conditional metrics, filters and ranking

Targets: final_spec.py, filter_aggregate.py, math_compute.py, bucket.py, order_by.py, relational.py.

Separate four concepts: missing label, missing metric input, no qualifying conditional rows, and missing required fact participation. Attach labels from the preserved fact/profile side with left joins. Keep required fact joins inner when the contract requires shared participation. Join null aggregate group keys with null-safe equality only where the grouping scopes match; normal null investor keys must not join.

Require is_not_null instead of != null, as in WM-2T-011. Add explicit conditional/default expression support for CASE-style sums and risk buckets. Preserve subtraction null propagation; coalescing either allocation input to zero changes the result. Define outflow sign per metric, since the reference collection uses more than one cash-flow convention.

Place HAVING-style predicates after complete aggregation. WM-4T-007 filters raw progress before AVG; WM-3T-016 and MC-105 push aggregate conditions onto raw rows. Fix metric formulas and candidate population before sorting; MC-104's top ten is wrong because concentration is SUM instead of MAX.

Acceptance: fixtures cover absent dimension, all-null metric, no qualifying conditional rows, unequal participation, null group merges, exact bucket boundaries, cutoff ties, and a nonempty witness for MC-105 and TT-065.

## P5 — Focus repairs and preserve diagnostic evidence

Targets: executor.py, main.py, reporting.py, validate.py, refine.py.

Repair the earliest responsible stage: source/path error to Retrieve/Decompose, field/filter error to QuerySpec, query translation error to Generate, metric/join error to FinalSpec. Reuse unchanged successful scans when their contracts and snapshot match. Preserve the failing final plan and all attempts before an early return.

Record per intermediate step: source/requirement IDs, columns and origin, row count, distinct identity count, null counts, key multiplicity, join cardinality, rejected predicates, and metric coverage. Keep complete query/spec artifacts alongside compact report summaries. Do not mistake last-branch scan summaries or sampled rows for complete execution evidence.

Acceptance: the three current execution failures have inspectable responsible-stage evidence; a final-plan repair does not unnecessarily requery unaffected branches; an empty result can be traced to a valid predicate or a contract failure.

## Verification order

1. Preserve existing 156 passing tests and add focused offline fixtures for the failures above. Compare operator plans against equivalent local SQL on the same small synthetic records; do not only test implementation-shaped expected outputs.
2. Exercise actual query rendering and validation with a small RDF graph, including alternate prefixes and OPTIONAL scope. Existing tests/support.py stubs term validation, so the current suite is not end-to-end source-fidelity verification.
3. Run a diagnostic subset covering source confusion, predicate scope, aliases, composite joins, two-level metrics, null eligibility and top-k. Avoid assuming all regressions share one cause.
4. Run the fixed 192 IDs against a fixed graph snapshot and complete reference artifacts. Publish per-question transitions, comparative versus other performance, execution errors, and evaluator version. Do not claim an expected accuracy gain before measurement.

## Deliverables

- MULTISTEP_COMPARATIVE_PLAN.md: separate implementation plan and all 76 comparative findings.
- QUESTION_REVIEW.csv: all 192 questions with saved grade, individual finding/change, reference SQL and report source.
- QUESTION_DETAILS.md: per-question retrieval contracts, executed SPARQL and final-step evidence.
- SOURCE_REVIEW.md: inventory and change disposition for every V4 Python file, plus the external grading wrapper.
- evidence.json and audit_saved.py: reproducible offline evidence inventory and hashes.

Recommended first implementation batch: P0 reference/grade validation plus P2 query-fidelity guards, followed by P1/P3 metric contracts. This addresses demonstrable mechanical failures before measuring larger comparative planning changes.
