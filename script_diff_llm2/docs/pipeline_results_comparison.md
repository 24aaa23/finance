# Improvement10 versus the main hybrid pipeline: brief comparison

> Run distinction: this comparison retains the earlier four-model Improvement10 results (GPT-OSS 78.1%). The primary Improvement10 report now analyzes the separately supplied GPT-OSS run at 83.9%. Its grader mode and historical inputs need matching before a controlled comparison with the main hybrid runs; the old comparison figures have not been replaced with numbers from a different run.

Snapshot: 8 October 2026. These reports analyze existing completed experiments; no raw answers or grader labels were modified. Accuracy means full MATCH divided by all 1,000 benchmark questions; PARTIAL does not count as a match. PIPELINE_SUCCESS means operational execution, not semantic correctness. Grader 2 using GPT-5 mini is the common evaluation basis. Other labels include execution and grading failures and are not one homogeneous category. Current incomplete Azure experiments and the newly added decomposition retries are outside this analysis.

Question IDs, question text and reference-answer text match exactly for the paired GPT-OSS, DeepSeek and Gemma comparisons. All use grader 2 with GPT-5 mini. This makes descriptive question-level comparison possible, but context, execution design, prompt contracts and runtime conditions differ, so this is not an isolated KG/decomposition ablation.

| Model | Improvement10 | Main without context | Main with context | Main without minus I10 | Main with minus I10 |
| --- | --- | --- | --- | --- | --- |
| GPT-OSS 120B | 78.1% | 78.9% | 79.0% | +0.8 pp | +0.9 pp |
| DeepSeek V3.2 | 74.4% | 80.6% | 78.3% | +6.2 pp | +3.9 pp |
| Gemma 3 27B IT | 31.9% | 61.3% | 60.9% | +29.4 pp | +29.0 pp |

The strongest practical gain is Gemma: +29.4 points without context and +29.0 with context. Its execution success also improves from 53.0% to roughly 80%. That is consistent with reducing the fragile generated Python Final Spec interface, although many other changes prevent a causal attribution. Because Gemma uses SQL for all main-pipeline questions, its improvement cannot be credited to actual KG execution.

DeepSeek gains 6.2 points without context and 3.9 with context. Its execution success is slightly lower in the main pipeline (93.5%/90.6% versus 93.9%), but MATCH among successful executions increases from 79.1% to about 86.3%. Its improvement therefore reflects better observed correctness among executable answers, not simply more executions.

GPT-OSS gains only 0.8/0.9 points. Execution success falls from 97.4% to 93.3%/92.4%, while conditional correctness improves from 80.2% to 84.6%/85.5%. Stricter node-local contracts and changed computation paths trade some executability for stronger observed answers among successes; the net accuracy gain is small and should not be advertised as a decisive architecture victory.

Paired without-context comparisons show 107 gains versus 99 losses for GPT-OSS, 158 versus 96 for DeepSeek and 365 versus 71 for Gemma. The systems have complementary strengths; replacing the old pipeline does not improve every question.

The main pipeline has lower recorded mean elapsed time for each shared model: GPT-OSS 33–34 seconds versus 60, DeepSeek 46–50 versus 59, and Gemma 53–68 versus 80. Timing includes failures, endpoint conditions and different planning work; it is not a controlled speedup measurement. Full-run cost cannot be compared fairly because historical main-hybrid token usage was not logged.

Architecturally, Improvement10 retrieves and composes datasets using a generated Python calculation plan; the main pipeline expresses computations in backend queries and coordinates them through an outer DAG. Both already include decomposition. Their contexts are different treatments: Improvement10 uses rich domain/rule/YAML documents with identified contamination risk; completed main-context runs activate sparse terminology and quarantine the evaluation-scoped rules document.

The paper can report the main pipeline's descriptive improvements and reduced sensitivity to Gemma's Final Spec failures. It should not claim that KG composition, business rules or decomposition alone caused those improvements. To establish those claims, use matched context, source data, model/provider, grader and repeated runs, plus explicit backend/decomposition ablations.

Detailed separate reports: [Improvement10](improvement10_results_analysis.md) and [main hybrid](main_hybrid_results_analysis.md).
