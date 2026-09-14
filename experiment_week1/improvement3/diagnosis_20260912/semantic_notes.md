# Successful-output semantic audit

Read-only investigation on 2026-09-12. Sources: `pipelien_output/graded_v1_pipeline_success_terra.csv`, its two `v1_queries_*_debug.csv` files, and reference SQL read directly from `query_specs_improevemnt/improvement1/dataset/verification_results_v2_sql_correct_442.xlsx` using ZIP/XML. No pipeline execution, API requests, workbook edits, or production edits were performed.

## Scope and grading limits

The graded CSV has 55 pipeline successes: **28 recorded MATCH, 18 recorded PARTIAL, 9 recorded MISMATCH**. These are existing grader labels, not a new independent correctness score. There are 192 attempted queries in the two supplied ranges, not a full 442-query evaluation.

Five successful rows have invalid ground-truth JSON, each exactly **32,767 characters**, consistent with the Excel cell text limit: WM-1T-008, WM-1T-009, WM-2T-011 (recorded MATCH), WM-2T-017, and BSQ-3T-009. Complete entity-set grading is unreliable for these rows until the full reference answer is regenerated from SQL or recovered from an untruncated source.

The grader calls `truncate_for_prompt` with a 60,000-character default. Five successful final-answer cells exceed that limit: WM-1T-008 (226,133), WM-1T-009 (60,925), WM-2T-009 (62,774), WM-2T-011 (79,493), MC-015 (482,205). The model therefore does not receive all answer rows in these cases.

Grader explanations also contain demonstrable counting mistakes:

- BSQ-1T-003: reference 39 records, result 34, overlap 34, missing 5, extra 0. The explanation says 36 correct and 2 omitted.
- TT-047: reference 49 investors, result 50, overlap 7, missing 42, extra 43. The explanation says both sets have 50 and 43 are missing.

The grader's universal absolute tolerance of 1.5 is inappropriate as a sole comparison rule across counts, currency, ratios, and percentages. Example: WM-2T-012 uses the wrong averaging grain but its three numeric discrepancies are under 1.5, so the grader identifies only the missing null group. Exact integer comparison and metric-specific tolerances would be more informative.

## Decisive examples with earliest wrong decision

### TT-058: an entire required condition is lost in decomposition

Question: investors with Deposit transactions, Scenario-based actions, and Economic Growth scenario records.

Reference SQL requires three predicates: `c.type='Deposit' AND r.logic='Scenario-based' AND s.scenario='Economic Growth'`, joining CashFlow, RebalancingAction, ScenarioRebalancing through investor identity.

Debug decomposition produces only two subquestions: Deposit CashFlow and Economic Growth ScenarioRebalancing. The RebalancingAction condition disappears. The final intersection returns **54 investors instead of 16**, including all 16 references plus **38 extras**. The validator explicitly approves the two-set intersection as satisfying the three-condition question. Additional operators cannot repair a requirement absent from the plan.

### TT-047: a categorical value is silently changed

Question and SQL require `Rebalance Sell`. The third subquestion rewrites this to `RebalancingAction.action = 'Sell'`; generated SPARQL filters `LCASE(STR(?action)) = "sell"`.

`Sell` and `Rebalance Sell` are distinct values in this dataset. Result: **7 common investors, 42 missing, 43 extras**. The validator checks the three-branch intersection shape and incorrectly asserts all original conditions are met.

### MC-007: the domain grouping key is reinterpreted as a date component

Question groups cash-flow comparison by `time_horizon`. SQL pre-aggregates cash by investor and then groups by `Investor.time_horizon`, reporting averages of investor inflow, outflow, and net cash flow.

The sole subquestion instead retrieves CashFlow amount/type/date and says time horizon is derived from date. Processing executes `Date_Extract(year)` then sums by year and inflow/outflow bucket. Output has **12 year/bucket rows instead of 4 time-horizon rows**. Both the entity relationship and requested output meaning are lost before execution.

### MC-015: validator prefers a wrong generated specification over the question

Question requires goal shortfall comparison across scenario. SQL computes per-investor/per-scenario scenario metrics and per-investor goal average, joins on investor, and then averages by scenario (13 result groups).

Decomposition asks only for individual goal shortfall. Query-spec cleanup removes an attempted second retrieval; active retrieval contains only InvestmentGoal. Final answer contains **4,247 goal rows** instead of 13 scenario groups.

Validator text explicitly states: "Although the natural-language question mentions 'across scenario' and two related tables, the formal query specification only requires shortfall per goal, and the result satisfies that specification." This is a direct example of checking self-consistency instead of user intent.

### MC-017: lost join grain, wrong averaging population, unintended sum

Reference SQL pre-averages SectorAllocation and PortfolioHolding separately by **(investor_id, sector)**, joins on **both investor_id and sector**, and averages those investor-sector values by sector.

The pipeline retrieves allocation by sector and computes holding average across all holdings per sector. It joins only on `sector`, having already lost investor-level membership and weights. The final result also sums allocation percentages: Automobile allocation **1,655.02 vs 13.57**; holding return **75.53 vs 37.24**. The remaining sectors also differ. This is not a missing arithmetic operator; it is an incorrect relational grain.

### WM-2T-012: averaging averages changes the meaning

SQL directly averages goal-level `progress_pct` by investor risk tolerance. The pipeline first averages each investor's goals, then averages investor averages by risk tolerance. These are not equivalent when investors have unequal goal counts.

Reference vs output: Aggressive 39.18 vs 39.76; Conservative 38.08 vs 38.25; Moderate 40.87 vs 41.21. The null group (45.88) is missing. This shows why "pre-aggregate everything before joining" is not a universal solution: the desired weighting must be explicit.

### WM-4T-006: temporal scope is narrowed incorrectly

Reference SQL constrains both cash-flow dates and holding purchase dates to calendar 2025. Decomposition explicitly retrieves cash-flow activity "(any date)" while applying 2025 only to holdings. Result is **29 investors vs 19**, with **10 extras**. The natural wording has some scope ambiguity, but the benchmark's intended interpretation is explicit in SQL.

## Retrieval completeness and projection

### Null groups removed before aggregation

- WM-2T-004: **24 vs 28 groups**. SPARQL makes `hasInvestmentGoalType` mandatory, dropping the four null investment-goal groups. All 24 remaining group counts match. A final `preserve_null_groups: true` cannot restore rows removed in Scan.
- WM-2T-006: **50 vs 66 groups**. Both CashFlow `source` and Investor `category` are mandatory triple patterns. All 16 groups involving a null source or category are lost. The 50 remaining counts match.
- BSQ-1T-003: **34 vs 39 records**. Query selects numerous extra mandatory fields including liquidityScore, goalMatchPct, sourceTable and healthOfInvestor, beyond the question's risk/diversification predicates. This creates a plausible completeness loss for partially populated records; confirming the exact missing-field cause would require inspecting the five missing KG records. The scan already contains only 34, so later processing is not where these five disappear.

### Correct entities but incomplete presentation

Exact investor-ID sets match reference for at least **six** PARTIAL cases whose ground truth parses fully: WM-2T-008 (21), WM-3T-001 (376), WM-3T-004 (243), WM-3T-006 (64), BSQ-3T-004 (110), TT-039 (108). All omit reference investor names. WM-2T-008 preserves the allocation values too. This is an output-contract issue, not failed relational reasoning. Some natural-language questions merely say "which investors," so a benchmark should state whether identity-only answers are accepted; under the present reference projection these are partial.

WM-2T-007 contains the correct **319 distinct investors but 334 rows** (15 duplicate rows) and omits names. WM-2T-009 contains the correct **206 distinct investors but 228 rows** (22 duplicate rows), retaining names. Deduplicating by investor identity must be an explicit contract for investor-list questions; child-row identity is a different grain.

## Historical empty-result/report corruption

WM-2T-002, WM-4T-002, TT-036, and WM-5T-003 have final intersection row counts of zero and permissive empty-result validation, while the reported answer contains the last Scan branch's nonempty rows. Historical `run_pipeline_v1/main.py:341-345` explains this: an empty `final_operator_data` falls through to `scan_raw_rows`.

Examples of resulting reported corruption:

- WM-2T-002: expected 133 investors; last branch contains 372 (239 extra). Earlier decomposition also invents Investor `segment='Conservative'` instead of riskTolerance, leaving one branch empty.
- WM-4T-002: expected 5 investors; report contains 135 rows/130 distinct investors, 125 extra distinct investors. Processing re-filters ScenarioRebalancing on `scenario`, although that field was used by SPARQL but not projected, yielding zero rows.
- TT-036: expected 63 investors; report contains 129 rows/127 distinct investors, 64 extra distinct investors. Processing re-filters CashFlow on `type`, which the Scan did not project, yielding zero rows.
- WM-5T-003: expected 3 investors; report contains 498 (495 extra).

The inspected current `run_pipeline_v3/main.py:342-348` no longer falls back to raw Scan rows, so the historical CSV issue must not be presented as proof that current V3 still writes raw results. It still checks final data by truthiness and falls back to final_answer for `[]`; preserving the distinction between absent output and valid empty output remains advisable.

BSQ-3T-009 illustrates another missing-input filter: the holdings branch filters on purchaseDate in processing after Scan projects IDs only. Processing yields zero; Set_Difference consequently returns all 990 2025 cash-flow investors. The reference JSON is truncated, so a complete false-positive count cannot be established from that cell.

## Avoid overclaiming data fabrication

WM-1T-008's Terra reason calls `GOAL-*` records fabricated. Those same identifiers appear in `Debug Scan Summary` with `sourceTable=ATOM_ENTITY_INVESTMENT_GOAL_001`, so the logs do not support calling this model hallucination. The ground truth is also truncated. The KG and SQL answer population should be reconciled before attributing these extras to pipeline reasoning. The scan's many mandatory fields and omitted final investorId are separate visible issues.

## Interpretation

The evidence shows several distinct failure mechanisms, not insufficient operator coverage: requirements lost or changed in decomposition, wrong relational grain, mandatory retrieval of nullable fields, re-filtering fields no longer present, incomplete output projection/deduplication, permissive self-validation, historical result-report fallback, and damaged evaluation artifacts. Frequencies above are exact only for the specified subsets; the categories overlap and should not be summed into a 27-case exclusive taxonomy.
