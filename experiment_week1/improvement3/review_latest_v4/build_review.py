"""Build read-only-review deliverables from saved evidence and manual findings."""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / 'evidence.json').read_text())

# Findings refer to the saved plans and SQL, not independently replayed live data.
mc_text = '''
001|Saved MATCH; raw goal averages match this question's requested grouping. Preserve as a control.
002|Risk bands use 20-point intervals instead of reference <33/<67/ELSE. Define boundaries and null/default behavior in the question contract; the question does not specify these thresholds.
003|Saved MATCH; left label attachment preserves null investment-type group. Preserve as a control.
004|Inner cash-type label join loses null group; filtered positive/negative subgroups need conditional-zero semantics. Preserve the base group and calculate sign-based components.
005|Raw goal averages weight investors by number of goals; reference averages per-investor averages. Aggregate by investor first and retain null risk group.
006|Uses holding category instead of Investor category and group totals instead of averages of investor totals. Resolve source ownership and use two aggregation levels.
007|Uses totals, signed negative outflow, and omits net-flow metric. Define all cash components per investor, then average by horizon; retain null horizon.
008|Inner Segment label join drops the null segment. Preserve health rows through optional label attachment.
009|Uses holding category and raw holding/allocation joins. Resolve profile category; independently calculate investor holding totals and MAX allocation concentration before joining.
010|Uses raw rebalancing amount/gap averages instead of required investor summaries. Separate per-investor calculations from risk-group averages and retain null risk.
011|Groups by horizon plus scenario instead of horizon; misses average of investor maximum allocation change. Compute row delta, investor MAX, then group AVG.
012|Joins raw goal and cash records, multiplying facts; omits goal-progress comparison. Aggregate with required investor/goal keys before joining.
013|Omits holding-return metric and weights health through raw holding rows. Build holding summaries and health comparison separately; retain null investment type.
014|Raw cash/rebalancing join multiplies facts; amount_right supplies only one requested metric. Summarize cash by investor/type and rebalancing by investor before combining.
015|Raw goal/scenario join changes weights and misses scenario delta. Calculate independent investor summaries and then horizon comparison.
016|Joins unrelated rebalanceId and scenarioRebalanceId, producing empty output. Use shared investor identity and preserve logic grouping; calculate each source's own allocation formula.
017|Joins global sector aggregates, losing investor+sector eligibility. Summarize at investor+sector first and retain requested AVG versus SUM distinctions.
018|Raw cash/scenario join multiplies facts and misses net cash flow. Build each investor metric first; retain nullable source groups.
019|Independent group summaries do not establish the required shared investor population; goal weights and null-group merge also differ. Join investor summaries before group aggregation.
020|Holding sums are at the useful level, but the inner risk label join removes the null group. Verify required fact participation when replacing joins.
021|Computes AVG cash amount per investor instead of SUM. Correct the inner metric and preserve null risk group.
022|Uses average allocation instead of investor maximum and raw holding average instead of investor total. Preserve required shared population and null risk group.
023|Uses group totals/counts and adds cash plus rebalance counts. Required transaction metric is average investor cash transaction count; summarize each source separately.
024|Uses scenario count instead of allocation change; goal investor summaries are present. Add delta metric and preserve null risk group.
025|Final_Spec fails because Investor connecting risk tolerance is missing. Retrieve the schema connection path, expand repair schema, and rerun only dependent stages.
026|Uses cash/scenario group totals and counts instead of requested investor summaries and group averages. Define metric levels explicitly; preserve null risk group.
027|Per-investor goal and health summary logic is present; inner horizon label attachment drops the null horizon. Repair label join only, retaining required participation.
028|Treats holding gain as return percentage instead of SUM(currentValue-cost) per investor. Correct units/formula and retain null horizon.
029|Uses cash/shortfall totals and raw goal weighting; outer merges split null horizon into separate rows. Join investor summaries before final grouping.
030|Uses AVG allocation rather than MAX and AVG currentValue rather than SUM per investor. Correct inner aggregates; existing null groups survive.
031|Uses totals/counts instead of investor averages and splits null groups in outer aggregate merges. Apply explicit metric levels and null-safe group merge only when appropriate.
032|Scenario count replaces allocation delta; goal averaging is at raw row level. Compute investor metrics then horizon averages; retain null group.
033|Zero-fills missing allocation inputs, uses scenario gap for rebalancing gap, and raw rebalancing averages. Preserve null arithmetic and source-qualified formulas; fix null-group merge.
034|Uses group cash totals/scenario counts and row-weighted delta. Define investor cash and scenario metrics and retain null horizon.
035|Inner Category label join drops null category; raw goal rows weight health and goal averages. Some wrong averages fall within grader tolerance. Use investor summaries despite PARTIAL reason focusing on nulls.
036|Mixes holding category with profile category and uses raw gain averages/totals. Resolve Investor category and SUM gain per investor before averaging.
037|Uses raw cash AVG instead of investor SUM and raw goal averages. Correct two-level metrics and preserve null category.
038|Uses allocation AVG instead of MAX and holding row AVG instead of investor SUM. Use profile category, shared population, and correct summaries.
039|Copies Investor rdfs_label into category after label collisions, yielding 550 name groups instead of six categories. Track column origin and explicitly alias Category label; correct totals versus investor averages.
040|Scenario count replaces allocation delta; raw goal weighting and null category loss remain. Add complete investor metric contract.
041|Computes rebalancing gap from scenario change, confusing source columns. Bind each formula to its owning source; use investor summaries and preserve null category.
042|Sums investor totals again instead of taking group averages; scenario delta is divided by row count at wrong level. Correct outer aggregates and nullable category.
043|Raw goal averages and independent group populations differ from investor comparison; null segment merges lose alignment. Join participating investor summaries before grouping.
044|Uses holding Segment rather than Investor Segment and raw holding gain average. Correct source and investor gain SUM; align null groups.
045|Uses group cash and shortfall totals instead of investor summary averages. Fix aggregation levels and null-segment merge.
046|Missing Investor source leads to holding Segment; raw holding/allocation join multiplies facts. Add profile source and investor summaries with MAX concentration.
047|Adds cash and rebalancing counts and uses totals; extra holding branch is unused. Define cash transaction count metric and required branch participation; preserve null segment.
048|Scenario and goal averages operate on raw records by segment. Calculate investor summaries first and preserve null segment in joins.
049|Zero-fills missing delta inputs and uses raw scenario/rebalancing weighting. Preserve SQL null arithmetic and two-level metrics; retain null segment.
050|Counts distinct scenario labels instead of allocation change and reports totals. Add requested metric definitions and preserve null segment.
051|Raw gain average differs from AVG investor gain SUM; independently merged group populations/null groups differ. Use one shared investor population.
054|Raw rebalancing/cash averages differ from investor sums, and goal weighting is wrong. Null aggregate-join keys leave missing comparison values. Use investor summaries then group once.
055|Raw scenario/rebalancing join multiplies facts and risks currentAllocationPct collision; zero-filling and missing scenario delta remain. Alias source fields and independently summarize formulas.
056|Uses group cash/sector totals, average allocation and zero-filled delta. Specify each investor metric and shared population before group comparison.
058|Uses investor shortfall SUM instead of AVG and allocation AVG instead of MAX. Preserve required participation and null dimensions.
061|Uses raw gain average rather than average investor gain totals; null group merge does not align all metrics. Correct inner metric and group assembly.
064|TimeHorizon prefix expands to ontology/TimeHorizonTimeHorizon, so q_time returns zero rows. Investor scan also expands three multivalued relations to 101104 rows. Validate expanded IRIs and row grain; fix row-weighted averages after these upstream failures.
065|Investor scenario summaries exist, but left joins include investors excluded by reference inner fact participation. Keep optional labels separate from eligibility joins; retain null horizon.
066|Uses raw group totals/means with independently merged null groups and unused holding source. Specify required metrics and source participation before combining.
068|Uses global shortfall sum/count rather than average investor averages, and allocation AVG instead of MAX. Correct metric levels and null-group merge.
071|Non-null metric levels are useful, but left fact joins differ from required shared participation and inner Category drops null group. Encode eligibility and label joins separately.
074|Summary functions are largely correct; left fact joins change the investor population, and inner Category removes null. Fix population before final means.
075|Raw scenario/rebalancing joins change multiplicity and eligibility. Independently summarize each source before category comparison; preserve null category.
076|Decomposition fails repeatedly on nonexistent InvestorProfile class. Resolve canonical Investor class and permit schema expansion during repair.
078|Raw group shortfall weighting and allocation AVG instead of MAX. Correct investor summaries and retain null groups.
083|Uses AVG currentValue per investor where reference requires SUM. Retain existing null groups and verify required fact participation.
084|Raw cash/rebalancing averages and scenario count replace requested investor totals/delta. Correct all metrics and null-group handling.
086|Reports totals with signed outflow instead of requested average positive outflow; reference also requires health participation. Make this hidden benchmark eligibility explicit before evaluating generalization.
090|Raw shortfall/currentValue/allocation averages replace investor AVG/SUM/MAX summaries. Correct metric definitions and null-group merge.
091|Invents non-null horizon filter; scenario AVG(newAllocationPct) is not delta. Restore nullable dimension, correct formula, and required fact population.
093|Reports group totals instead of averages of investor metrics; goal shortfall needs investor AVG, not SUM. Preserve conditional-zero semantics and make reference health eligibility explicit.
097|Uses group holding SUM instead of AVG investor SUM and allocation AVG instead of MAX. Correct metric levels, eligibility, and nullable group.
098|Uses investor scenario SUM instead of AVG and left fact participation; inner labels discard nulls. Correct metric and population contracts.
100|Invents cash types inflow/outflow; both scans return zero and repairs preserve the mistaken requirement. Use amount sign predicates, restore complete investor metrics, and specify health eligibility.
104|Concentration uses SUM allocation instead of MAX; missing scores are zero-filled. Correct the score formula/null policy before testing top-ten membership and order.
105|Saved MATCH is empty-result agreement despite wrong logic: aggregate thresholds are pushed onto raw cash/goals/scenario fields and new allocation replaces delta. Require a positive synthetic witness; do not treat this as semantic success.
'''
notes = {'MC-' + line.split('|', 1)[0]: line.split('|', 1)[1] for line in mc_text.strip().splitlines()}

def assign(ids, text):
    for key in ids.split():
        notes[key] = text

assign('WM-1T-011 WM-1T-013 WM-1T-014 WM-1T-015 WM-1T-017 WM-2T-005 WM-2T-012 WM-2T-013 WM-2T-014 WM-2T-019 WM-3T-008 WM-4T-004 BSQ-1T-004 BSQ-1T-005 BSQ-1T-006 BSQ-2T-009 TT-042', 'Inner dimension-label attachment excludes required null groups. Preserve the fact/profile grouping base with optional labels; retain required fact joins. Confirm named-group values with deterministic comparison.')
assign('WM-1T-012', 'Left join starts from dimension rows, so absent dimension values still disappear. Start from fact/group rows and left-attach labels.')
assign('WM-1T-005', 'Final plan fails on alias dependencies: independent rename steps read join_all, so the next step lacks the preceding alias. Chain renames and validate column origin and dependencies before execution.')
assign('WM-1T-019', 'Top-five selection differs at a tied cutoff (9900). Define tie-aware evaluation or a specified secondary key before declaring tied membership wrong.')
assign('WM-2T-002 WM-2T-020 WM-4T-001 WM-4T-008 BSQ-3T-001', 'Filters risk-tolerance words on Investor category, producing an empty branch. Ground categorical concepts in RiskTolerance/profile risk_tolerance and reject incompatible literal domains.')
assign('WM-2T-003 WM-5T-001', 'Gold is grounded as Asset instead of holding investment type. Use the InvestmentType relation; reject unsupported cross-branch IN reference strings and undeclared graph paths.')
assign('WM-3T-004', 'Aggressive is filtered on category and Gold on investment name rather than risk tolerance and investment type. Fix both source-field mappings.')
assign('WM-2T-004 WM-2T-006', 'Inner joins to nullable grouping dimensions remove required combinations. Preserve nulls in both group keys and compare the complete group-key set.')
assign('WM-2T-011', 'Final filter sector != null evaluates UNKNOWN for every row and removes everything. Require is_not_null plus explicit blank-string policy; ground truth is also truncated and must be restored.')
assign('WM-3T-002 BSQ-3T-002', 'Bucket boundaries differ from reference <33/<67/ELSE, null risk is not assigned reference ELSE, and inner label joins omit null groups. Specify benchmark band definitions explicitly and add default/null bucket behavior.')
assign('WM-3T-003', 'Inner cash-type label join drops null type combinations. Count distinct investors at the required group grain and preserve nullable labels.')
assign('WM-3T-009', 'Outer merging separately aggregated null keys creates multiple null-group rows. Prefer one shared base/group operation, or scoped null-safe equality for matching aggregate groups.')
assign('WM-3T-013', 'Both 2024 date filters are inside OPTIONAL blocks, so all holdings/cash rows survive. Move row predicates to the correct outer filter scope and retain the null risk group; preserve reference profile base and zero semantics.')
assign('WM-3T-016 WM-4T-010 WM-5T-003', 'Pushes total/net conditions onto individual cash/goal rows before aggregation. Reference net flow uses a type-dependent CASE formula, not plain SUM(amount). Define that formula explicitly, aggregate first, then filter; goal shortfall also needs its requested entity summary.')
assign('WM-4T-003', 'Computes a row-weighted goal average (sum of sums/counts), not AVG of investor averages. Inner risk labels remove null group and left fact joins differ from required population.')
assign('WM-4T-007', 'Filters progressPct <25 before averaging, changing AVG population. Retrieve all goal progress, average by investor, then apply threshold; sector branch is present despite grader wording about missing evidence.')
assign('BSQ-1T-007', 'Saved MATCH omits the null-sector group (13 reference rows versus 12). Grader waived it as uninformative; strict group coverage must retain the row even when metrics are null.')
assign('BSQ-1T-008', 'Inner scenario-label join removes the null-scenario candidate before ranking, replacing the correct fifth row. Preserve all groups before top-five selection.')
assign('BSQ-2T-001', 'Filters Long-term on category instead of time horizon. Correct categorical source before investor goal count and HAVING >=4.')
assign('BSQ-2T-008', 'Uses ScenarioRebalancing.triggeredAction for Automated Trigger instead of RebalancingAction.logic. Resolve source class and exact property before joining investors.')
assign('BSQ-2T-010', 'Reuses the cash-type rdfs_label as category after a label collision, producing two transaction-type groups. Alias Category label explicitly; apply reference Withdrawal sign and conditional zeros.')
assign('BSQ-3T-003', 'shortfall >0 occurs only inside OPTIONAL, retaining all 4865 goals. Outer row filtering must exclude nonqualifying goals before investor intersection; saved output has one extra investor.')
assign('BSQ-3T-005', 'Filters Tactical as a scenario and omits RebalancingAction logic source. Retrieve action logic and market scenario independently and intersect on investor.')
assign('BSQ-3T-006', 'Uses raw weighted shortfall mean, omits liquidity-score comparison, and removes null risk group. Enforce full metric coverage and AVG of investor goal averages.')
assign('BSQ-3T-007', 'Joins global sector totals rather than investor+sector summaries, losing the shared investor-sector population. Join on the composite key before final sector totals.')
assign('BSQ-4T-003', 'Uses Investor risk tolerance instead of PortfolioHealth numeric risk bands and omits health source. Add numeric band contract, investor summaries, and required participation.')
assign('BSQ-4T-004', 'Compares textual riskTolerance with numeric 50 instead of health riskScore; lacks health source and uses signed Withdrawal sum for descending ranking. Correct source, datatype, sign, and candidate population.')
assign('BSQ-4T-005', '2025 date filter is absent from the holding branch while present on cash. Require source-specific predicate coverage for both date conditions before intersection.')
assign('TT-039 TT-061', 'Goal timeToGoalMonths <=12 is inside OPTIONAL, so all 4865 goals survive. Validate row-filter scope, then intersect eligible investor sets.')
assign('TT-044 TT-056', 'Filters Manual Override on action instead of rebalancing logic. Correct property/domain mapping; current branch is empty.')
assign('TT-047', 'Rebalance Sell literal is changed to Sell. Preserve exact categorical literal; additionally check goal filter scope during query contract validation.')
assign('TT-054', 'Inner logic-label join drops null groups. Reference SQL also includes cash-flow participation absent from question/plan; clarify that benchmark requirement before enforcing it generically.')
assign('TT-058', 'Missing Scenario-based rebalancing-logic predicate admits extra investors. Enforce every source-specific condition from the question.')
assign('TT-063', 'Subtracts SUM shortfall rather than reference AVG shortfall per investor; zero-fills null deltas and uses left participation. Specify score metric and eligibility before ranking; wording leaves shortfall aggregation implicit.')
assign('TT-065', 'Saved MATCH is empty-result agreement, but Tactical filters action instead of reference logic. Add a positive witness so an empty date window cannot hide semantic errors.')
assign('TT-057', 'Saved MATCH on this top ten, but row delta zero-fills missing inputs whereas reference subtracts with null propagation. Protect current result and add missing-input counterexample.')

for c in data['cases']:
    key = c['short_id']
    if key not in notes:
        if c['grade'] == 'MATCH':
            notes[key] = 'Saved MATCH; retain as regression control. Verify declared answer shape, entity identity, aliases, and duplicate policy deterministically rather than relying solely on the saved semantic grade.'
        else:
            notes[key] = 'Saved result discrepancy requires follow-up against complete source rows. Existing grader evidence: ' + c['reason']
    if not c['reference_json_parseable']:
        notes[key] += ' Reference JSON is cut off at the Excel cell limit (32767 characters); full-set correctness is unresolved until restored from SQL to an external artifact.'

def md(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')

columns = ['question_id', 'saved_grade', 'execution_status', 'review_finding_and_change', 'reference_complete_json', 'expected_rows', 'actual_rows', 'question', 'saved_grader_reason', 'reference_sql', 'source_report']
with (HERE / 'QUESTION_REVIEW.csv').open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    for c in sorted(data['cases'], key=lambda c:c['id']):
        writer.writerow(dict(zip(columns, [c['short_id'], c['grade'], c['status'], notes[c['short_id']], c['reference_json_parseable'], c['expected_rows'], c['result_rows'], c['question'], c['reason'], c['sql'], c['report']])))

intro = '''The review covers all 192 saved questions, their debug traces, and their matching workbook questions/answer text. Findings compare saved retrieval contracts, executed SPARQL, final plans, row-count traces, and reference SQL. No live database replay or model rerun was performed. Stored scan samples do not prove every underlying value. Saved grades are preserved, not independently recertified. Some questions leave reference metric definitions or participation implicit; these are benchmark ambiguities, not permission to inject reference SQL into inference.

The latest saved grades are 57 MATCH, 75 PARTIAL, 55 MISMATCH, 2 OTHER, and 3 skipped execution failures. The comparative subset is 76 questions: 3 MATCH, 36 PARTIAL, 35 MISMATCH, and 2 execution failures. MC-105's empty MATCH has visibly incorrect plan semantics. All 192 question strings and ground-truth strings match the workbook; six reference cells contain truncated JSON. The three inference manifests match current inference sources; current grade_final_answers.py differs from the recorded hash. Keep inference and grader provenance separate.
'''

comparative = '''# Separate multi-step comparative change plan

''' + intro + '''
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
'''
for c in sorted((c for c in data['cases'] if c['short_id'].startswith('MC-')), key=lambda c:c['short_id']):
    comparative += f"| {c['short_id']} | {c['grade']} | {md(notes[c['short_id']])} |\n"
(HERE / 'MULTISTEP_COMPARATIVE_PLAN.md').write_text(comparative, encoding='utf-8')

details = ['# All 192 question reviews', '', intro, 'Full saved model response prose is omitted here; evidence.json retains decoded source evidence. Nested diagnostic response excerpts may be truncated even when the CSV trace itself is complete.', '']
for c in sorted(data['cases'], key=lambda c:c['id']):
    details += [f"## {c['short_id']} — {c['grade']}", '', c['question'], '', notes[c['short_id']], '', f"Execution: {c['status']}. Reference rows: {c['expected_rows']}; result rows: {c['result_rows']}.", '', 'Reference SQL:', '```sql', c['sql'], '```', '', 'Saved retrieval and final-step evidence:', '```json', json.dumps({'sources': c['branches'], 'retrieval_contracts': c['retrievals'], 'executed_queries': c['queries'], 'final_steps': c['steps'], 'execution_row_counts': c['execution']}, ensure_ascii=False, indent=2), '```', '']
(HERE / 'QUESTION_DETAILS.md').write_text('\n'.join(details), encoding='utf-8')

groups = {
 'schema_loader.py': 'P1: populate source/field descriptions, owning class, ranges, optionality, and relationship cardinality in retrieval index; avoid multivalued connector projection inflation.',
 'connections.py': 'P1/P3: resolve missing schema paths and validate entity/composite join identity, beyond retaining already-declared keys.',
 'llm_operators/retrieve.py': 'P1: use meaningful schema descriptions and categorical domains; expand required neighbor classes during repair.',
 'llm_operators/decompose.py': 'P1/P3: produce full metric/eligibility contract alongside raw branches; distinguish row versus aggregate predicates and canonical classes.',
 'llm_operators/query_spec.py': 'P1/P2: strict operator/value/datatype validation; reject undeclared predicates and cross-branch reference strings; include repaired source schema.',
 'llm_operators/query_spec_validate.py': 'P1/P2: retain semantic critique, but deterministic schema/domain checks must enforce source and requirement coverage.',
 'llm_operators/generate.py': 'P2: render supported raw retrieval deterministically from the typed QuerySpec; validate any fallback against that contract.',
 'llm_operators/pre_scan_validate.py': 'P2: validate expanded class/property IRIs, bound-variable provenance, OPTIONAL/filter scope and exact retrieval contract, beyond SELECT syntax/projection.',
 'llm_operators/refine.py': 'P2/P5: repairs must preserve original meaning and use structured failure reasons; do not reinforce incorrect decomposition requirements.',
 'non_llm_operators/scan.py': 'P2/P5: verify declared keys/grain and query fidelity; retain null/numeric support; record complete scan schema and identity statistics.',
 'utils.py': 'P2: replace wm:-only term extraction with expanded-IRI AST checks and source property ownership; preserve exact literals during repair.',
 'spec_contracts.py': 'P1/P3: extend contracts with predicate scope, metric expression/units, inner/outer aggregation, source lineage and participant population.',
 'spec_runtime.py': 'P3: propagate grain, identity and column lineage; enforce metric coverage, unique summary keys and collision-safe explicit aliases.',
 'llm_operators/final_spec.py': 'P3/P4: consume metric contracts and construct independent summaries then eligibility joins then final groups; validate every requested metric.',
 'relational.py': 'P3/P4: keep SQL null-unequal entity joins; use null-safe joins only for compatible aggregate group keys; expose cardinality assertions.',
 'llm_operators/integrate.py': 'P3/P4: active strict path uses relational runtime; improve upstream join planning, not legacy fuzzy merge/dedup behavior.',
 'llm_operators/filter_aggregate.py': 'P3/P4: retain strict SQL aggregation/null behavior; reject malformed intent such as != null upstream and support conditional aggregates through explicit expressions.',
 'non_llm_operators/math_compute.py': 'P4: add validated conditional expressions where needed; preserve null subtraction and source-qualified operands, avoid implicit zero filling.',
 'non_llm_operators/bucket.py': 'P4: explicit ELSE/default/null policy and precise boundaries; do not invent undocumented bands.',
 'llm_operators/order_by.py': 'P4: rank only complete correctly calculated candidates; specify typed sort and tie policy.',
 'executor.py': 'P5: route repairs to earliest responsible stage, expand schema when needed, preserve failing FinalSpec trace before return; add intermediate identity/null statistics.',
 'main.py': 'P0/P5: preserve run and grade provenance separately; store all attempt traces and avoid treating last-branch summary as complete evidence.',
 'grade_final_answers.py': 'P0: validate complete reference JSON; deterministic grouped/set/numeric/rank checks before optional semantic judgement; avoid universal numeric tolerance and prompt truncation.',
 'run_identity.py': 'P0: separate inference-source and grader fingerprints; bind reports to cohort and graph snapshot.',
 'reporting.py': 'P0/P5: reference artifacts outside Excel cells; explicit invalid-reference status and durable linked report/debug artifacts.',
 'llm_operators/validate.py': 'P3/P5: semantic review can assist but cannot substitute for enforced metric, predicate and population contracts.',
 'llm_operators/processing_spec.py': 'Preserve deterministic raw-row pass-through; keep identity/grain metadata accurate. No extra branch LLM planner is necessary.',
 'llm_operators/explain.py': 'Low priority: saved numeric final output is determined upstream; preserve deterministic presentation while fixing retrieval/plans.',
 'llm_operators/link.py': 'Legacy helper is not the main V4 connection mechanism; consolidate schema path logic only if brought into active execution.',
 'non_llm_operators/check_schema.py': 'Legacy prefix/keyword guard is insufficient; use active expanded-IRI parser validation instead of relying on required prefix text.',
 'non_llm_operators/fuseki.py': 'Retain timeout/health handling. No evidence these transport paths explain the dominant semantic failures; snapshot identity is useful.',
 'non_llm_operators/date_extract.py': 'Retain existing extraction; ensure source date filters are applied before extraction and contract states month versus year-month.',
 'non_llm_operators/difference.py': 'Retain strict relational set-difference path; choose entity-set output explicitly and reject cross-branch filter pseudo-references.',
 'non_llm_operators/set_intersect.py': 'Retain strict relational intersection; validate entity keys and distinguish set answers from repeated fact rows.',
 'non_llm_operators/union.py': 'Retain explicit distinct_on semantics; avoid using duplicate branches as an implicit answer-shape repair.',
 'clients.py': 'No primary correctness rewrite proposed; keep deterministic call configuration and record request provenance.',
 'common.py': 'Keep runtime configuration stable during correctness comparison; no credential changes are needed for this review.',
 'config.py': 'Keep cohort/model flags fixed for regression attribution; expose new contract modes explicitly when implemented.',
 'execution.py': 'Preserve operator dispatch; propagate new plan validation and intermediate diagnostics consistently.',
 'planner.py': 'Keep fixed V4 DAG; semantic fixes belong in explicit contracts and compiler rather than model-generated operator routing.',
 'dag.py': 'Keep compatibility export; no direct semantic failure found.',
 'run.py': 'No functional change required to direct launcher.',
 '__main__.py': 'Low-priority documentation correction: module docstring still refers to run_pipeline_v3.',
}
coverage = ['# Source review coverage and change targets', '', 'Inventory is generated from every Python source below run_pipeline_v4. Test files were inventoried and the suite executed; this is not a claim that mocked tests cover generated query semantics.', '', '| File | Lines | Review disposition |', '|---|---:|---|']
for f in data['summary']['source_inventory']:
    name = f['file']
    disposition = groups.get(name)
    if disposition is None:
        disposition = ('Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification.' if name.startswith('tests/') else 'Historical audit helper; do not mix its older cohort/results with latest 192-question evidence.' if name.startswith('docs/') else 'Package exports reviewed for active dispatch; no correctness change proposed.')
    coverage.append(f"| {name} | {f['lines']} | {disposition} |")
coverage += ['', 'Additional wrapper reviewed: ../grade_v4_3_files_terra.py. Its combine_graded_files() uses the original FILES_TO_GRADE even when --latest selects latest inputs. Pass the selected file list through combination or use one canonical batch runner; test --latest --combine without service calls.', '', 'Full file hashes and definition inventory are retained in evidence.json.']
(HERE / 'SOURCE_REVIEW.md').write_text('\n'.join(coverage), encoding='utf-8')
print('Built QUESTION_REVIEW.csv, QUESTION_DETAILS.md, MULTISTEP_COMPARATIVE_PLAN.md, SOURCE_REVIEW.md')
print('Questions:',len(data['cases']),'MC notes:',sum(k.startswith('MC-') for k in notes))
