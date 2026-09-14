# Architecture and contract review

Read-only diagnosis of the supplied historical results and current source. No LLM calls, database queries, credentials, or production edits. Small reproductions evaluated only AST-extracted pure functions using a fake LLM response.

## Version evidence

- All 192 supplied debug rows identify `aop-gpt-oss-120b-improvement3-strict-contracts-v3`.
- Current `run_pipeline_v3/common.py:74` defaults to `aop-gpt-oss-120b-improvement3-answer-coverage-v5`.
- Current `run_pipeline_v3/llm_operators/final_spec.py` was modified on 2026-09-12 at 12:41 local time; the supplied runs finished at approximately 02:49 and 03:53. Current code cannot be assumed identical to the code used for those runs.
- Current `run_pipeline_v1/common.py:74` has the old version string, but its `spec_contracts.py` and `final_spec.py` have later fixes, with mtimes around 01:38, after the approximately 00:48 run starts. A long-running Python process can retain previously imported code despite an edited file.
- `run_pipeline_improved3.py:9` imports `run_pipeline.main`, not `run_pipeline_v3.main`. Exact invocation and source fingerprint must be saved for every future run; a folder or version label is insufficient.

## Proven historical contract bug: scalar becomes list, then becomes a string

An implementation mismatch explains the logged `Final_Spec measure input dataset does not exist: ['q1_processed']` errors without requiring a bad model plan.

1. `run_pipeline/spec_contracts.py:15` includes `input` in `LIST_FIELDS`.
2. Its normalization at lines 43-44 changes `"input": "q1_processed"` to `"input": ["q1_processed"]`.
3. `run_pipeline/llm_operators/final_spec.py:169` calls `str(measure.get("input") or default_measure_input)`.
4. The resulting lookup key is the literal string `['q1_processed']`; the real dataset key is `q1_processed`.

The current v3 scalar normalization at `spec_contracts.py:43-47` and explicit input flattening at `llm_operators/final_spec.py:280-284` repair that particular validation mismatch. Thus the historical failure must not be described as an unfixed v3 bug without rerunning the actual current source.

## Proven current bug: final aggregate filters are silently deleted

`run_pipeline_v3/llm_operators/final_spec.py:198-204` removes every `Filter_Aggregate` entry from `final_steps` whenever `final_measures` is present. It does not distinguish redundant aggregate operations from necessary `operation: filter` steps.

Offline reproduction:

```json
{
  "final_group_by": ["investorId"],
  "final_measures": [{
    "output_column": "total_amount", "operation": "sum",
    "input_column": "amount", "input": "q1_processed"
  }],
  "final_steps": [{
    "operator": "Filter_Aggregate", "input": "previous",
    "operation": "filter",
    "filters": [{"field": "total_amount", "operator": ">", "value": 1000}]
  }],
  "projection": ["investorId", "total_amount"]
}
```

Actual result: `final_steps: []`, `contract_errors: []`. A request for investors whose total is above 1000 becomes an unrestricted grouped total. Fix canonicalization to preserve filters and any distinct aggregate stages; canonicalization must not delete semantic predicates.

## Proven current weakness: contract validation tracks fields that no longer exist

`Processing_Spec` initializes a union of raw fields (`processing_spec.py:111`) and adds every produced output column (`:117-123`). It never derives each dataset's actual output schema or removes columns dropped by grouping. `validate_step_contract` (`spec_contracts.py:119-133`) therefore verifies field existence somewhere in history, rather than on the declared input dataset.

Offline reproduction: raw rows have `investorId, amount`; step 1 groups by investor and creates `total_amount`; step 2 reads step 1 and calculates `amount * 2`. Contract errors are empty even though `amount` no longer exists in the grouped result.

`Final_Spec` has a related issue: `final_spec.py:245,300,312-325` accumulates raw and produced columns. A final grouped SUM followed by projection of the original ungrouped `amount` also returns no contract errors in an offline reproduction.

Fix: derive an output schema per dataset and operation. Aggregate output equals grouping fields plus measure outputs. Validate references against their selected predecessor's schema, and projection against the actual terminal dataset. Runtime shape checks should enforce the same contract.

## Confirmed lossy cleanup and permissive fallbacks

- `query_spec.py:211-213` silently reduces multiple retrieval specifications to the first. If Decompose produced an inadequate branch and Query_Spec tries to retrieve a second required source, the extra source disappears rather than prompting decomposition repair.
- `processing_spec.py:96` and `final_spec.py:190-191` silently drop unknown operators. Unsupported model instructions should produce a targeted contract error, not a shortened apparently valid plan.
- `validate_query_spec_contract` accepts a retrieval with a valid class but empty `fields` and `entity_key`. This was reproduced offline; it returns `[]` errors. Query_Spec JSON parse fallback produces essentially that shape (`query_spec.py:132-149`).

## Architecture changes and why operator count is not accuracy

The old implementation already had DAG planning and multiple candidate evaluation. The meaningful execution change is:

- Old `run_pipeline_improved_1.py:897-921` tells Generate to implement the complete query and treat Query_Spec as guidance. SQL/SPARQL handles joins, aggregation, formulas, ordering, and projection in a coherent relational plan.
- Old `:1711-1721` explicitly chooses single SPARQL or preaggregate SPARQL and favors an executable query over a brittle specification shape.
- Current `planner.py:73-74` defaults to a fixed spec-first DAG. The multi-candidate planning and operator cost/reward machinery below it is bypassed.
- Current `planner.py:134-163` creates Query_Spec -> Generate -> Pre_Scan_Validate -> Scan -> Processing_Spec for every branch, then Final_Spec -> Validate -> Explain.
- Current `decompose.py:132-133` and `spec_contracts.py:84-100` require one source class per branch. Even a straightforward two-class join therefore crosses two retrieval contracts, two scan schemas, two processing contracts, and a merge specification.
- Current `generate.py:91-97` prohibits aggregation, formulas, sorting, and limits in SPARQL. All these responsibilities now belong to the custom interpreter and its contracts.

Deterministic arithmetic is a useful direction, but it cannot recover discarded rows, wrong joins, a missing condition, a changed grouping level, or an omitted display field. More operators add representational capacity and also interfaces that have to preserve semantics. This change effectively builds a small relational compiler; its supported semantics and type checking need to be as explicit as the underlying query engine's.

## Grain risks: check against each reference query

`processing_spec.py:56-59` instructs every fact-table branch to aggregate to its natural entity grain before merging. That is not universally semantics-preserving. For example, an average of per-investor goal averages differs from an average across all goals when investors have unequal numbers of goals. A count of processed investor rows is not a count of original goal rows. Some benchmark references may intentionally use per-investor aggregation, so this cannot be judged from the English query alone.

Historical example to compare with reference SQL: `WM-2T-012` is PIPELINE_SUCCESS and asks average goal progress across investor risk-tolerance groups. Processing computes `AVG(progressPct)` by investorId; Final computes `AVG(avgProgressPct)` by riskTolerance. Whether this matches the dataset reference depends on its specified weighting.

Preserve sufficient statistics (`sum`, non-null `count`) for weighted averages, stable entity keys for distinct counts, and explicit grain/row-population requirements in the global logical plan. Choose preaggregation only when the reference semantics allow it. Do not force it merely because there are multiple sources.

## Prompt conflicts remain in current source

- `query_spec.py:247-258` always empties `operator_plan`, `measures`, top-level `filters`, and `group_by`.
- `generate.py:95` says never aggregate or calculate, but `:143` says not to calculate unless there is no operator_plan. The current pipeline always has an empty operator_plan.
- `generate.py:120` recommends aggregating separately in SPARQL subqueries for unsafe joins, while `:95` forbids aggregation and nested subqueries.
- `pre_scan_validate.py:55-56` allows raw unaggregated retrieval only conditionally on having an operator_plan, although raw retrieval is always the current contract.
- The opt-in legacy decomposition DAG prompt (`planner.py:183-192`) requests branches without Processing_Spec/Final_Spec, while its validator requires both (`:309-312`). The fallback similarly omits them (`:239-293`). This is a latent comparison-path inconsistency; it does not explain default spec-first run failures.

These are source-confirmed contradictions, not measured counts of observed failures caused by each contradiction.

## Prioritized changes

1. Freeze an exact source snapshot and replay recorded specs/results through its deterministic functions. Separate interpreter failures from incorrect model intent before another expensive full evaluation.
2. Repair the scalar/list contract, dataset-name resolution, aggregate-filter deletion, and per-dataset schema tracking. Add small semantic cases covering these reproducible failures.
3. Preserve one authoritative logical plan for row populations, grouping, join keys/types, distinctness, predicates, and output columns. Downstream stages should refine execution rather than repeatedly reinterpret the question.
4. Use the old single-query route for query classes already executed reliably; compare a small ablation against compulsory decomposition. Introduce branch preaggregation only where it measurably improves the same query IDs.
5. Track execution success separately from answer correctness. A validator that examines its own generated plan and a few sample rows cannot establish equivalence to reference SQL.

The supplied evidence supports implementation and contract defects, plus semantic ownership fragmentation. It does not establish that deterministic operators or decomposition are inherently wrong, nor that any design change guarantees 350/442.
