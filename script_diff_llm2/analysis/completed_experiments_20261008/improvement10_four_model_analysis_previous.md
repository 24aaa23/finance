# Improvement10: results, findings and limitations

Snapshot: 8 October 2026. These reports analyze existing completed experiments; no raw answers or grader labels were modified. Accuracy means full MATCH divided by all 1,000 benchmark questions; PARTIAL does not count as a match. PIPELINE_SUCCESS means operational execution, not semantic correctness. Grader 2 using GPT-5 mini is the common evaluation basis. Other labels include execution and grading failures and are not one homogeneous category. Current incomplete Azure experiments and the newly added decomposition retries are outside this analysis.

## 1. What this experiment tests

Improvement10 is a domain-conditioned SQL pipeline. Its original workflow combines query understanding, retrieval-oriented specifications/decomposition, SQL retrieval, intermediate processing and a Python Final Spec for final composition/calculation. An agent compiles the supplied domain prompt, business-rules addendum and table YAML documents; consultation can also access original documents. All four model experiments use context. There is no completed Improvement10 without-context control in this comparison.

The original snapshot is commit `9ce5a6d99c96f3c17dda0b98ec8edc0c11bd2380`. Model/provider and path adapters are external. These are the existing `run_01/parallel_workers4` results, not the newer Improvement10/11 hybrid derivative.

## 2. Overall performance

| Model | Condition | MATCH | PARTIAL | MISMATCH | Other labels | Match rate | Execution success |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-OSS 120B | with context | 781 | 127 | 87 | 5 | 78.1% | 97.4% |
| DeepSeek V3.2 | with context | 744 | 155 | 97 | 4 | 74.4% | 93.9% |
| Gemma 3 27B IT | with context | 319 | 91 | 585 | 5 | 31.9% | 53.0% |
| Qwen3 Coder 480B | with context | 704 | 127 | 140 | 29 | 70.4% | 90.7% |

GPT-OSS is the strongest aggregate model here, followed by DeepSeek, Qwen and Gemma. The gap is 3.7 percentage points between GPT-OSS and DeepSeek, 7.7 points between GPT-OSS and Qwen, and 46.2 points between GPT-OSS and Gemma. This describes these runs, not intrinsic model capability or an effect of parameter count alone.

Grading remains incomplete in a narrower sense: every output contains 1,000 rows, but 5 GPT-OSS, 4 DeepSeek, 2 Gemma and 22 Qwen rows have GRADER_API_ERROR. If every unresolved API-error row became a match, the respective upper bounds would be 78.6%, 74.8%, 32.1% and 72.6%. These bounds leave the aggregate ranking unchanged. OTHER and CRASH are separate statuses and are not assumed recoverable grading errors.

## 3. Execution reliability and semantic correctness

| Model | Executed | Final Spec failures | QuerySpec failures | Decomposition failures | Crashes | MATCH among executed |
| --- | --- | --- | --- | --- | --- | --- |
| GPT-OSS 120B | 974 | 26 | 0 | 0 | 0 | 80.2% |
| DeepSeek V3.2 | 939 | 60 | 1 | 0 | 0 | 79.1% |
| Gemma 3 27B IT | 530 | 429 | 35 | 6 | 0 | 60.2% |
| Qwen3 Coder 480B | 907 | 85 | 0 | 2 | 6 | 77.6% |

Final Spec is the major execution bottleneck. Gemma fails there on 429 questions, and on another 41 at QuerySpec/decomposition. Even a simple retrieval can fail because the generated processing plan uses invalid dataset names, unsupported operations or fields that were not preserved in intermediate datasets. This is a structured-plan compatibility problem, not evidence that Gemma cannot retrieve a name from SQL.

GPT-OSS executes 97.4% of questions, but only 80.2% of those executions receive MATCH. For this model, most remaining loss is in the meaning, population or output of executable plans. DeepSeek and Qwen also have substantial executed-but-not-matching outputs. A successful Python plan can still implement the wrong calculation.

Gemma has two bottlenecks: 47% of queries do not execute successfully, and only 60.2% of successful executions match. Fixing plan validity alone would not remove all its errors. Conditional rates include unresolved grading errors and select different successful subsets for each model.

## 4. Query-type trends

| Query type | Questions | GPT-OSS 120B | DeepSeek V3.2 | Gemma 3 27B IT | Qwen3 Coder 480B |
| --- | --- | --- | --- | --- | --- |
| Direct Retrieval | 34 | 94.1% | 100.0% | 5.9% | 76.5% |
| Multi-Relational | 212 | 83.5% | 71.2% | 40.6% | 65.6% |
| Categorical Aggregation | 212 | 81.6% | 86.8% | 48.1% | 79.2% |
| Composite Reasoning | 143 | 71.3% | 55.9% | 11.9% | 64.3% |
| Rule-Based Detection | 29 | 82.8% | 72.4% | 44.8% | 79.3% |
| Filtered List | 103 | 81.6% | 76.7% | 37.9% | 63.1% |
| Exception Detection | 53 | 90.6% | 86.8% | 9.4% | 81.1% |
| Comparative | 15 | 46.7% | 66.7% | 13.3% | 66.7% |
| Ranking | 65 | 95.4% | 93.8% | 56.9% | 76.9% |
| Multi-step Comparative | 55 | 25.5% | 36.4% | 1.8% | 54.5% |
| Reference Compliance | 39 | 64.1% | 48.7% | 12.8% | 48.7% |
| Temporal | 40 | 82.5% | 97.5% | 25.0% | 97.5% |

Straightforward tasks are not uniformly easy across models. DeepSeek answers all 34 direct-retrieval questions correctly, and GPT-OSS answers 32. Gemma answers only two, with inspected failures showing Final Spec/schema errors. Thus complexity of the orchestration contract can dominate simplicity of the user's question.

Ranking is a relative strength: GPT-OSS matches 62/65 and DeepSeek 61/65. A plausible explanation is that a well-defined metric, sort direction and limit provide a clearer execution target than a multi-stage comparison. This is an interpretation; the table alone does not identify the cause.

Multi-step comparative questions are a persistent weakness: GPT-OSS matches 14/55, DeepSeek 20/55, Qwen 30/55 and Gemma 1/55. They demand correct population selection, intermediate grain and ordered computations. More individually plausible steps create more opportunities to lose fields or change aggregation meaning. Qwen leads this category despite ranking below GPT-OSS overall.

Temporal questions show another specialization: DeepSeek and Qwen each match 39/40, GPT-OSS 33/40 and Gemma 10/40. Reference compliance is less reliable across all models. Small categories, particularly the 15-question Comparative group, should not support broad population-level conclusions.

## 5. Expert questions and partial answers

| Model | Expert MATCH / 127 | Expert match rate | Expert PARTIAL |
| --- | --- | --- | --- |
| GPT-OSS 120B | 64 | 50.4% | 42 |
| DeepSeek V3.2 | 53 | 41.7% | 55 |
| Gemma 3 27B IT | 5 | 3.9% | 16 |
| Qwen3 Coder 480B | 75 | 59.1% | 20 |

Qwen has the highest Expert match rate, 59.1%, although GPT-OSS has the highest overall rate. GPT-OSS reaches 50.4%, DeepSeek 41.7% and Gemma 3.9%. Aggregate accuracy therefore conceals substantial model specialization and severe difficulty-specific failure.

DeepSeek has 155 PARTIAL labels, more than its 97 MISMATCH labels. Many partial outputs may be nearer a complete answer, but PARTIAL is not a calibrated measure of distance from correctness. Inspected grader explanations repeatedly mention duplicate investors and missing requested fields. In other cases the correct row appears among unrelated rows. These errors suggest entity grain, filter placement and projection completeness as useful diagnostic targets.

## 6. Concrete failure mechanisms

These examples are evidence-backed illustrations, not a frequency-coded taxonomy:

- **Lost fields between stages:** Qwen's WM125-1T-002 fails because final projection references risk_tolerance/time_horizon absent from the selected input. Gemma's WM125-1T-001 also combines invalid dataset naming with a missing investor_name field.
- **Incorrect aggregate contract:** DeepSeek's WM125-2T-028 fails because investor_count does not preserve outer count_distinct. Gemma's WM125-1T-003 attempts an aggregate without a nonempty aggregation list.
- **Wrong final grain:** GPT-OSS's ARC125-3T-009 fails Final Spec because grouping differs from the interpreted investor_id/investor_name grain.
- **Row multiplication:** DeepSeek's WM125-3T-026 includes all required investors but duplicates two; Gemma and Qwen also have repeated-investor partials. Joins over multiple child records can multiply rows when final entity uniqueness is not preserved.
- **Filters not applied to the final output:** GPT-OSS's WM125-1T-023 includes the correct investor's scores plus many unrelated rows. Correct retrieval somewhere inside the plan is insufficient if final composition ignores the intended population.

These explain why additional execution retries are not a complete solution: deterministic structural validation, explicit dataset interfaces, population preservation and final output grain matter.

## 7. Runtime, tokens and efficiency

Timing uses summed per-question elapsed seconds, not four-worker wall-clock throughput. Startup compilation and grading are excluded. Token latency below is non-streaming request duration per reported output token; it includes prompt processing, network and queueing, and is not isolated decoding latency.

| Model | Seconds/question | Calls/question | Input tokens/question | Output tokens/question | Request ms/output token | Illustrative cost/question | MATCH / summed second |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-OSS 120B | 59.869 | 7.03 | 93,732 | 6,573 | 9.074 | $0.018003 | 0.013045 |
| DeepSeek V3.2 | 59.421 | 6.88 | 67,365 | 2,731 | 21.660 | $0.020009 | 0.012521 |
| Gemma 3 27B IT | 80.268 | 8.70 | 90,904 | 3,095 | 25.895 | $0.025937 | 0.003974 |
| Qwen3 Coder 480B | 46.539 | 7.49 | 67,823 | 2,337 | 19.703 | Not priced | 0.015127 |

Costs apply the previously supplied input/output rates per million tokens: GPT-OSS $0.15/$0.60, DeepSeek $0.28/$0.42 and Gemma $0.27/$0.45. They are illustrative normalized estimates, not verified Bedrock invoices. They exclude grading and context preparation. Qwen has no supplied pricing assumption; no cost is invented.

Qwen's token-latency estimate uses the 994 rows with complete reported usage; its full-run elapsed-time efficiency includes all 1,000 rows. Six failed calls have missing token usage, so its recorded token totals are incomplete. The other three runs record no missing-usage calls. Recorded cached-input counts should be considered when translating this normalization into actual provider charges.

Qwen is fastest end to end in this set. GPT-OSS and DeepSeek take about one minute per question on average, while Gemma takes about 80 seconds despite being the smallest model. Gemma averages 8.70 calls/question versus 7.03 GPT-OSS and 6.88 DeepSeek, consistent with greater repair/plan burden. This does not prove calls are the only cause; provider throughput and token generation differ too. Model-request time accounts for nearly all recorded per-question processing time, making inference a more promising latency target than SQLite execution.

## 8. Context provenance and limitations

The context is intentionally database-specific and richer than the main pipeline's terminology-only active pack. However, the supplied business-rules addendum contains evaluation-related corrections, benchmark references and observed cohort information. The existing [context audit](improvement10_context_leakage_audit.md) found no direct reference-answer injection in the inspected planner path, but did identify benchmark-contamination risk and propagation of evaluation-related content into actual compiled rules. The results should not be described as a clean, independently authored business-context experiment.

Other limits are one run per model, one repeatedly used wealth-management development benchmark, unresolved grader errors, model-specific compiled packs, cloud-provider timing effects and no no-context control. No unseen-domain transfer, statistical superiority or causal benefit of business rules follows from this experiment alone. Large-model size does not guarantee correct structured-plan generation, and local privacy does not follow merely from using open weights through a hosted API.

The strongest defensible finding is that Improvement10 works well with GPT-OSS and DeepSeek, but its generated multi-stage processing/Final Spec interfaces are a substantial failure surface, especially for Gemma. Complex comparisons and final row semantics remain weaknesses even where execution succeeds.

## Artifact provenance

Counts were recomputed by `analysis/completed_experiments_20261008/summarize.py`. Input file hashes, detailed status counts, per-type counts and paired transitions are saved in `analysis/completed_experiments_20261008/summary.json`.

- improvement10/deepseek_v3_2/with_context: [raw](../ablations/improvement10_models/runs/deepseek_v3_2/run_01/parallel_workers4/raw_pipeline.csv) and [grader 2](../ablations/improvement10_models/runs/deepseek_v3_2/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv).
- improvement10/gemma_3_27b_it/with_context: [raw](../ablations/improvement10_models/runs/gemma_3_27b_it/run_01/parallel_workers4/raw_pipeline.csv) and [grader 2](../ablations/improvement10_models/runs/gemma_3_27b_it/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv).
- improvement10/gpt_oss_120b/with_context: [raw](../ablations/improvement10_models/runs/gpt_oss_120b/run_01/parallel_workers4/raw_pipeline.csv) and [grader 2](../ablations/improvement10_models/runs/gpt_oss_120b/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv).
- improvement10/qwen3_coder_480b/with_context: [raw](../ablations/improvement10_models/runs/qwen3_coder_480b/run_01/parallel_workers4/raw_pipeline.csv) and [grader 2](../ablations/improvement10_models/runs/qwen3_coder_480b/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv).
