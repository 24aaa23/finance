```
Question
-> create 1 decomposition
-> create 3 DAG candidates from that decomposition
-> select best DAG
-> execute


Main Question
  ↓
Retrieve schema/KG context
  ↓
Generate 3 decompositions
  ↓
Select best decomposition
  ↓
Generate 3 DAG candidates for selected decomposition
  ↓
Validate/select best DAG
  ↓
Execute DAG
  ↓
For each small question:
    Query_Spec → Generate simple SPARQL → Pre_Scan_Validate → Scan
  ↓
Use operators:
    Filter_Aggregate / Math_Compute / Set_Intersect / Difference / Union / Integrate / Order_By
  ↓
Merge subquestion outputs
  ↓
Validate final answer
  ↓
Explain final answer

Spec-first execution detail:
  - Query_Spec is raw retrieval only: one source class, fields, source filters, and entity/join keys.
  - Processing_Spec runs after every Scan and aggregates or filters that branch at its entity grain.
  - Final_Spec receives every processed branch and plans the explicit merge keys, final aggregation,
    null-group preservation, ranking, projection, and rounding.
  - Existing Python operators execute both processing specs deterministically; the LLM never computes rows.




Query_Spec:
  source_class, fields, entity_key, preserve_null_fields

Processing_Spec:
  input, per_entity_group_by, operation, output_column

Final_Spec:
  inputs, join_key, final_group_by, final_operation,
  preserve_null_groups, ranking, limit, projection

Final_Spec also declares `final_measures`: each projected measure has its output column,
operation, input column, input dataset, and grouping key. The executor compiles these
declarations into deterministic operators and verifies they appear in final rows.

## Minimal reliability rules

The pipeline keeps the three-spec design. These rules are generic execution safeguards,
not finance-domain or benchmark-SQL hard-coding.

1. Query_Spec is retrieval only: raw schema-valid fields, explicit entity/join keys, and
   source filters. It has no aggregation, cross-branch joins, formulas, ranking, or limits.
2. Processing_Spec operates on exactly one Scan result. Its local operators are determined
   by the declared input/output schemas and required measure lineage, not keyword or
   domain-table rules.
3. Final_Spec receives every `*_processed` branch. For more than one branch, every branch
   must occur in a merge-step input; a partial one-branch answer is rejected and regenerated.
4. The spec interpreter safely flattens malformed nested `input` / `inputs` arrays. Invalid
   LLM JSON produces a spec-contract retry rather than an execution crash.
5. Validation repairs the stage that failed:
   - unknown RDF terms or an unexpected empty raw scan: regenerate Query_Spec, then SPARQL,
     and scan again;
   - a Final_Spec measure whose declared source column is absent from its processed branch:
     regenerate Processing_Spec;
   - merge, final aggregation, ranking, or projection failure: regenerate Final_Spec.
   Raw Scan, Pre_Scan_Validate, and Final_Spec each allow three total attempts (the original
   execution plus up to two repairs). Final-stage repair never rewrites an already successful
   raw scan.
   When Final_Spec is present, Validate judges Final_Spec, Final Execution, and final rows;
   branch-local raw SPARQL is retrieval evidence only and must not be treated as the final join.
6. Schema contracts guide planning and repair: every requested final field must be available
   from a processed branch or produced by a declared step; all merge inputs and output fields
   are checked against actual rows rather than table names or question-specific rules.

7. A shared spec normalizer flattens list-shaped LLM fields once before every contract check
   and execution. During spec execution, operators use declared source/group/sort fields only;
   they do not silently substitute a similarly named or first numeric field.
8. Final aggregate measures have one canonical declaration (`input`, `input_column`,
   `operation`, `group_by`, `output_column`). Derived calculation, date extraction, ordering,
   and limiting run after those measures. The runtime records field lineage by dataset/step and
   rejects a plan before execution if a declared source is unavailable.
9. Final validation false is reported as `FINAL_SPEC_ERROR`, never `PIPELINE_SUCCESS`.

The report CSV remains final-output-only. Processed branch data, generated specs, execution
logs, and retry context are held only in runtime memory for validation and are not written to
the report.

## Strict-contract execution and repair plan

```
Original question
-> existing Decompose
-> Query_Spec for each decomposition branch
-> Query_Spec_Validate
-> Generate simple SPARQL -> Pre_Scan_Validate -> Scan
-> Processing_Spec for each scanned branch
-> Final_Spec across processed branches
-> existing Validate -> Explain
```

1. `Query_Spec` fetches only raw, schema-valid fields, explicit entity/join keys, and source
   filters. It never aggregates, ranks, limits, calculates, or joins fact branches.
2. Each `Processing_Spec` works on exactly one Scan result. It filters, extracts dates, and
   aggregates that fact branch at its declared natural entity grain.
3. `Final_Spec` merges processed branches only on explicit schema-derived key(s), then applies
   final grouping and measures, derived values, ranking, limits, and final rounding.
4. A raw one-to-many fact table is always locally aggregated before it is merged with another
   fact table. This is the generic two-level aggregation rule used by the benchmark SQL.
5. Every metric declares its source branch and column, local/final grain where relevant,
   operation, output column, and calculation stage. Null group values are preserved.
6. A shared normalizer fixes malformed nested identifier lists before contract validation and
   execution. Operators use exact declared fields in spec mode; they never silently select a
   similar name or a first numeric column.
7. Contracts check source classes, raw fields, branch outputs, merge inputs/keys, measure
   lineage, projections, and final-step fields before an operator executes.
8. Each repair loop has three total attempts. Unknown RDF terms, invalid raw field selection,
   or an unexpectedly empty Scan repair `Query_Spec` and rerun only that branch. Missing
   processed lineage repairs the affected `Processing_Spec`. Merge, aggregation, projection,
   ranking, or final-answer validation repairs only `Final_Spec`; it does not rerun a valid raw
   SPARQL scan unless the feedback proves that required raw data is missing.
9. Validation is against the original question and final specification. A validation failure is
   recorded as a structured error, never as `PIPELINE_SUCCESS`.

The CSV intentionally stores only final answer/status, validation result, timing, scan status,
and failure stage. Raw rows, intermediate branch rows, specs, and retry traces remain in memory
for the active run so the report stays small and evaluation-ready.
```
