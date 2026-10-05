# Context/no-context reliability audit and generic v6 changes

## Saved-run evidence

The snapshot in `summary.json` covers completed DeepSeek and Gemma raw runs, the partial Kimi no-context run, and the earlier GPT-OSS v5 reports. `failure_nodes.csv` inventories failed nodes. Reports actively being written are snapshots, not final results.

| Model/run | Without context raw success | With context raw success | Grading available at snapshot |
|---|---:|---:|---|
| DeepSeek V3.2 | 729/1000 | 746/1000 | No-context Mini: 208 rows, incomplete |
| Gemma 3 27B IT | 602/1000 | 630/1000 | No completed graded report |
| Kimi K2 Thinking | 410/466 | No raw report at snapshot | No graded report |
| GPT-OSS legacy v5 | 912/1000 | 903/1000 | No-context TERA 811 MATCH; context Mini 785 MATCH |

These are execution success counts, not match counts. DeepSeek context increased raw success by 17 questions, Gemma by 28. GPT-OSS lost nine raw successes. GPT-OSS's TERA/Mini comparison is confounded by both a raw rerun and different graders. Do not compare an unfinished, ordered grader prefix with a complete run as if it measured final accuracy.

Per-question raw latency (concurrent runs; not total wall time): DeepSeek median 32.68 seconds without / 31.31 with context, Gemma 25.17 / 25.73, GPT-OSS 23.06 / 22.80. Partial Kimi median is 127.37 seconds. Large slow tails make mean and median differ substantially. The existing API log counts omit some direct backend calls, so they are not a complete per-stage cost measurement.

## Concrete defects

1. **Unsupported DAG operators.** Gemma's no-context run has 221 failed nodes marked `unknown`: SQL, JOIN, SELECT, COUNT and related spellings were sent to an executor that only implements Subquery and set operators. The context run has 214 such failed nodes. These are infrastructure failures, not evidence the database cannot answer the question.
2. **Invalid intermediate bindings.** DeepSeek generated comma-separated compound sources, placeholder output names, and downstream types/aliases that do not identify upstream output columns. Some final nodes were constrained by speculative declared outputs even though nothing consumed them. These made valid backend requests fail QuerySpec contracts or binding resolution.
3. **Scope confusion.** SQL prevalidation occasionally required every root-question predicate in an intermediate node, although sibling nodes handled those conditions. Post-scan normalization and validation also used the root question instead of the local subquery. A root entity-list request could make an intermediate count look invalid, generating unnecessary retries.
4. **Misinterpreted arithmetic and grain.** Prior GPT-OSS checks confirmed wrong entity/child source ownership, row-weighted versus entity-weighted averages, SUM versus AVG shifts, double sign transformations, and duplicate investor results. New QuerySpec/generation guidance preserves explicit signs and distinguishes normalization stages; it does not embed reference answers or domain-specific thresholds.
5. **Spec/generation divergence.** Read-only compiler replay found generators adding `OR field IS NULL` to NOT IN predicates and reversing signs that were not requested by the QuerySpec. Deterministic compilation can remove these reinterpretations for a narrow supported subset.

## Why context did not produce the expected large gain

The actual prepared DeepSeek cache has nine active entries, all terminology. Gemma has three, all terminology. `phase0_business_rules.md` explicitly describes correction of disputed evaluation rows and excludes this 1000-query corpus; it remains quarantined from preparation and inference. No approved operational policies are present in these caches. Thus these runs test limited terminology context, not a fully grounded business-rule bundle.

DeepSeek also returned 25 entries with matching terms formatted as a string instead of a list. Old validation rejected them. The updated validator normalizes this representation while retaining quote/source/conflict checks and the independent approval gate for operational definitions.

The intro file has factual mapping hazards. For example, it describes customer segments Premium/Standard/Mass, while the actual profile segment column contains Small Cap/Large Cap/Mid Cap/Diversified. This is evidence that identically named concepts can refer to different classifications. More prompt text is not sufficient: preparation must see the real physical source and observed domain and flag conflicting mappings. Observed values are not a guarantee that future or unobserved values are forbidden.

The old GPT-OSS context report has no selected-rule traces, so operational rule usage cannot be reconstructed from the configured document paths. Version 6 persists the actual active bundle and per-QuerySpec selection, including an empty selection.

## Implemented changes

- Validate supported DAG operators, unique node IDs, exact upstream fields and acyclicity before execution. Invalid compound plans fall back to one complete-question backend query. A single backend node with a SQL verb is normalized to Subquery. Valid connected DAGs still execute dynamically.
- Reject multi-node plans without a single final result rather than silently selecting unrelated terminal results. Preserve parallel branches that merge through a supported set operation.
- Remove downstream output contracts from terminal nodes. Keep every real inter-node output binding.
- Validate and normalize results against each node's local description. Clarify the same boundary in SQL prevalidation.
- Recognize a schema-grounded physical ID projected under a declared alias; an aggregate of that field is not accepted as an identity. Duplicate detection still applies.
- Add conservative deterministic SQL compilers for explicit one-source point projections and one-level aggregations. They handle quoted literals, null tests, scalar and grouped aggregates, and ID-only entity-set projections. Unsupported joins, bound inputs, compound predicates, two-level grain, population/aggregate filters, ranking and derived alias computations continue through the model. No validation or scan step is skipped.
- Normalize explicit null equality/inequality into null predicates. Null-containing membership lists remain outside the compiler fast path instead of being reinterpreted.
- Keep contract repair at temperature zero where already supported by the pipeline's existing model convention. Explain compact normalization expressions and complete formula dependencies.
- Normalize context matching-term representation and ordinary singular/plural matching. Ground selected context against the complete runtime schema, then expose a missed relevant source to QuerySpec.
- Include primary keys and bounded observed text domains in context preparation/cache identity. Persist `domain_context_state.json` with the active bundle, model, fingerprint, count and hash. Context schema/candidates are not evaluation answers.
- Add a bounded parallel grader wrapper. Every row passes through the original `regrade_existing_report`, preserving its prompts, input lengths, policy, status handling, null review, baseline reuse and error retry behavior. Only the coordinator writes the combined CSV. Two wrappers cannot write the same output concurrently. This does not prevent the original sequential script from competing for that file; do not launch both against the same output.
- Add explicit pilot windows and optional checkpoint intervals to the ablation launcher. Full-run defaults remain 1000 questions, four query workers and per-row checkpoints. New ablations identify themselves as `ablation-generic-reliability-v6`.

Existing grader code, raw/graded reports, benchmark references and database files were not modified. No model API jobs were started during this work.

## Verification and limits

Final verification: 162 unit tests passed, 37 existing tests skipped, and nine ablation-launcher tests passed. Guide shell blocks passed Bash syntax checks. The original grader file is byte-identical to Git HEAD; its SHA-256 is recorded in `verification.json`.

Offline tests cover executable DAGs and fallbacks, scope isolation, schema-grounded identity aliases, context cache evidence, optional/no-context behavior, null handling, one-source compiler execution, and the exact grader workflow. The parallel wrapper produces the same row dictionaries as the original sequential grader under identical mocked judgments, including null review and retrying only grader errors on resume. Actual independent LLM judgments may vary; concurrency does not make them deterministic.

`compiler_replay.json` records 1095 executable saved nodes eligible for the new compilers, with no SQL preparation errors. Among 1058 nodes with comparable saved scan output, 1046 match the requested-value multiset exactly; 12 differ. Four are NOT IN predicates where the model added NULL rows, several are explicit signed SUMs where the model flipped signs, and the remaining grouped differences concern NULL buckets. Some eligible nodes had failed earlier and lack saved scan data. Eligibility means one Generate model call can be avoided; it is not a measured end-to-end speedup or a prediction that every eligible row becomes MATCH.

The compilers execute the QuerySpec faithfully; a semantically wrong QuerySpec can still produce a wrong answer. Complex multi-source/comparative questions remain a significant limitation. Operational rules require independently reviewed source definitions, not evaluation-derived rules with their provenance markers removed. The intro's source mappings need review before expecting large context gains.

Actual accuracy and wall-time improvements have not been measured on a new live run. The same Mini grader is needed for a fair comparison. The original grader's 60000-character truncation remains unchanged, so previously documented large-result judging limitations remain. Improvements were motivated by observed benchmark failures; retain an unseen evaluation set for final transfer/generalization claims.

## Reproduce offline analysis

From repository root:

```bash
/usr/bin/python3 script_diff_llm2/analysis/ablation_reliability_20261005/analyze.py
/usr/bin/python3 script_diff_llm2/analysis/ablation_reliability_20261005/replay_compiler.py
```

See `README_RELIABILITY_V6.md` for fresh-run, pilot, context review and parallel grading commands. Keep old runs for comparison and use a new run tag after code changes.
