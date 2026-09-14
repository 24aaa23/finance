The regression is real. The useful idea is to make execution deterministic; the problematic assumption is that more decomposition, specifications, validators, and operators automatically make the answer more correct. This implementation now has to preserve query meaning across a custom relational interpreter, and several interfaces do not agree about what a valid plan means.

This diagnosis uses the supplied debug/graded files, the older graded results, the baseline results, reference SQL in the dataset, and offline synthetic probes of current code. No production pipeline files were changed and no paid model calls or database reruns were made.

**What the recorded results show**

The supplied new runs cover 192 distinct questions, not all 442. Matching by Sample Row ID gives:

| Run | Recorded exact matches on the same 192 | Full 442 result available |
|---|---:|---:|
| Modified run, supplied logs | 28 / 192 (14.58%) | No |
| Older improvement1 | 70 / 192 (36.46%) | 232 / 442 |
| Baseline file | 80 / 192 (41.67%) | 252 / 442 |

These are existing grader labels, not independent regrading. The baseline filename mentions GPT-OSS, but its embedded Pipeline Version says `base-pipeline-qwen3-235b-v1`. That configurable label alone does not establish the actual model. Confirm model and retry configuration before calling this a controlled architecture comparison. Ground-truth strings are identical between the old/baseline files and between old/new successful rows.

The modified version loses 48 questions the older version got right and gains 6 the older version missed; 22 are correct in both. The net change is -42 on the matched subset.

| New execution outcome | Questions |
|---|---:|
| Final specification failure | 93 |
| Processing specification failure | 21 |
| Query specification failure | 15 |
| Crash | 6 |
| Scan failure | 2 |
| Pipeline success | 55 |

Those 55 successes contain 28 MATCH, 18 PARTIAL, and 9 MISMATCH. Thus approximately half of the completed outputs are fully correct under the existing grader. Overall, 137/192 attempts stop before successful completion. The first 100 contain 27 matches; the last 92 contain just 1. These selected ranges are not a random sample, so do not extrapolate their percentage to the remaining 250 questions.

**1. Several failures are deterministic implementation bugs, not inadequate model reasoning**

The strongest historical example is `WM-1T-015`. Its final measure correctly names `q1_processed`, yet validation reports that `['q1_processed']` does not exist. In the older implementation still present in `run_pipeline`, normalization turns the scalar input into a list; the final validator converts that list into a string and uses it as a dataset key. The actual key and lookup string are different. Regenerating an otherwise correct plan cannot reliably fix this.

Across recorded repair attempts, 44 distinct queries encounter a missing final-measure dataset error, 55 encounter a missing step dataset, and 54 encounter a projection field without a source. These categories overlap; they are not an exclusive allocation of the 137 failures. Current v3 contains fixes for the scalar/list mismatch and temporary dataset naming, so these historical counts are not a measurement of current-source failure rates.

Six independent synthetic probes reproduce issues that remain in the current source:

| Current issue | Reproduction and consequence | Source |
|---|---|---|
| Generated formula contract is unsupported | Logged TT-033 uses `expression: combined_amount + rebalance_amount`; Math_Compute never reads `expression` and returns a missing-column error | `non_llm_operators/math_compute.py:44` |
| Sort input type mismatch | `order_by: [{column: total, direction: desc}]` causes `TypeError: unhashable type: 'list'` | `llm_operators/order_by.py:48`, `:75` |
| Scalar combination reads stale input | Summing two columns separately gives two valid scalar tables, then Combine_Scalars checks the previous raw input instead of its declared measure inputs and fails | `executor.py:554`, before input selection at `:571-577` |
| Operator failures disappear from execution evidence | Math_Compute returns an error; the interpreter keeps only empty data and a row count, losing the error | `executor.py:601-605` |
| COUNT semantics are underspecified | Counting a nullable column over `[null, 5]` returns 2 instead of SQL COUNT(column)'s 1; explicit row-count and non-null-count semantics are needed | `llm_operators/filter_aggregate.py:195-219` |
| A necessary aggregate filter is deleted | A valid SUM followed by `total_amount > 1000` becomes SUM with no filter; contract_errors remains empty | `llm_operators/final_spec.py:198-204` |

The count probe establishes a semantic support gap, not a measured count of benchmark failures. The six logged crashes all say `unhashable type: 'list'`; the sorting reproduction provides a concrete matching mechanism, but the saved exceptions do not include enough stack information to prove every crash has that exact origin.

Reproduce these findings with `python experiment_week1/improvement3/diagnosis_20260912/reproduce_runtime_issues.py`. The output records source hashes and the actual versus expected behavior. The probes evaluate extracted functions with synthetic rows/fake model responses, avoiding pipeline initialization and network access.

**2. The plan sometimes changes the question before operators run**

Several incorrect successes have an identifiable early semantic error:

| Query | Required meaning from reference SQL | What the pipeline does |
|---|---|---|
| TT-058 | Deposit transactions AND Scenario-based actions AND Economic Growth scenario records | Decomposition omits Scenario-based actions entirely; returns 54 investors instead of 16, with 38 extras |
| TT-047 | Action equals Rebalance Sell | Decomposition changes it to Sell; only 7 reference investors overlap, with 42 missing and 43 extras |
| MC-007 | Group investor cash-flow averages by Investor.time_horizon | Treats time horizon as calendar year, groups by year/type, and sums; returns 12 rows instead of 4 |
| MC-015 | Compare shortfall across scenario, using both relevant sources | Retrieves only individual goals and returns 4,247 goal rows instead of 13 scenario groups |
| MC-017 | Pre-average by (investor, sector), join on both keys, then average by sector | Loses investor grain, joins only on sector, and sums allocation percentages; Automobile allocation becomes 1,655.02 instead of 13.57 |

For MC-015, the validator explicitly acknowledges that the question asks about scenario and two tables, but accepts the result because it satisfies the narrower generated specification. This is a direct failure to preserve the original requirements. Correctness relative to an incorrect generated spec does not establish correctness relative to the question.

The final validator sees only the first 10 rows for nonempty answers. It cannot establish complete entity-set equality or all numeric results from that sample. Empty list-style answers can also be accepted by a keyword/type heuristic before the normal checks. This makes propagation of runtime errors especially important: an operator failure represented as `[]` can be mistaken for a legitimate empty answer.

**3. Mandatory preaggregation changes the answer's weighting**

Processing_Spec instructs fact branches to aggregate to natural entity grain before merging. That can avoid join multiplication for some queries, but it is not a universal semantic rule.

For `WM-2T-012`, reference SQL averages goal progress across all goals in each risk-tolerance group. The pipeline first averages each investor's goals, then averages those investor averages. Investors with different goal counts get different weights in the two calculations. Recorded Aggressive-group results are 39.18 in the reference and 39.76 in the pipeline; the null group is also absent.

For an illustrative case, investor A has one goal at 0% and investor B has three goals at 100%. The average across four goals is 75%; the average of the two investors' averages is 50%. Both calculations can be appropriate, but they answer different questions. An AVG operator cannot choose the intended population by itself.

Choose the output row identity, grouping, population, and weighting globally before local processing. Where preaggregation is valid, preserve sufficient statistics such as sum and non-null count, and preserve the necessary identity keys for distinctness and joins. For this goal-level mean, final averaging should use total sum / total count, not an unweighted average of branch averages.

**4. Some rows and columns disappear before final processing can recover them**

- WM-2T-004 loses four null investment-goal groups because the relationship is mandatory in SPARQL. WM-2T-006 loses 16 groups involving null source/category for the same reason. All remaining counts match. Setting `preserve_null_groups: true` at the end cannot reconstruct discarded rows.
- At least six PARTIAL answers have exactly the correct investor-ID sets but omit reference investor names. That is an output-contract issue. Decide consistently whether names are required for "which investors" questions, then retrieve them where required.
- WM-2T-007 and WM-2T-009 have correct distinct investor sets but duplicate rows. Specify whether the output grain is one investor, one holding, or another entity.
- Some processing steps re-filter a field that Scan used but did not project. Examples include TT-036's transaction type and WM-4T-002's scenario. The branch becomes empty after successful retrieval.

Current contract checks sometimes track the union of every field ever seen, rather than the fields on the step's actual input. Grouping can remove a column while validation still believes it exists. Each operator needs a predictable output schema: for example, an aggregate yields its grouping keys plus its measures. Final projection must be checked against the terminal table.

**5. Reporting and evaluation also need correction**

The historical reporting code in `run_pipeline_v1/main.py:341-345` uses raw scan rows when the final result is empty. For WM-2T-002, WM-4T-002, TT-036, and WM-5T-003, the final intersection is empty, but the saved answer contains the last branch's nonempty data. This means grading evaluates something different from what final validation checked. Current v3 removes the raw-data fallback but still treats empty final data as absent; preserve a validated `[]` explicitly.

Twenty-one reference-answer cells across 442 are invalid JSON and exactly 32,767 characters long, consistent with Excel truncation. Five of the 55 new successes are affected. The grader also truncates answers at 60,000 characters, so five new successful result cells are not shown in full to the grader. Its explanations contain counting errors independently visible from ID-set comparisons.

Regenerate complete ground truth from the verified SQL against the intended source snapshot, store it in JSON/JSONL or another format without the cell limit, and compare structured rows deterministically. Specify projection mapping, numeric tolerances, null handling, ordering, and duplicate/set semantics. Keep an LLM for genuinely ambiguous semantic review. Do not silently discard damaged benchmark rows to raise the score.

The grader calls some GOAL-* rows fabricated, but those IDs already occur in raw scan evidence with a sourceTable value. The available logs support investigating KG/SQL population or source-scoping differences; they do not prove LLM fabrication. Reconcile the KG with the SQL source before assigning that failure to reasoning.

**What is overcomplicated, and what to retain**

The old implementation already had a planner and operators. Its generator could execute the full relational calculation in SPARQL. The modified design forbids aggregation, formulas, ranking, and multi-source retrieval in branch queries, and moves those responsibilities into separately generated processing/final specs plus a custom interpreter.

The default planner now constructs a fixed spec-first DAG; the alternate candidate-planning machinery is bypassed by default at `planner.py:73-74`. A larger operator registry therefore does not by itself create a better chosen plan. A simple lookup even passes through repeated filtering and multiple specifications that cannot add new information about the requested value.

Keep deterministic execution and explicit contracts. Reduce independent reinterpretation of the question. A preferable design to test is:

`Question + schema -> one logical plan with explicit requirements -> deterministic validation/compilation -> query engine and necessary operators -> structured comparison`

That logical plan should own exact predicates, join keys/types, output grain, grouping, metrics/weighting, nulls, distinctness, ranking, and display columns. Query_Spec, Processing_Spec, and Final_Spec can remain execution partitions of the same plan if needed; they should not independently redefine it. Use branch decomposition when its semantics and benefit are established, rather than forcing every source into a separately reasoned branch.

**A practical route toward 350/442**

1. Freeze the exact source, entrypoint, model parameters, dataset/KG snapshot, and grader for each run. `run_pipeline_improved3.py:9` currently imports `run_pipeline.main`, not `run_pipeline_v3.main`. The supplied logs say strict-contracts-v3, while current v3 defaults to answer-coverage-v5 and contains edits made after the run. Fixing a different imported package will not affect a rerun.
2. Repair deterministic interpreter defects and require the small synthetic cases above to produce correct outputs or explicit unsupported-plan errors. Do not spend full-run model calls rediscovering runtime bugs.
3. Preserve all original requirements and table-specific output schemas through one logical plan. Repair missing source fields at retrieval/planning, missing metrics at processing, and final presentation at the final stage; repeatedly regenerating the last spec cannot restore information already lost upstream.
4. Compare the existing direct/full-query path against compulsory decomposition with the same model, questions, attempts, source data, and grader. Start with representative diagnostic cases; retain the route that improves measured correctness for each query family without using ground truth at inference time.
5. Repair evaluation, then run a frozen full 442-query evaluation. Track execution rate, exact correctness, correct-ID/incomplete-projection cases, semantic failures, latency, and model calls separately. Track both newly solved questions and regressions.

Reaching 350 means 79.19% exact correctness over the full set. There is no evidence yet that a particular patch will achieve that. The current evidence does establish that adding more operators or retries is not the next useful experiment: 147 queries already have stage repairs, 462 such repair events are logged, and 49 queries repeat identical error lists at the same stage. The next gains need to come from reliable execution, preserved semantics, and sound evaluation.

Detailed evidence is in [architecture_notes.md](architecture_notes.md), [semantic_notes.md](semantic_notes.md), [statistics.json](statistics.json), and [runtime_probe_results.json](runtime_probe_results.json). Recompute recorded counts with `python experiment_week1/improvement3/diagnosis_20260912/summarize_runs.py`.
