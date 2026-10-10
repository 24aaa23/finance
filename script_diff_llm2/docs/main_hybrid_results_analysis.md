# Main hybrid pipeline: results, findings and limitations

Snapshot: 8 October 2026. These reports analyze existing completed experiments; no raw answers or grader labels were modified. Accuracy means full MATCH divided by all 1,000 benchmark questions; PARTIAL does not count as a match. PIPELINE_SUCCESS means operational execution, not semantic correctness. Grader 2 using GPT-5 mini is the common evaluation basis. Other labels include execution and grading failures and are not one homogeneous category. Current incomplete Azure experiments and the newly added decomposition retries are outside this analysis.

## 1. Scope and architecture

This analysis uses the six completed `reliability_v6_01` experiments: GPT-OSS, DeepSeek and Gemma, each without and with context. Kimi's with-context run is incomplete and the Qwen hybrid outputs have no completed grader-2 report in this comparison; neither is treated as a complete accuracy experiment.

The main pipeline forms a question-dependent DAG of backend subqueries and set operations. Node-local QuerySpec defines the requested computation; SQL/SPARQL performs node calculations, and bindings/set operators coordinate results. Unlike Improvement10's final Python composition plan, much computation is pushed into a backend query. The KG is derived from the same SQL database, so these are alternative representations of shared data.

These historical runs predate the newly implemented three decomposition repairs. Their results cannot be used to claim those repairs improved accuracy. The newer Azure SQL-only and baseline-derived hybrid runs are different, still incomplete experiments.

## 2. Overall performance

| Model | Condition | MATCH | PARTIAL | MISMATCH | Other labels | Match rate | Execution success |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-OSS 120B | without context | 789 | 109 | 101 | 1 | 78.9% | 93.3% |
| GPT-OSS 120B | with context | 790 | 93 | 114 | 3 | 79.0% | 92.4% |
| DeepSeek V3.2 | without context | 806 | 89 | 80 | 25 | 80.6% | 93.5% |
| DeepSeek V3.2 | with context | 783 | 92 | 100 | 25 | 78.3% | 90.6% |
| Gemma 3 27B IT | without context | 613 | 82 | 292 | 13 | 61.3% | 79.6% |
| Gemma 3 27B IT | with context | 609 | 85 | 288 | 18 | 60.9% | 80.0% |

DeepSeek without context has the highest observed match rate, 80.6%. GPT-OSS remains near 79% in both conditions. Gemma reaches roughly 61%, materially below the larger models. DeepSeek's lead over GPT-OSS without context is 17 questions; without repeated runs this small gap should not be described as stable superiority.

The 1,000-row reports contain one grader API error for GPT-OSS with context and six grader API errors plus one token-output error for Gemma with context. Even if all seven Gemma grading failures became matches, its with-context rate would only rise to 61.6%. Execution failures are included in the denominator; percentages do not silently discard hard questions.

## 3. Context effect: turnover rather than consistent improvement

| Model | New MATCH with context | Lost MATCH with context | Both MATCH | Net change |
| --- | --- | --- | --- | --- |
| GPT-OSS 120B | 67 | 66 | 723 | 1 |
| DeepSeek V3.2 | 68 | 91 | 715 | -23 |
| Gemma 3 27B IT | 22 | 26 | 587 | -4 |

GPT-OSS gains 67 matches and loses 66, producing an almost unchanged total while 133 question outcomes change. DeepSeek gains 68 and loses 91; Gemma gains 22 and loses 26. Context is therefore not consistently improving this benchmark. Independent generation and grader variation also contribute, so these transitions are associations, not proof that each change was caused by context.

The actual active context matters: previously inspected run states show four GPT-OSS terminology entries, five DeepSeek entries and one Gemma entry. Operational formulas/defaults were not automatically active, and phase0_business_rules.md was quarantined as evaluation-scoped. This is chiefly an experiment with model-specific terminology, not a complete business-rule integration experiment.

Sparse terminology can help map a phrase to the right field, but it does not necessarily establish signed-amount meaning, average-of-averages, entity uniqueness or a multi-stage metric definition. This is a plausible explanation for weak aggregate gains, not a measured causal attribution. Different preparation models also produce different packs, confounding answering capability with context preparation.

## 4. Query-type and difficulty trends

The following table shows without-context / with-context match rates.

| Query type | Questions | GPT-OSS 120B | DeepSeek V3.2 | Gemma 3 27B IT |
| --- | --- | --- | --- | --- |
| Direct Retrieval | 34 | 100.0% / 94.1% | 97.1% / 100.0% | 100.0% / 100.0% |
| Multi-Relational | 212 | 92.9% / 90.6% | 90.1% / 90.6% | 79.2% / 77.8% |
| Categorical Aggregation | 212 | 85.4% / 82.1% | 87.7% / 85.4% | 76.9% / 77.8% |
| Composite Reasoning | 143 | 65.7% / 74.8% | 64.3% / 59.4% | 46.2% / 47.6% |
| Filtered List | 103 | 78.6% / 77.7% | 78.6% / 72.8% | 52.4% / 50.5% |
| Rule-Based Detection | 29 | 62.1% / 75.9% | 72.4% / 72.4% | 79.3% / 79.3% |
| Exception Detection | 53 | 90.6% / 88.7% | 88.7% / 84.9% | 43.4% / 45.3% |
| Comparative | 15 | 33.3% / 53.3% | 53.3% / 53.3% | 26.7% / 26.7% |
| Ranking | 65 | 90.8% / 90.8% | 84.6% / 81.5% | 60.0% / 55.4% |
| Multi-step Comparative | 55 | 23.6% / 27.3% | 69.1% / 65.5% | 25.5% / 23.6% |
| Reference Compliance | 39 | 56.4% / 53.8% | 43.6% / 46.2% | 38.5% / 38.5% |
| Temporal | 40 | 92.5% / 82.5% | 92.5% / 87.5% | 25.0% / 25.0% |

Direct retrieval is strong for all three models, including Gemma. The difficult categories involve more semantic decisions: composite reasoning, multi-step comparisons and reference compliance. DeepSeek matches 38/55 multi-step comparative questions without context, compared with GPT-OSS 13/55 and Gemma 14/55. GPT-OSS is relatively stronger on ranking and exception detection.

Context helps some categories and hurts others. GPT-OSS composite reasoning increases from 94 to 107 matches, while categorical aggregation falls from 181 to 174 and temporal from 37 to 33. There is no general conclusion that context helps harder questions. Gemma remains at 10/40 temporal matches in both conditions. The query type identifies where to investigate, not the specific cause of every error.

| Model | Expert without context / 127 | Expert with context / 127 |
| --- | --- | --- |
| GPT-OSS 120B | 59 (46.5%) | 67 (52.8%) |
| DeepSeek V3.2 | 78 (61.4%) | 70 (55.1%) |
| Gemma 3 27B IT | 37 (29.1%) | 40 (31.5%) |

Expert questions remain materially weaker than the aggregate rate. Difficulty labels need not be monotonic because their query-type compositions differ; the evidence supports an Expert-group weakness, not a fixed accuracy penalty for every increase in difficulty.

## 5. Execution failures versus wrong executable answers

| Model | Condition | QuerySpec contract failures | Other raw failures | Executed but not MATCH | MATCH among executed |
| --- | --- | --- | --- | --- | --- |
| GPT-OSS 120B | without context | 66 | 1 | 144 | 84.6% |
| GPT-OSS 120B | with context | 73 | 3 | 134 | 85.5% |
| DeepSeek V3.2 | without context | 40 | 25 | 129 | 86.2% |
| DeepSeek V3.2 | with context | 69 | 25 | 123 | 86.4% |
| Gemma 3 27B IT | without context | 192 | 12 | 183 | 77.0% |
| Gemma 3 27B IT | with context | 189 | 11 | 191 | 76.1% |

Gemma's contract failures dominate its execution losses: 192 without context and 189 with context. GPT-OSS has 66/73 such failures and DeepSeek 40/69. A contract failure prevents useful execution; it is different from an executed result graded wrong. GPT-OSS with context has an additional node exception, so its 74 DAG_NODE_ERROR labels are not all QuerySpec contract failures.

DeepSeek loses 29 successful executions with context, exactly alongside the increase from 40 to 69 contract failures; its conditional match rate stays near 86.3%. The observed regression is concentrated in executable specification formation, rather than a large collapse in correctness among executed answers. This arithmetic is descriptive and does not establish why context caused a failure.

## 6. Semantic error patterns

Previously inspected rows and current stage statistics support these mechanisms:

- **Population ownership:** filtering investor profiles by stated goal is not equivalent to filtering all child goal records by that goal type. GPT-OSS WM125-2T-026 illustrates narrowing the records averaged beyond the intended population.
- **Aggregation grain:** counting qualifying rows, counting distinct investors and counting one per grouped investor produce different answers. Gemma's WM125-2T-028/029 examples return investor_count=1 across many rows rather than one total count.
- **Staged measures:** averaging investor-level averages differs from averaging all child rows. Ratios, normalization and ranking can also require explicitly ordered stages.
- **Duplicates:** GPT-OSS WM125-3T-023/026 partial outputs include repeated investor keys. DISTINCT must follow the requested answer grain; indiscriminate deduplication would be wrong for event-level answers.
- **Signed amounts:** re-signing already signed cash flows or subtracting signed outflows can change totals. Definitions need source support rather than question-specific patches.
- **Validation of a mistaken specification:** a query can pass pre-scan validation and return rows matching QuerySpec while QuerySpec itself misrepresents the question. Shape agreement is weaker than semantic correctness.

These are examples, not exhaustive causal counts. Grader explanations also require scrutiny: earlier audits found some partial judgments despite matching entity sets or row multisets. Long outputs, ordering and reference formatting can affect model evaluation. This does not justify relabelling partials wholesale.

## 7. How much hybrid composition actually happens

| Model | Condition | SQL only | KG only | Both SQL and KG | Single-node plans |
| --- | --- | --- | --- | --- | --- |
| GPT-OSS 120B | without context | 859 | 128 | 13 | 987 |
| GPT-OSS 120B | with context | 869 | 124 | 7 | 993 |
| DeepSeek V3.2 | without context | 973 | 18 | 9 | 950 |
| DeepSeek V3.2 | with context | 977 | 14 | 9 | 941 |
| Gemma 3 27B IT | without context | 1000 | 0 | 0 | 999 |
| Gemma 3 27B IT | with context | 1000 | 0 | 0 | 1000 |

Most recorded plans use SQL, and most contain a single node. Gemma's plans are all SQL; GPT-OSS uses both backends on only 13/7 questions and DeepSeek on 9/9. These are recorded plans, including failed execution, not a guarantee that every backend completed.

A single node is legitimate when one backend can answer the whole question, especially because the KG is derived from SQL. However, these aggregate scores provide limited evidence of successful cross-backend composition. They do not demonstrate that decomposition into multiple agents caused the accuracy advantage.

Historical logs recorded 324/294 fallback events for GPT-OSS, 29/28 for DeepSeek and 3/3 for Gemma, without/with context. Some logs contain resumed attempts, so these are events, not exact unique-query counts. Empty/rejected decompositions do not necessarily mean malformed DAG topology: scope checks can reject proposals before DAG construction. The newly added retry loop addresses those rejected plans; it has not yet been evaluated in the completed runs analyzed here.

## 8. Runtime and measurement limits

| Model | Condition | Mean seconds/question | MATCH / summed execution second |
| --- | --- | --- | --- |
| GPT-OSS 120B | without context | 33.111 | 0.023829 |
| GPT-OSS 120B | with context | 34.112 | 0.023159 |
| DeepSeek V3.2 | without context | 46.191 | 0.017449 |
| DeepSeek V3.2 | with context | 49.731 | 0.015745 |
| Gemma 3 27B IT | without context | 53.177 | 0.011527 |
| Gemma 3 27B IT | with context | 67.743 | 0.008990 |

Context increases recorded mean elapsed time by about 3.0% for GPT-OSS, 7.7% for DeepSeek and 27.4% for Gemma. The data do not separate added prompt processing, different node plans, repairs and endpoint variation. Gemma is not the fastest simply because it is smaller.

The historical full hybrid CSVs do not contain model token usage or generation-only timing. Their absent token columns are missing measurements, not zero usage. Later 40-question measurements are samples, not full-run totals; some contained approximately 600-second request stalls. They should not be compared directly to Improvement10's full-run token telemetry as though both were identical measurements. The existing [six-run analysis](six_run_results_analysis.md) gives those sample estimates and sensitivity caveats.

Efficiency here is MATCH divided by summed question elapsed time, following the specified definition. It does not measure wall-clock throughput under parallel workers, and excludes grading and startup context compilation.

## 9. Limitations and defensible findings

The main constraints are one run per condition, one repeatedly analyzed development dataset, sparse/model-dependent context, unresolved grading errors, unequal category sizes, no clean causal decomposition control and few genuinely mixed-backend plans. The composition interface passes values/columns and entity sets; it is not a general arbitrary cross-backend row-join engine. Complicated measures still rely on correctly generated SQL/SPARQL or supported compiler patterns.

No unseen-domain transfer, universal financial-database support or privacy guarantee follows from these results. The KG and SQL share source data, and cloud-hosted open weights still transmit prompts to a provider. Improvement10 context-provenance problems should not be transferred automatically to the main pipeline, but repeated benchmark-driven development also limits held-out generalization claims for the main pipeline.

The evidence supports strong observed accuracy for GPT-OSS and DeepSeek, substantial dependence on query type and specification reliability, a large Gemma gap, and no consistent aggregate benefit from the current terminology context. The priorities are correct population/grain/staged semantics, typed specification reliability and evaluation stability. Additional DAG repairs are a reasonable experiment, not an established improvement.

## Artifact provenance

Counts were recomputed by `analysis/completed_experiments_20261008/summarize.py`. Input file hashes, detailed status counts, per-type counts and paired transitions are saved in `analysis/completed_experiments_20261008/summary.json`.

- main_hybrid/deepseek_v3_2/with_context: [raw](../ablations/v5_test1000/runs/deepseek_v3_2/with_context/reliability_v6_01/raw_pipeline.csv) and [grader 2](../ablations/v5_test1000/runs/deepseek_v3_2/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv).
- main_hybrid/deepseek_v3_2/without_context: [raw](../ablations/v5_test1000/runs/deepseek_v3_2/without_context/reliability_v6_01/raw_pipeline.csv) and [grader 2](../ablations/v5_test1000/runs/deepseek_v3_2/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv).
- main_hybrid/gemma_3_27b_it/with_context: [raw](../ablations/v5_test1000/runs/gemma_3_27b_it/with_context/reliability_v6_01/raw_pipeline.csv) and [grader 2](../ablations/v5_test1000/runs/gemma_3_27b_it/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv).
- main_hybrid/gemma_3_27b_it/without_context: [raw](../ablations/v5_test1000/runs/gemma_3_27b_it/without_context/reliability_v6_01/raw_pipeline.csv) and [grader 2](../ablations/v5_test1000/runs/gemma_3_27b_it/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv).
- main_hybrid/gpt_oss_120b/with_context: [raw](../ablations/v5_test1000/runs/gpt_oss_120b/with_context/reliability_v6_01/raw_pipeline.csv) and [grader 2](../ablations/v5_test1000/runs/gpt_oss_120b/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv).
- main_hybrid/gpt_oss_120b/without_context: [raw](../ablations/v5_test1000/runs/gpt_oss_120b/without_context/reliability_v6_01/raw_pipeline.csv) and [grader 2](../ablations/v5_test1000/runs/gpt_oss_120b/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv).
