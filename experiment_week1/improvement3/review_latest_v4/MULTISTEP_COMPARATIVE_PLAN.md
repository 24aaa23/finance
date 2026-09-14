# Separate multi-step comparative change plan

The review covers all 192 saved questions, their debug traces, and their matching workbook questions/answer text. Findings compare saved retrieval contracts, executed SPARQL, final plans, row-count traces, and reference SQL. No live database replay or model rerun was performed. Stored scan samples do not prove every underlying value. Saved grades are preserved, not independently recertified. Some questions leave reference metric definitions or participation implicit; these are benchmark ambiguities, not permission to inject reference SQL into inference.

The latest saved grades are 57 MATCH, 75 PARTIAL, 55 MISMATCH, 2 OTHER, and 3 skipped execution failures. The comparative subset is 76 questions: 3 MATCH, 36 PARTIAL, 35 MISMATCH, and 2 execution failures. MC-105's empty MATCH has visibly incorrect plan semantics. All 192 question strings and ground-truth strings match the workbook; six reference cells contain truncated JSON. The three inference manifests match current inference sources; current grade_final_answers.py differs from the recorded hash. Keep inference and grader provenance separate.

## SQL-derived benchmark rules

The workbook SQL has now been analyzed separately for rows labeled `Multi-step Comparative`. See `MULTISTEP_SQL_RULEBOOK.md` and `multistep_sql_interpretation.csv`. This analysis is only for understanding how the benchmark author translated question text into computation. It should guide the semantic contract and validators; it should not inject per-question SQL or question IDs into inference.

The 56 SQL rows with `query_type = Multi-step Comparative` all use `WITH` CTEs, reduce fact/event sources to `investor_id`, and then group the final output by an investor-profile dimension: `risk_tolerance`, `time_horizon`, `category`, or `segment`. This confirms the main rule for this family: interlink the intent decomposition and execution decomposition through a SQL-style metric contract. V4 should require each requested metric to declare its source, formula, source grain, final grouping dimension, join eligibility, and filter scope before execution.

## Required planning structure

1. Resolve the grouping dimension's owner: Investor risk tolerance/category/segment/time horizon is not a similarly named holding property. Add necessary connector classes from the schema graph.
2. Create a metric contract before fetching raw fields: source, expression, units, row predicate, investor/composite grouping key, inner aggregate, outer aggregate, null/default semantics, and required participant population. Every requested output must link to that contract.
3. Retrieve raw facts independently, preserving their record identity. Avoid projecting multiple multivalued investor-to-fact relations into a single investor rowset; MC-064 expands to 101104 rows before final work.
4. Compute each metric at its intended level. Typical reference patterns are AVG goal progress/shortfall per investor, SUM holding value/gain/cash/rebalance amount, MAX allocation concentration, and AVG/MAX/SUM scenario delta as specified. These are not universal defaults: select them from an explicit contract.
5. Join those summaries on investor identity, or investor+sector/type where required. Validate key entity type, uniqueness, and cardinality. A rebalance record ID cannot substitute for investor identity.
6. Apply the required common investor population using fact joins/semijoins. Attach nullable dimension labels separately with left joins; changing every join to left would break MC-065/074.
7. Aggregate once over the final group. AVG(per-investor AVG) must not become raw AVG or sum/count over all records. Null group keys must survive; null-safe equality is appropriate only when merging aggregates of the same grouping scope.
8. Apply aggregate predicates, calculate scores, then sort/limit. Preserve exact formula units, sign conventions, null propagation, and ties. Project every required comparison metric.

## Implementation sequence and acceptance

- **C1: metric contract and typed source map.** Update decompose.py, final_spec.py, connections.py and spec_contracts.py. Start with MC-005/006/016/025/039/076. Accept only when ownership, join paths, all outputs, and two aggregation levels are explicit; invented classes and unrelated record joins are rejected.
- **C2: query fidelity.** Build deterministic raw QuerySpec-to-SPARQL rendering with expanded IRI and predicate-scope checks. MC-064 must address the actual TimeHorizon class and avoid investor row multiplication; MC-100 must not invent inflow/outflow type labels.
- **C3: comparative compiler.** Extend spec_runtime.py with column provenance, entity/composite grain, aggregation lineage, eligibility checks, and metric coverage. Preserve the existing relational operators. Test MC-030/039/055/083/104 with small unequal-fact-count fixtures.
- **C4: nulls and conditional metrics.** Distinguish missing dimension, missing metric input, missing fact participation, and CASE ELSE zero. Add conditional-expression/default bucket support. Test MC-004/027/029/065/074/093 and null inputs to scenario differences.
- **C5: rankings and semantic witnesses.** MC-104 needs the right concentration formula before top-ten ordering; MC-105 needs a nonempty positive fixture that exposes premature filters. Never accept empty answer agreement as proof of a correct plan.
- **C6: fixed-cohort evaluation.** First compare deterministic local fixtures against equivalent SQLite SQL; then run the same 76 comparative IDs and the remaining 116 controls on the same data snapshot. Show correct-to-wrong and wrong-to-correct transitions, not just totals. Keep repaired evaluation scores separate from the original 57/192.

## Per-question findings

All 76 comparative questions are listed, including the three saved matches. Each row describes the observed divergence and the proposed correction. Reference SQL and complete saved query/step evidence are in QUESTION_DETAILS.md and evidence.json.

| Question | Saved grade | Finding and planned change |
|---|---|---|
| MC-001 | MATCH | Saved MATCH; raw goal averages match this question's requested grouping. Preserve as a control. |
| MC-002 | MISMATCH | Risk bands use 20-point intervals instead of reference <33/<67/ELSE. Define boundaries and null/default behavior in the question contract; the question does not specify these thresholds. |
| MC-003 | MATCH | Saved MATCH; left label attachment preserves null investment-type group. Preserve as a control. |
| MC-004 | PARTIAL | Inner cash-type label join loses null group; filtered positive/negative subgroups need conditional-zero semantics. Preserve the base group and calculate sign-based components. |
| MC-005 | PARTIAL | Raw goal averages weight investors by number of goals; reference averages per-investor averages. Aggregate by investor first and retain null risk group. |
| MC-006 | MISMATCH | Uses holding category instead of Investor category and group totals instead of averages of investor totals. Resolve source ownership and use two aggregation levels. |
| MC-007 | PARTIAL | Uses totals, signed negative outflow, and omits net-flow metric. Define all cash components per investor, then average by horizon; retain null horizon. |
| MC-008 | PARTIAL | Inner Segment label join drops the null segment. Preserve health rows through optional label attachment. |
| MC-009 | MISMATCH | Uses holding category and raw holding/allocation joins. Resolve profile category; independently calculate investor holding totals and MAX allocation concentration before joining. |
| MC-010 | MISMATCH | Uses raw rebalancing amount/gap averages instead of required investor summaries. Separate per-investor calculations from risk-group averages and retain null risk. |
| MC-011 | MISMATCH | Groups by horizon plus scenario instead of horizon; misses average of investor maximum allocation change. Compute row delta, investor MAX, then group AVG. |
| MC-012 | PARTIAL | Joins raw goal and cash records, multiplying facts; omits goal-progress comparison. Aggregate with required investor/goal keys before joining. |
| MC-013 | PARTIAL | Omits holding-return metric and weights health through raw holding rows. Build holding summaries and health comparison separately; retain null investment type. |
| MC-014 | MISMATCH | Raw cash/rebalancing join multiplies facts; amount_right supplies only one requested metric. Summarize cash by investor/type and rebalancing by investor before combining. |
| MC-015 | MISMATCH | Raw goal/scenario join changes weights and misses scenario delta. Calculate independent investor summaries and then horizon comparison. |
| MC-016 | MISMATCH | Joins unrelated rebalanceId and scenarioRebalanceId, producing empty output. Use shared investor identity and preserve logic grouping; calculate each source's own allocation formula. |
| MC-017 | MISMATCH | Joins global sector aggregates, losing investor+sector eligibility. Summarize at investor+sector first and retain requested AVG versus SUM distinctions. |
| MC-018 | PARTIAL | Raw cash/scenario join multiplies facts and misses net cash flow. Build each investor metric first; retain nullable source groups. |
| MC-019 | PARTIAL | Independent group summaries do not establish the required shared investor population; goal weights and null-group merge also differ. Join investor summaries before group aggregation. |
| MC-020 | PARTIAL | Holding sums are at the useful level, but the inner risk label join removes the null group. Verify required fact participation when replacing joins. |
| MC-021 | PARTIAL | Computes AVG cash amount per investor instead of SUM. Correct the inner metric and preserve null risk group. |
| MC-022 | MISMATCH | Uses average allocation instead of investor maximum and raw holding average instead of investor total. Preserve required shared population and null risk group. |
| MC-023 | MISMATCH | Uses group totals/counts and adds cash plus rebalance counts. Required transaction metric is average investor cash transaction count; summarize each source separately. |
| MC-024 | PARTIAL | Uses scenario count instead of allocation change; goal investor summaries are present. Add delta metric and preserve null risk group. |
| MC-025 | SKIPPED_EXECUTION_FAILURE | Final_Spec fails because Investor connecting risk tolerance is missing. Retrieve the schema connection path, expand repair schema, and rerun only dependent stages. |
| MC-026 | MISMATCH | Uses cash/scenario group totals and counts instead of requested investor summaries and group averages. Define metric levels explicitly; preserve null risk group. |
| MC-027 | PARTIAL | Per-investor goal and health summary logic is present; inner horizon label attachment drops the null horizon. Repair label join only, retaining required participation. |
| MC-028 | PARTIAL | Treats holding gain as return percentage instead of SUM(currentValue-cost) per investor. Correct units/formula and retain null horizon. |
| MC-029 | MISMATCH | Uses cash/shortfall totals and raw goal weighting; outer merges split null horizon into separate rows. Join investor summaries before final grouping. |
| MC-030 | PARTIAL | Uses AVG allocation rather than MAX and AVG currentValue rather than SUM per investor. Correct inner aggregates; existing null groups survive. |
| MC-031 | MISMATCH | Uses totals/counts instead of investor averages and splits null groups in outer aggregate merges. Apply explicit metric levels and null-safe group merge only when appropriate. |
| MC-032 | PARTIAL | Scenario count replaces allocation delta; goal averaging is at raw row level. Compute investor metrics then horizon averages; retain null group. |
| MC-033 | MISMATCH | Zero-fills missing allocation inputs, uses scenario gap for rebalancing gap, and raw rebalancing averages. Preserve null arithmetic and source-qualified formulas; fix null-group merge. |
| MC-034 | MISMATCH | Uses group cash totals/scenario counts and row-weighted delta. Define investor cash and scenario metrics and retain null horizon. |
| MC-035 | PARTIAL | Inner Category label join drops null category; raw goal rows weight health and goal averages. Some wrong averages fall within grader tolerance. Use investor summaries despite PARTIAL reason focusing on nulls. |
| MC-036 | PARTIAL | Mixes holding category with profile category and uses raw gain averages/totals. Resolve Investor category and SUM gain per investor before averaging. |
| MC-037 | MISMATCH | Uses raw cash AVG instead of investor SUM and raw goal averages. Correct two-level metrics and preserve null category. |
| MC-038 | MISMATCH | Uses allocation AVG instead of MAX and holding row AVG instead of investor SUM. Use profile category, shared population, and correct summaries. |
| MC-039 | MISMATCH | Copies Investor rdfs_label into category after label collisions, yielding 550 name groups instead of six categories. Track column origin and explicitly alias Category label; correct totals versus investor averages. |
| MC-040 | PARTIAL | Scenario count replaces allocation delta; raw goal weighting and null category loss remain. Add complete investor metric contract. |
| MC-041 | MISMATCH | Computes rebalancing gap from scenario change, confusing source columns. Bind each formula to its owning source; use investor summaries and preserve null category. |
| MC-042 | MISMATCH | Sums investor totals again instead of taking group averages; scenario delta is divided by row count at wrong level. Correct outer aggregates and nullable category. |
| MC-043 | PARTIAL | Raw goal averages and independent group populations differ from investor comparison; null segment merges lose alignment. Join participating investor summaries before grouping. |
| MC-044 | PARTIAL | Uses holding Segment rather than Investor Segment and raw holding gain average. Correct source and investor gain SUM; align null groups. |
| MC-045 | PARTIAL | Uses group cash and shortfall totals instead of investor summary averages. Fix aggregation levels and null-segment merge. |
| MC-046 | MISMATCH | Missing Investor source leads to holding Segment; raw holding/allocation join multiplies facts. Add profile source and investor summaries with MAX concentration. |
| MC-047 | PARTIAL | Adds cash and rebalancing counts and uses totals; extra holding branch is unused. Define cash transaction count metric and required branch participation; preserve null segment. |
| MC-048 | PARTIAL | Scenario and goal averages operate on raw records by segment. Calculate investor summaries first and preserve null segment in joins. |
| MC-049 | MISMATCH | Zero-fills missing delta inputs and uses raw scenario/rebalancing weighting. Preserve SQL null arithmetic and two-level metrics; retain null segment. |
| MC-050 | MISMATCH | Counts distinct scenario labels instead of allocation change and reports totals. Add requested metric definitions and preserve null segment. |
| MC-051 | PARTIAL | Raw gain average differs from AVG investor gain SUM; independently merged group populations/null groups differ. Use one shared investor population. |
| MC-054 | MISMATCH | Raw rebalancing/cash averages differ from investor sums, and goal weighting is wrong. Null aggregate-join keys leave missing comparison values. Use investor summaries then group once. |
| MC-055 | MISMATCH | Raw scenario/rebalancing join multiplies facts and risks currentAllocationPct collision; zero-filling and missing scenario delta remain. Alias source fields and independently summarize formulas. |
| MC-056 | MISMATCH | Uses group cash/sector totals, average allocation and zero-filled delta. Specify each investor metric and shared population before group comparison. |
| MC-058 | PARTIAL | Uses investor shortfall SUM instead of AVG and allocation AVG instead of MAX. Preserve required participation and null dimensions. |
| MC-061 | PARTIAL | Uses raw gain average rather than average investor gain totals; null group merge does not align all metrics. Correct inner metric and group assembly. |
| MC-064 | MISMATCH | TimeHorizon prefix expands to ontology/TimeHorizonTimeHorizon, so q_time returns zero rows. Investor scan also expands three multivalued relations to 101104 rows. Validate expanded IRIs and row grain; fix row-weighted averages after these upstream failures. |
| MC-065 | PARTIAL | Investor scenario summaries exist, but left joins include investors excluded by reference inner fact participation. Keep optional labels separate from eligibility joins; retain null horizon. |
| MC-066 | MISMATCH | Uses raw group totals/means with independently merged null groups and unused holding source. Specify required metrics and source participation before combining. |
| MC-068 | PARTIAL | Uses global shortfall sum/count rather than average investor averages, and allocation AVG instead of MAX. Correct metric levels and null-group merge. |
| MC-071 | PARTIAL | Non-null metric levels are useful, but left fact joins differ from required shared participation and inner Category drops null group. Encode eligibility and label joins separately. |
| MC-074 | PARTIAL | Summary functions are largely correct; left fact joins change the investor population, and inner Category removes null. Fix population before final means. |
| MC-075 | MISMATCH | Raw scenario/rebalancing joins change multiplicity and eligibility. Independently summarize each source before category comparison; preserve null category. |
| MC-076 | SKIPPED_EXECUTION_FAILURE | Decomposition fails repeatedly on nonexistent InvestorProfile class. Resolve canonical Investor class and permit schema expansion during repair. |
| MC-078 | PARTIAL | Raw group shortfall weighting and allocation AVG instead of MAX. Correct investor summaries and retain null groups. |
| MC-083 | PARTIAL | Uses AVG currentValue per investor where reference requires SUM. Retain existing null groups and verify required fact participation. |
| MC-084 | PARTIAL | Raw cash/rebalancing averages and scenario count replace requested investor totals/delta. Correct all metrics and null-group handling. |
| MC-086 | MISMATCH | Reports totals with signed outflow instead of requested average positive outflow; reference also requires health participation. Make this hidden benchmark eligibility explicit before evaluating generalization. |
| MC-090 | PARTIAL | Raw shortfall/currentValue/allocation averages replace investor AVG/SUM/MAX summaries. Correct metric definitions and null-group merge. |
| MC-091 | MISMATCH | Invents non-null horizon filter; scenario AVG(newAllocationPct) is not delta. Restore nullable dimension, correct formula, and required fact population. |
| MC-093 | MISMATCH | Reports group totals instead of averages of investor metrics; goal shortfall needs investor AVG, not SUM. Preserve conditional-zero semantics and make reference health eligibility explicit. |
| MC-097 | PARTIAL | Uses group holding SUM instead of AVG investor SUM and allocation AVG instead of MAX. Correct metric levels, eligibility, and nullable group. |
| MC-098 | MISMATCH | Uses investor scenario SUM instead of AVG and left fact participation; inner labels discard nulls. Correct metric and population contracts. |
| MC-100 | MISMATCH | Invents cash types inflow/outflow; both scans return zero and repairs preserve the mistaken requirement. Use amount sign predicates, restore complete investor metrics, and specify health eligibility. |
| MC-104 | PARTIAL | Concentration uses SUM allocation instead of MAX; missing scores are zero-filled. Correct the score formula/null policy before testing top-ten membership and order. |
| MC-105 | MATCH | Saved MATCH is empty-result agreement despite wrong logic: aggregate thresholds are pushed onto raw cash/goals/scenario fields and new allocation replaces delta. Require a positive synthetic witness; do not treat this as semantic success. |
