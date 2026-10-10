# Improvement10 SQL pipeline: detailed evaluation, findings and limitations

## 1. Scope and evidence

This analysis uses the results supplied for the `pipelien_output_sql_v3` run as its numerical basis. It replaces the earlier four-model summary as the primary Improvement10 analysis. The supplied GPT-OSS run achieved **839 full matches out of 1,000 questions (83.9%)**; it is a different run from the previously analyzed GPT-OSS experiment with 781 matches. The two results must not be merged or substituted into the same experimental comparison without checking their run identities and evaluation policies.

The supplied report states that its author recomputed results from graded CSVs, debug files and per-call telemetry. Those underlying archive files were not attached here, so its detailed statistics and root-cause assignments are attributed to that report rather than presented as independently reproduced in this revision. The local Improvement10 source was inspected to explain the mechanisms and identify architectural limitations. Concrete example failures below come from the supplied report.

| Setting | Supplied run |
| --- | --- |
| Pipeline label | `aop-improvement8-v3`, spec-first v9, in the Improvement10 codebase |
| Answer model | `openai.gpt-oss-120b` |
| Evaluation | GPT-5 mini, direct semantic judgment |
| Data/backend | Wealth-management SQLite dataset |
| Questions | Eight suites of 125 questions: 1,000 total |
| Parallelism | One sequential worker per suite; eight suites in parallel |
| Reported run window | 6 October 2026, 15:04–18:07 |
| Context | Domain documentation, business rules and table YAML metadata |

The local source confirms the pipeline/spec labels. The reported runtime rounds to approximately 3 hours 5 minutes, while the displayed start/end times span 3 hours 3 minutes; exact elapsed time requires the original timestamps. This small difference should not be resolved by inventing precision.

## 2. What the pipeline does, and why its design matters

The system resolves the question against physical SQL metadata and a compiled business-context pack. Query Understanding specifies field ownership, metrics, filters, population, final grouping, ranking and NULL policy. Retrieval and decomposition identify the source data needed. QuerySpec defines raw retrieval, SQL fetches the records, and generated processing/final specifications compose and calculate over the retrieved datasets using supported Python operators.

This separates **what data must be retrieved** from **how the final result must be calculated**. It makes intermediate data and calculations inspectable and supports staged aggregation. However, it creates several interfaces that must agree: interpretation, retrieval predicates, dataset names, retained fields, intermediate grain and final output grain. An error at one interface can survive later stages even when every API call and SQL statement succeeds.

A typical dependency chain is:

```text
Question + schema + compiled domain context
                    ↓
            Query Understanding
                    ↓
       Retrieval selection / decomposition
                    ↓
       QuerySpec → SQL → retrieved datasets
                    ↓
         Processing Spec / Final Spec
                    ↓
       Validated deterministic execution
                    ↓
               Final answer
```

The inspected code includes repair loops, contract checks and optional specialist consultation. These safeguards reduce malformed plans but do not establish that the resolved interpretation is correct. The results are therefore best understood as a test of a structured, domain-conditioned SQL orchestration system, not merely a single generated SQL statement.

## 3. Overall results: strong execution, incomplete semantic correctness

| Metric | Reported value | Interpretation |
| --- | --- | --- |
| Full MATCH | 839/1,000 — **83.9%** | Strict answer accuracy |
| PARTIAL | 107/1,000 — **10.7%** | Some accepted content, but incomplete/incorrect answer |
| MISMATCH | 54/1,000 — **5.4%** | Includes ten hard pipeline failures |
| Successful end-to-end execution | 990/1,000 — **99.0%** | Execution reliability, not answer correctness |
| Model calls | 6,954; all reported successful | API reliability, not reasoning reliability |
| Weighted partial-credit score | **89.25%, rounded to 89.3%** | MATCH + 0.5 × PARTIAL, divided by 1,000 |
| Reported Wilson 95% interval | 81.5–86.0% | Sampling interval under binomial assumptions |

Of the 161 non-matches, only ten are hard pipeline failures. The remaining 151 comprise 107 partial answers and 44 mismatches from questions that produced an answer. Thus **93.8% of non-matches are answer-quality failures rather than hard execution failures**. Among the 990 successfully executed questions, the full-match rate is approximately **84.7%**.

The main opportunity is consequently semantic preservation, not connection reliability. A completed query can still aggregate at the wrong level, omit a required predicate, choose a similarly named field from the wrong table or return an incorrect row set. Calling all 151 answers “confident” would require calibrated confidence evidence, which is not provided.

The partial-credit score is useful as a descriptive secondary measure, but assigning every partial answer half credit is arbitrary. It is not F1, precision, recall or a probability of correctness. A ranking missing one investor and a substantially incomplete result may both receive PARTIAL while differing considerably in practical usefulness.

The Wilson interval does not account for correlated question templates, grader disagreement, benchmark contamination or repeated development on the same dataset. It should not be interpreted as the full uncertainty of the experiment.

## 4. Suite-level strengths and weaknesses

| Suite | Full matches | Accuracy | Supplied 95% interval | Partial-credit score | Median seconds |
| --- | --- | --- | --- | --- | --- |
| Benchmark | 120/125 | 96.0% | 91–98% | 96.8% | 37.3 |
| Batch Status | 120/125 | 96.0% | 91–98% | 97.6% | 40.5 |
| Scoring Quantitative | 109/125 | 87.2% | 80–92% | 91.2% | 36.5 |
| Temporal Transaction | 109/125 | 87.2% | 80–92% | 89.2% | 37.6 |
| At-Risk Critical | 105/125 | 84.0% | 77–89% | 90.4% | 47.3 |
| Reference Compliance | 103/125 | 82.4% | 75–88% | 90.8% | 29.8 |
| Enrichment Context | 96/125 | 76.8% | 69–83% | 81.2% | 49.9 |
| Multi-Step Comparative | 77/125 | 61.6% | 53–70% | 76.8% | 74.4 |

The suite match counts sum to 839. Three patterns emerge.

**Lookup/cohort tasks are a relative strength.** Benchmark and Batch Status each reach 96%. These tasks often admit a direct mapping from question conditions to source fields and a clear answer population. The result supports strong performance on these suites, not a claim that all lookup-style enterprise queries are solved.

**Middle-performing suites contain recurring mechanical defects.** Reference Compliance loses many partial-credit points through extra NULL entries. Temporal mismatches are frequently associated with missing date predicates. These are more localized than a wholly wrong interpretation and suggest specific checks that can be evaluated without changing the grader.

**Analytical composition is the clearest weakness.** Multi-Step Comparative has the lowest accuracy and highest median time. Its 15.2-point gap between strict accuracy and partial credit indicates many incomplete answers, but not that they are all easy to repair. Enrichment also requires disambiguating dimensions and aggregating correctly across related records.

These suites represent different task mixtures. It is not valid to declare every difference below eight percentage points statistically insignificant merely because individual confidence intervals overlap. Formal comparisons require an appropriate test, consideration of template dependence and multiple comparisons. The broad separation between 96.0% and 61.6% is more compelling descriptively than small differences between middle suites.

## 5. Complexity trends: semantic structure matters more than table count

### 5.1 Join depth

The supplied report gives accuracies of 84.4%, 93.4%, 78.9%, 72.0% and 84.4% for one through five tables. It also reports correlations between table count and model calls (ρ = 0.84), input tokens (0.78) and latency (0.69).

More tables generally increase planning and context burden, but the accuracy trend is not monotonic. Single-table questions can require complete reference lists, precise NULL treatment or large output sets. Five-table questions can be highly formulaic: the supplied report notes 20/20 correct five-signal detection questions. That subgroup does not imply every five-table question is easy.

The interpretation is that **table count is an incomplete complexity proxy**. The number of semantic choices—population, join cardinality, aggregation stages, null treatment and ranking scope—is often more consequential. A five-condition template can be easier than a two-table average requiring carefully defined weighting.

### 5.2 Answer shape

Single-row answers reportedly achieve 94.6% accuracy, whereas answers with two to five rows achieve 71.4%. Small grouped outputs can be demanding because each row represents a population and a calculation; a missing NULL group or an incorrect group average can invalidate a large fraction of the answer.

This association does not prove answer length causes errors. Output size, suite and query type are confounded. Large lists also introduce completeness, duplication and judge-comparison challenges.

### 5.3 Difficulty labels

| Difficulty | Questions | Accuracy | Median seconds | Mean model calls |
| --- | --- | --- | --- | --- |
| Easy | 82 | 93.9% | 25.6 | 5.3 |
| Medium | 361 | 87.8% | 33.4 | 6.0 |
| Hard | 306 | 83.0% | 43.4 | 6.8 |
| Advanced | 124 | 82.3% | 62.1 | 8.4 |
| Expert | 127 | 70.1% | 94.3 | 9.5 |

Overall, higher difficulty coincides with lower accuracy and more inference work. Expert questions are roughly 3.7 times slower at the median than Easy questions and require about 1.8 times as many calls.

Within individual suites, the ordering can reverse. The supplied report gives At-Risk Easy at 69% and Expert at 100%, and Scoring Hard at 100% versus Medium at 85%. Small subgroups, formulaic question patterns and suite-specific label calibration can explain such reversals. Difficulty labels should be treated as annotations rather than a universal scale of computational complexity.

### 5.4 Position and time within the run

Enrichment declines from 96% in its first 25 questions to 60–64% in its last 50; Multi-Step Comparative falls from 84% in its first block to 48–64% in later blocks. The suite order generally moves toward more tables and calculations, so later-position weakness is consistent with harder task content.

The reported increase from approximately 31-second medians early in execution to over 100 seconds after two hours is also consistent with increasingly difficult remaining questions. It does not independently establish service degradation, model fatigue or accumulated conversational state.

The supplied report states generation speed stayed near 150 output tokens/second. Unless that measure isolates decoding, it cannot exclude queueing or prompt-processing effects. Per-call timestamps and streaming measurements would be needed to conclude that load played no role.

## 6. Failure taxonomy and intuitive mechanisms

The supplied analysis assigns one primary cause to each of the 161 non-matches. Percentages below refer to that error population, not all questions. These assignments are diagnostic judgments; real failures can involve several interacting causes.

| Primary cause | Questions | Share of non-matches |
| --- | --- | --- |
| Wrong aggregation grain/formula | 40 | 24.8% |
| NULL-group policy as the only defect | 28 | 17.4% |
| Wrong row set: extra/missing records | 26 | 16.1% |
| Composite ranking drift | 14 | 8.7% |
| Wrong values plus missing NULL group | 11 | 6.8% |
| Silently dropped filter | 10 | 6.2% |
| Pipeline specification failure | 10 | 6.2% |
| Wrong source column | 10 | 6.2% |
| Duplicate rows from join fan-out | 7 | 4.3% |
| Wrong entity/projection | 5 | 3.1% |

### 6.1 Nested aggregation and grain

In MC125-040, averaging rebalance records gives approximately 89k, while averaging each investor's total gives approximately 405k. Both can be valid arithmetic over valid records, but they answer different questions:

```text
Average of event amounts
    ≠
Average of per-investor total event amounts
```

The first weights investors according to their number of events; the second gives each included investor one intermediate total. The local Query Understanding contract explicitly distinguishes inner/outer aggregation and intermediate entity keys from final grouping. The observed errors therefore indicate incomplete propagation or realization of those distinctions, rather than absence of the concepts from the prompt.

This mechanism also explains average signed cash flow, average total holding value and composite measures. Correctness requires specifying the entity population, intermediate aggregation, treatment of entities with no records and final aggregation together.

### 6.2 NULL semantics

The supplied examples show opposite errors: adding a NULL entry to a reference-value list whose reference excludes it, and removing the NULL group from a grouped result whose reference retains it. `null_policy` is reportedly unspecified in 450 interpretations.

The pipeline does have a NULL-policy field. Its weakness is **underspecified and inconsistently enforced policy**, not complete absence of support. Missingness can mean unknown, absent participation or a genuinely excluded observation, depending on the field and task. A global instruction to always include or exclude NULL would repair one class while damaging another.

Policy should be derived from the question and independently documented semantics, then enforced consistently across SQL retrieval and final processing. When benchmark conventions are not recoverable from either source, the issue is partly task ambiguity, not exclusively a model error.

### 6.3 Predicates lost during repair

The supplied report identifies repeated unfiltered outputs: six temporal questions return the same whole-table total, 2,110,617,425, and two date-count questions return the full count, 7,828. It attributes eight of eleven Temporal mismatches to this pattern; the broader primary taxonomy counts ten dropped-filter cases across suites.

The local QuerySpec checker can reject a downstream predicate incorrectly applied during raw retrieval. Moving a predicate is legitimate when its expression depends on a computed intermediate value. But a stage-local repair is insufficient if the final plan never applies it. The central requirement is **end-to-end predicate conservation**: every interpreted predicate must appear at a valid stage, and repairs must preserve that assignment.

Repeated whole-table totals are a strong diagnostic signal for a missing restriction. They do not mean every repeated value is erroneous; unrelated queries can legitimately share a result.

### 6.4 Shared field names and source ownership

EC125-2T-043 binds “category” to a holding category rather than investor category. SQL syntax, column existence and data types cannot detect the semantic substitution because both fields exist.

Useful metadata must distinguish the entity owning a field, its definition and observed domain. An external context pack can improve this, but it can also reinforce the wrong mapping if compilation conflates similarly named concepts. Source-qualified meanings should survive all the way into interpretation and execution.

### 6.5 Final Spec and projection failures

Eight of the ten hard failures reportedly involve a final-grain guard; some also involve invalid join arity/dataset naming. Other failures involve an invalid expression or lost outer count. These guards are protecting execution from unsupported or inconsistent plans. Disabling them would increase the number of produced answers without establishing correctness.

The appropriate repair is to regenerate the plan with the expected grain, available datasets and preserved fields stated explicitly, then revalidate. The supplied report's three-attempt statistics describe observed groups, not necessarily the configured maximum: the inspected local executor permits four Final Spec attempts. Exact source/run identity is needed before describing three attempts as the universal retry limit.

### 6.6 Composite ranking and duplication

Ranking drift can arise even when eight or nine of the top ten investors are correct. Changing a component filter or the min–max normalization population changes scores and can swap boundary members. A final top-k check alone cannot validate the underlying score construction.

Join fan-out duplicates investors when one investor has multiple qualifying sector or holding records. For entity lists, uniqueness should be checked at the requested entity key. For event or position outputs, repeated investor IDs are legitimate. Deduplication must follow answer grain, not be applied indiscriminately.

## 7. Repairs as diagnostic signals

| Supplied diagnostic group | Questions | Accuracy |
| --- | --- | --- |
| No logged repairs | 865 | 85.5% |
| One repair | 85 | 77.6% |
| Four or more repairs | 21 | 42.9% |
| One Final Spec attempt | 919 | 84.5% |
| Three Final Spec attempts | 18 | 38.9% |
| Query Understanding retried | 277 | 78.0% |
| More than ten model calls | 33 | 60.6% |
| “Predicate moved downstream” repair | 37 | 67.6% |

These groups overlap and do not form one partition. The report also gives 87.3% accuracy for questions with two Final Spec attempts. Repairs can recover useful answers; repeated attempts are not inherently harmful.

The likely interpretation is selection: difficult or inconsistent interpretations need more repairs and are also more likely to remain wrong. A causal claim that retries reduce accuracy would require a matched no-repair experiment. Nevertheless, repeated repairs are observable warning signals that could support confidence routing.

Any escalation rule needs calibration on separate data. A rule flagging third-attempt plans will also flag correct answers, and a stronger model or human review increases cost. The supplied proposed rule flags 46 questions at 65% accuracy and captures twelve mismatches; it should be evaluated as a triage policy, not described as a guaranteed correctness detector.

## 8. Context preparation and specialist consultation

Improvement10 compiles the domain prompt, business-rules addendum and table YAML documents into a schema-linked context pack. In the simple compiler mode, the documents are supplied together for compilation and review. This helps encode ownership, units, signs and formulas without embedding all domain knowledge directly in operator code.

The context still has limitations. It is only as reliable as its provenance and mappings; compilation is not proof that every rule is correct or independent of evaluation. The prior [context audit](improvement10_context_leakage_audit.md) identified evaluation-related corrections and cohort observations in the inspected Improvement10 documents. Whether the supplied run used the same document versions must be verified from its original manifest. This cannot be resolved by its pipeline label alone.

The supplied run reports zero specialist consultations despite the feature being enabled. The local consultation mechanism is request-driven: an operator must emit a valid consultation request. It is not an automatically invoked second opinion on every answer. Therefore an enabled flag does not establish that specialists reviewed the difficult cases.

Likewise, empty `ambiguities` fields on all questions are not evidence that the questions were unambiguous. They may reflect the model confidently resolving uncertain meanings or contract/repair behavior. A self-reported uncertainty field needs external calibration before serving as a trustworthy safeguard.

## 9. Latency, token burden and efficiency

### 9.1 Reported inference work

| Stage | Calls | Calls/question | Median input tokens/call |
| --- | --- | --- | --- |
| Query Understanding | 1,396 | 1.40 | 22.4k |
| QuerySpec | 2,442 | 2.44 | 11.4k |
| Final Spec | 1,112 | 1.11 | 14.6k |
| Decompose | 1,004 | 1.00 | 13.9k |
| Retrieve | 1,000 | 1.00 | 1.0k |
| Total | **6,954** | **6.95** | Approximately 92M input + 6.3M output tokens overall |

The supplied stage counts sum to 6,954. Approximately 98.3k tokens/question and 117k tokens/full match demonstrate substantial inference overhead. This is accumulated usage across calls, not a single request's context length.

Query Understanding reportedly accounts for 39% of LLM time and 34% of tokens, with an approximately 86k-character prompt. Large static schema/rule context can improve grounding but is repeatedly transmitted and processed. More context is not automatically better; unnecessary material increases cost and can introduce competing interpretations.

Only 7.7M of the approximately 92M input tokens are reported cached, or 8.4%. Stable prompt prefixes are a plausible optimization target, but cache eligibility and billing depend on the provider. Reusing a compiled knowledge pack and provider prompt caching are different mechanisms.

### 9.2 Latency and parallel execution

Median question latency is 41.8 seconds and p95 approximately 115 seconds. MATCH answers have a 40.6-second median versus 57.4 seconds for PARTIAL answers. More difficult questions often need additional calls, longer specifications and more intermediate calculations.

The supplied report gives approximately 14 hours of serial question time and approximately 3 hours 5 minutes of wall-clock time, bounded by the Multi-Step suite's 11,109 seconds. These describe different quantities. Eight workers do not guarantee eightfold speedup: fixed suite assignment leaves fast suites finished while the slow suite continues, producing a tail dominated by the hardest worker.

Using the rounded 14-hour sum, execution efficiency is approximately **839 / 50,400 = 0.01665 full matches per summed question-second**. Wall-clock throughput is approximately **4.5 full matches/minute** using the reported 3-hour-5-minute duration. Both are approximate because the underlying exact totals are unavailable here. They must not be interchanged.

### 9.3 Illustrative cost

Using the previously supplied normalization prices of $0.15/M input tokens and $0.60/M output tokens for GPT-OSS, the rounded 92M/6.3M totals imply approximately:

- **$17.58 for answering 1,000 questions**;
- **$0.01758 per question**;
- **$0.02095 per full match**.

These are illustrative calculations, not verified incurred AWS charges. They do not account for provider-specific cached-input pricing, and preparation/grading costs are not established by the supplied answering totals. No exact token-generation latency should be invented from question elapsed time; model-call timing and output usage must be aligned.

## 10. Grader reliability and reference conventions

The supplied report describes one direct semantic GPT-5 mini judgment per question without a deterministic first-stage equivalence check. It identifies inconsistent handling of extra NULL rows, duplicate rows, supersets of required IDs and the wrong identifier column. Some defects receive MATCH in one case and PARTIAL/MISMATCH in another.

For the 449 entity-ID questions, MATCH outputs reportedly average approximately 98% ID recall and precision. This supports usefulness of the judge for those outputs, but it does not measure the judge's own classification precision and recall, prove numerical answers are correct or quantify an overall “few points” of grading noise.

The nineteen empty-reference questions were all answered correctly according to the supplied evaluation. Empty cases are useful when the system must correctly discover no qualifying entities, but could provide weak signal if empty output is accepted without distinguishing execution failure from a valid empty result.

Reference conventions also matter. GROUP BY including a NULL group and a reference-value listing excluding NULL can both be legitimate. The question or prior documentation should make intended treatment recoverable. Disagreement with a reference is not always proof of faulty SQL if the natural-language task is underspecified.

A deterministic result comparison with appropriate numeric tolerances can be an additional audit metric. It should not replace the fixed grader or silently revise existing labels. The supplied root-cause analysis used a 0.5% numeric tolerance; that is an audit assumption whose suitability depends on units, rounding and metric semantics. Raw counts and IDs may require exact comparison.

## 11. Limitations and threats to interpretation

### Pipeline limitations

1. **Meaning must survive multiple contracts.** Repairing one stage can lose predicates or fields needed by later stages.
2. **Nested aggregation remains fragile.** Intermediate entity grain and final group grain can be confused even when represented in the interpretation.
3. **Ambiguous physical names require semantic ownership.** Column existence cannot distinguish investor and holding category.
4. **NULL policy is often unspecified.** A field exists in the contract, but a robust resolved policy is not consistently enforced.
5. **Self-validation is incomplete.** A valid executable plan can faithfully implement an incorrect interpretation; specialists do not automatically intervene.
6. **Inference overhead is high.** Almost seven calls and approximately 98k tokens/question impose latency and cost even when SQL execution is straightforward.
7. **Parallel workers have unequal workloads.** Suite-based sharding can leave a long completion tail; redistribution must preserve identities, outputs and context.

### Evaluation limitations

1. This supplied run uses one answer model, one database and one reported execution; it does not establish model-independent reliability or transfer.
2. There is no matched previous-version baseline inside this run. `Old Status = NEW_BENCHMARK` is not a baseline evaluation.
3. The single LLM judge is imperfect, and PARTIAL is not a calibrated numerical distance from correctness.
4. Question templates, suite, join count, answer shape and difficulty are confounded; descriptive correlations are not causal effects.
5. Root causes were assigned from traces and comparisons but not independently double-coded; categories can overlap in reality despite one primary label per question.
6. Context provenance must be checked. Evaluation-related material found in the local Improvement10 documents prevents an unconditional claim of benchmark-independent grounding.
7. The supplied report calls the dataset synthetic. Its generation/provenance documentation is not attached; this run alone should not be presented as evidence of realistic enterprise deployment or two independent real-world domains.
8. Reported confidence intervals omit grader, template and development-selection uncertainty. Repeated use of the benchmark for debugging further limits held-out claims.
9. The original archive is unavailable in this attachment. Precise runtime/token metrics, statement-level root causes and historical code identity were not independently replayed for this revision.
10. Cloud-hosted open-weight inference is not local processing. Enterprise privacy requires deployment/access controls beyond the model's weight availability.

## 12. Priorities and realistic improvement expectations

| Priority | Change to evaluate | Supplied affected cases | Why it may help |
| --- | --- | --- | --- |
| 1 | End-to-end predicate preservation after repairs | Ten dropped-filter cases | Prevents plausible unfiltered outputs after stage reassignment |
| 2 | Explicit, source-grounded NULL semantics | 28 NULL-only cases; eleven mixed cases | Aligns missingness treatment across retrieval and final processing |
| 3 | Final-grain and interface-aware repair | Ten hard specification failures | Repairs unsupported plans while preserving protective guards |
| 4 | Entity-grain uniqueness checks | Seven primary duplicate cases | Prevents join fan-out in entity lists |
| 5 | Source-qualified concept mappings | Ten wrong-column cases | Separates similarly named dimensions from different entities |
| 6 | Typed per-entity → per-group aggregation patterns | Forty primary grain/formula cases | Makes staged measures explicit rather than implicit in prose |
| 7 | Calibrated escalation for repeated repair | Overlapping high-effort groups | Routes uncertainty rather than equating execution with correctness |
| 8 | Static-prefix optimization and balanced scheduling | Runtime/cost rather than fixed match count | Reduces repeated context work and the slow-worker tail |

These are proposed experiments, not implemented changes in this document. Existing pipeline code, grader code and saved labels remain unchanged.

The supplied report estimates that four mechanical fixes could recover 54 unique non-matches. If all 54 became MATCH, strict accuracy would reach **89.3%**, an arithmetic improvement of 5.4 percentage points. This happens to equal the rounded half-credit score but is a different concept.

There is a small accounting discrepancy: the individual listed primary categories for NULL-only, dropped filters, hard spec errors and duplicates sum to **55**, not 54. The original question-ID union must be checked before quoting a precise recoverable total. Neither 54 nor 55 is a measured achievable gain. A repaired query can still have another defect, and fixes can introduce regressions on previously correct questions.

The deeper opportunity is reducing semantic drift across the pipeline: every answer should preserve the requested population, field ownership, aggregation stages, null treatment and output grain. Improving those invariants is more directly supported by this run than increasing retries indiscriminately or weakening validation.

## 13. Paper-ready interpretation

On the supplied 1,000-question wealth-management benchmark, the domain-conditioned SQL pipeline achieves 83.9% full semantic matches with GPT-OSS 120B and executes 99.0% of questions successfully. Performance is strongest on lookup/cohort suites and weakest on multi-step analytical comparisons. Most non-matches arise after successful execution, indicating that semantic preservation across interpretation, retrieval and final composition is a more significant limitation than API or execution reliability. Error analysis identifies aggregation grain, missingness, predicate conservation and source ownership as recurring failure mechanisms. The system makes approximately seven model calls per question and has a substantial context-processing cost. These results demonstrate useful capability on the evaluated dataset while leaving open questions about context provenance, evaluator consistency, robustness across repeated runs and transfer to unseen databases.

## Evidence and source references

- Supplied numerical analysis: [preserved attachment](../analysis/completed_experiments_20261008/improvement10_supplied_run_analysis.txt).
- Earlier, distinct four-model experiment: [preserved previous analysis](../analysis/completed_experiments_20261008/improvement10_four_model_analysis_previous.md).
- Inspected source: `ablations/improvement10_models/source/improvement10/run_pipeline_v3_sql _/` — `query_understanding.py`, `llm_operators/query_spec.py`, `main.py`, `executor.py`, `consultation.py`, `knowledge.py` and `knowledge_single.py`.
- Context provenance review: [Improvement10 context audit](improvement10_context_leakage_audit.md).
