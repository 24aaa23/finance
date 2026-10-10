# Analysis of the six completed model/context experiments

Snapshot: 6 October 2026. Scope: `ablations/v5_test1000/runs/*/*/reliability_v6_01` for GPT-OSS 120B, DeepSeek V3.2 and Gemma 3 27B IT. Each condition contains 1,000 raw rows and 1,000 grader rows. GPT-5 mini is the grader. Kimi is excluded from this six-run comparison.

Full-run accuracy and execution measurements are separate from the later 40-question measurement experiment. No pipeline outputs or grading labels were changed for this analysis.

## 1. Overall results

Accuracy is MATCH/1,000. PARTIAL is reported separately, not counted as a correct answer. Execution success means PIPELINE_SUCCESS, which does not guarantee semantic correctness.

| Model | Context | MATCH | PARTIAL | MISMATCH | Other statuses | Accuracy | Execution success |
|---|---|---:|---:|---:|---:|---:|---:|
| GPT-OSS | Without | 789 | 109 | 101 | 1 | 78.9% | 93.3% |
| GPT-OSS | With | 790 | 93 | 114 | 3 | 79.0% | 92.4% |
| DeepSeek | Without | 806 | 89 | 80 | 25 | 80.6% | 93.5% |
| DeepSeek | With | 783 | 92 | 100 | 25 | 78.3% | 90.6% |
| Gemma | Without | 613 | 82 | 292 | 13 | 61.3% | 79.6% |
| Gemma | With | 609 | 85 | 288 | 18 | 60.9% | 80.0% |

Other statuses must not be treated as one failure category. GPT-OSS with context has one GRADER_API_ERROR and two PRE_SCAN_ERROR rows. Gemma with context has six GRADER_API_ERROR, one TOKEN_OUTPUT_ERROR and eleven PRE_SCAN_ERROR rows. Gemma without context has twelve PRE_SCAN_ERROR and one OTHER row. DeepSeek without context has twenty-five PRE_SCAN_ERROR; with context has twenty-four PRE_SCAN_ERROR and one SCAN_ERROR. QuerySpec contract failures are often labelled MISMATCH by grading, so grader-label counts alone do not identify execution failures.

DeepSeek without context has the highest observed match rate. Its advantage over GPT-OSS without context is 17 questions, or 1.7 percentage points. This is an observed ranking from one run per condition, not proof of a stable population-level superiority. Gemma's gap is much larger: 19.3 percentage points below DeepSeek without context.

The unresolved grading errors can move GPT-OSS with context from 79.0% to at most 79.1%, and Gemma with context from 60.9% to at most 61.6%. These are bounds, not predictions. Gemma's small negative context effect is therefore provisional; the large model gap is not explained by those errors.

## 2. Context changes individual answers more than aggregate accuracy suggests

| Model | New matches with context | Matches lost with context | Both conditions match | Net match change |
|---|---:|---:|---:|---:|
| GPT-OSS | 67 | 66 | 723 | +1 |
| DeepSeek | 68 | 91 | 715 | -23 |
| Gemma | 22 | 26 | 587 | -4 |

GPT-OSS's essentially unchanged aggregate accuracy hides 133 questions that changed between MATCH and non-MATCH. Context is not simply adding one useful answer; it coincides with substantial turnover. DeepSeek improves 68 questions but loses 91. Gemma changes fewer questions, consistent with a weaker observed intervention and persistent underlying failures.

These transitions cannot all be attributed causally to context. Independent generation, execution variation and grader judgments can change results. A repeated no-context control and multiple seeds/runs are needed to separate that variation from the context intervention. All conditions use the same questions, so paired question-level analysis is more informative than comparing aggregate percentages alone.

## 3. The current context experiment is a terminology experiment

Startup logs and cached reviews show:

| Model | Candidates | Active entries | Active content |
|---|---:|---:|---|
| GPT-OSS | 42 | 4 | Investment goal, category, investment type, sector terminology |
| DeepSeek | 37 | 5 | Asset categories, customer segments, investment goals, investment types, sectors |
| Gemma | 12 | 1 | Investment-goal terminology |

All active entries are terminology. The `phase0_business_rules.md` document is quarantined as evaluation-scoped and excluded from preparation and inference. Operational and computational candidates are not active in these configurations.

Therefore, the results do not establish that validated business rules fail to help. They establish that this model-specific, automatically prepared terminology context does not consistently improve aggregate performance. The amount and content of active context also vary between models. The experiment jointly varies the answering model and its context-preparation quality; it does not give every model an identical approved context pack.

One plausible reason for the weak benefit is that many queries already state their categories and thresholds explicitly, while the active entries do not resolve staged averages, signed cash-flow semantics, population ownership or aggregation grain. This is an interpretation supported by the active content and observed errors, not a quantified causal finding.

## 4. Performance depends strongly on query type

Each cell below is the match percentage without context / with context. Query-type labels and source-sheet labels are distinct; a multi-step sheet can contain several query types.

| Query type | Questions | GPT-OSS | DeepSeek | Gemma |
|---|---:|---:|---:|---:|
| Direct Retrieval | 34 | 100.0 / 94.1 | 97.1 / 100.0 | 100.0 / 100.0 |
| Multi-Relational | 212 | 92.9 / 90.6 | 90.1 / 90.6 | 79.2 / 77.8 |
| Categorical Aggregation | 212 | 85.4 / 82.1 | 87.7 / 85.4 | 76.9 / 77.8 |
| Composite Reasoning | 143 | 65.7 / 74.8 | 64.3 / 59.4 | 46.2 / 47.6 |
| Filtered List | 103 | 78.6 / 77.7 | 78.6 / 72.8 | 52.4 / 50.5 |
| Ranking | 65 | 90.8 / 90.8 | 84.6 / 81.5 | 60.0 / 55.4 |
| Multi-step Comparative | 55 | 23.6 / 27.3 | 69.1 / 65.5 | 25.5 / 23.6 |
| Exception Detection | 53 | 90.6 / 88.7 | 88.7 / 84.9 | 43.4 / 45.3 |
| Temporal | 40 | 92.5 / 82.5 | 92.5 / 87.5 | 25.0 / 25.0 |
| Reference Compliance | 39 | 56.4 / 53.8 | 43.6 / 46.2 | 38.5 / 38.5 |
| Rule-Based Detection | 29 | 62.1 / 75.9 | 72.4 / 72.4 | 79.3 / 79.3 |
| Comparative | 15 | 33.3 / 53.3 | 53.3 / 53.3 | 26.7 / 26.7 |

Direct retrieval is strong for all models. The largest practical weaknesses appear when the question requires several semantic decisions, especially multi-step comparison, reference compliance and composite reasoning.

DeepSeek's multi-step comparative advantage is substantial: 38/55 matches without context, versus 13 for GPT-OSS and 14 for Gemma. GPT-OSS is stronger on some other categories, including ranking and exception detection. Model suitability cannot be reduced to parameter count or one aggregate accuracy.

Gemma's temporal result is particularly weak: 10/40 matches in both conditions. This identifies temporal specification and computation as a targeted diagnostic area, but does not by itself prove that every temporal failure is a date-filter error.

Context effects are uneven. GPT-OSS composite reasoning improves from 94 to 107 matches, while categorical aggregation falls from 181 to 174 and temporal queries from 37 to 33. DeepSeek does not show an aggregate improvement across these difficult categories. Small categories such as Comparative have too few questions for strong general conclusions.

The dedicated multi-step comparative source sheet also performs poorly: GPT-OSS 49/125 and 53/125; DeepSeek 76/125 and 71/125; Gemma 27/125 and 24/125. Thus the weak multi-step performance is visible under two different benchmark groupings.

## 5. Expert questions remain a major limitation

| Model | Expert matches without context | Expert matches with context |
|---|---:|---:|
| GPT-OSS | 59/127 (46.5%) | 67/127 (52.8%) |
| DeepSeek | 78/127 (61.4%) | 70/127 (55.1%) |
| Gemma | 37/127 (29.1%) | 40/127 (31.5%) |

The system's overall match rate hides much weaker performance on Expert questions. Difficulty labels are not perfectly monotonic: Advanced and Hard groups need not have the same composition. The appropriate claim is that the Expert group is a consistent weakness, rather than that every increase in labelled difficulty produces a fixed decline.

## 6. Execution reliability and answer correctness are separate bottlenecks

| Model | Context | QuerySpec contract failures | Other raw failures | Executed but not MATCH | MATCH among successful executions |
|---|---|---:|---:|---:|---:|
| GPT-OSS | Without | 66 | 1 | 144 | 84.6% |
| GPT-OSS | With | 73 | 3 | 134 | 85.5% |
| DeepSeek | Without | 40 | 25 | 129 | 86.2% |
| DeepSeek | With | 69 | 25 | 123 | 86.4% |
| Gemma | Without | 192 | 12 | 183 | 77.0% |
| Gemma | With | 189 | 11 | 191 | 76.1% |

Executed-but-not-MATCH includes unresolved grading errors; it is not synonymous with proven incorrectness. Likewise, conditional match rates select a different set of successful questions in each condition.

QuerySpec contract failures dominate raw failures, particularly for Gemma. They occur before useful database execution and usually at Q1. This suggests that source/field grounding, structured-spec compatibility and semantic interpretation need attention before simply adding more query-generation retries.

DeepSeek with context loses 29 successful executions while QuerySpec failures increase from 40 to 69. Its match rate conditional on successful execution is nearly unchanged. The observed context regression is therefore concentrated in the ability to produce executable plans/specifications, rather than a broad decline in the correctness of successfully executed answers. This decomposition is descriptive; it does not establish why the context caused any particular failure.

Fixing every execution failure would not guarantee a match: repaired queries could still use the wrong population, aggregation or identity. Success rates should never be used as substitutes for accuracy.

## 7. Concrete semantic error patterns

The reviewed rows support several recurring mechanisms. They are examples, not an exhaustive frequency-coded taxonomy.

**Population ownership.** In GPT-OSS WM125-2T-026, the question selects investors by their stated Retirement Planning goal and asks for an average of per-investor goal progress. The pipeline returns 18.0522 versus the reference 41.34. Prior read-only replay traced the problem to also filtering goal records by goal type, narrowing the population of records being averaged. The distinction between a profile attribute and a child-record attribute matters even when both have similar names.

**Aggregation grain and staged computation.** Gemma WM125-2T-028 and WM125-2T-029 return many rows whose investor_count is one, instead of a single total count of 746 or 740. The underlying problem is output/aggregation grain. A valid COUNT expression does not make the whole query semantically correct if grouping remains at investor level. Other questions require average-of-investor-averages, which differs from averaging all goal rows directly.

**Duplicate entities.** GPT-OSS WM125-3T-023 and WM125-3T-026 receive PARTIAL judgments because qualifying investors appear more than once. One validation trace explicitly reports duplicate investor keys while the result is still retained. Entity-list questions need uniqueness at the requested entity grain, without indiscriminately deduplicating questions that ask for separate events or holdings.

**Signed amounts and financial definitions.** The earlier audit of these runs identified transaction cases where generated CASE expressions re-signed amounts already stored with signs, or subtracted signed outflows incorrectly. These are metric-definition errors. They require source-backed semantics, not benchmark-specific exceptions.

**Validation of the wrong specification.** Several incorrect results have pre-scan validation describing the query as valid and post-scan validation reporting that output shape matches QuerySpec. A query can faithfully implement an incorrect QuerySpec. Agreement between generated specification and generated query is insufficient evidence that the original question was answered.

**Evaluation reliability.** Earlier read-only audits found some PARTIAL examples with matching ID sets or even full row multisets, including long outputs. Not every PARTIAL can be treated as a true semantic error. These cases require separate evidence checks; they do not justify changing saved labels or assuming all partial answers are correct. The grader remains unchanged.

## 8. These runs mainly exercise SQL

Recorded node backends show:

| Model | Context | SQL-only plans | KG-only plans | Plans containing both SQL and KG |
|---|---|---:|---:|---:|
| GPT-OSS | Without | 859 | 128 | 13 |
| GPT-OSS | With | 869 | 124 | 7 |
| DeepSeek | Without | 973 | 18 | 9 |
| DeepSeek | With | 977 | 14 | 9 |
| Gemma | Without | 1,000 | 0 | 0 |
| Gemma | With | 1,000 | 0 | 0 |

SQL-only here includes SQL plans with set operators but no KG nodes. These counts describe planned/recorded backend choices, including failed nodes, not proof that every planned backend executed.

The SQL database and KG are representations of the same underlying data, so a SQL-only answer can be legitimate. However, an aggregate match rate dominated by SQL does not demonstrate effective SQL–KG composition. Backend selection differs by model, meaning that the comparison also includes planning/routing differences. A targeted hybrid subset and backend/decomposition ablations are needed to substantiate architecture-specific claims.

## 9. Runtime and cost

Full-run mean question elapsed time and execution efficiency use all 1,000 rows, including failures. Efficiency uses MATCH divided by summed question elapsed time; it is not wall-clock throughput under four workers.

| Model | Context | Full-run mean seconds/question | Correct answers / summed execution second |
|---|---|---:|---:|
| GPT-OSS | Without | 33.111 | 0.02383 |
| GPT-OSS | With | 34.112 | 0.02316 |
| DeepSeek | Without | 46.191 | 0.01745 |
| DeepSeek | With | 49.731 | 0.01575 |
| Gemma | Without | 53.177 | 0.01153 |
| Gemma | With | 67.743 | 0.00899 |

Context raises full-run mean elapsed time by approximately 3.0% for GPT-OSS, 7.7% for DeepSeek and 27.4% for Gemma. The measurements do not isolate the cause: model retries, backend choices and endpoint conditions also vary. Gemma's smaller size does not translate into lower observed end-to-end latency.

The separate 40-question samples estimate cost/query at $0.006118/$0.006992 for GPT-OSS, $0.010716/$0.008587 for DeepSeek and $0.008071/$0.008030 for Gemma, without/with context. These use the user's cross-provider input/output prices, not verified incurred AWS charges. They exclude grading and observed startup preparation; cached preparation does not reveal the earlier preparation cost.

Sample request latency/output-token estimates are 27.340/7.547 ms for GPT-OSS, 22.012/72.080 ms for DeepSeek and 20.649/22.513 ms for Gemma. GPT-OSS without context and DeepSeek with context each contain four roughly 600-second stalls. Their latency estimates are contaminated by those delays and should be remeasured or explicitly reported as observed request latency including stalls. Filtering out those requests gives sensitivity values of 7.913 and 21.497 ms/token, but those values must not silently replace the original measurements.

Gemma's samples do not show that stall pattern. Nevertheless, non-streaming request time includes network overhead, prompt processing and queueing. None of these measurements is pure token decoding time. The 40-question sample is weighted by query type, and bootstrap intervals quantify sampling variation, not endpoint or pricing uncertainty.

## 10. Limitations and appropriate claims

1. One full run per model/context condition cannot establish stability or causal context effects. Generative variation and grader variation remain confounded.
2. There are eight unresolved grader API/token errors across two conditions. Small context differences remain provisional.
3. PARTIAL is not a numerical accuracy contribution, and no F1 metric follows from these labels without a separate precision/recall definition.
4. The benchmark is one 1,000-question wealth-management dataset with unequal query-type counts. These runs do not establish transfer to an unseen enterprise domain.
5. Active context is sparse terminology, not a full independent operational-rule pack. Context content is model-specific.
6. The KG is derived from SQL, and few plans use both backends. This is not a benchmark of two independent knowledge sources.
7. There is no matched no-decomposition control in these six runs. They cannot establish the isolated benefit of decomposition, orchestration or deterministic compilers.
8. These results do not compare Improvement 6 under the same model, database, queries and grader. Historical results obtained with another grader are not controlled comparisons.
9. Validation can miss semantic errors or retain results with warnings. Executability and output-shape validity are weaker than correctness.
10. Timing includes endpoint effects, and measured token usage/cost comes from a later sample. Cloud-hosted open-weight inference does not by itself establish local data privacy.
11. Development has repeatedly used this dataset for error analysis. It should be described as a development benchmark; final generalization claims require a separately held-out evaluation.

## 11. Priorities supported by the evidence

First, resolve the remaining grading errors and retain the existing scoring policy. Second, improve QuerySpec grounding and contract compatibility using physical schema evidence and typed interfaces; preserve validation rather than accepting unsupported specifications. Third, make population, row grain, uniqueness, signed-amount semantics and staged aggregation explicit and inspectable before generation. Fourth, test source-backed business definitions in a separate approved context condition, distinct from terminology. Do not integrate evaluation-scoped corrections as runtime rules.

For efficiency, skip model reviews only where deterministic checks cover the relevant failure mode, and verify that this preserves correctness. More concurrency or more repair calls alone are not supported as solutions by the current measurements. For the paper, add targeted hybrid examples, decomposition/backend ablations and repeated runs rather than attributing all accuracy to the architecture.

The defensible interpretation is that the pipeline achieves approximately 79–81% full matches with GPT-OSS and DeepSeek on this development benchmark, but performance depends strongly on query complexity and structured-spec reliability. Gemma is substantially weaker. The current terminology context does not consistently improve the system. The largest remaining opportunities are semantic specification and validation, not simply executing more queries successfully.
