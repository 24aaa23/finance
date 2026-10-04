# Source metric catalog

The pipeline has no built-in financial metric definitions. A data owner can supply a versioned JSON catalog with `SEMANTIC_CATALOG_FILE=/absolute/path/catalog.json` (or a path relative to `script_diff_llm2`). The file is optional. A missing or invalid configured file stops startup; the runtime never silently falls back to invented definitions.

```json
{
  "version": "source-metrics-v1",
  "metrics": [
    {
      "id": "total-charge-per-customer",
      "backend": "sql",
      "source": "charges",
      "fields": ["amount"],
      "terms": ["total charge"],
      "definition": "Sum of charge amounts for each customer in the eligible population",
      "formula": "SUM(amount) per customer",
      "unit": "source currency",
      "provenance": "data owner's metric dictionary, version 1"
    }
  ]
}
```

These names are illustrative synthetic data, not a built-in rule. Each `source` and `fields` entry must exist in the live SQL or KG schema. `backend` is `sql` or `kg`. `terms` select definitions for a subquery by matching its wording; the prompt receives only matching definitions from the retrieved schema slice. `provenance` must identify an independently authored source. Do not construct this file from benchmark questions, reference answers, grader feedback, or held-out results. Domain labels, formulas, units and thresholds belong in this source-owned catalog only when documented by that source; otherwise Query_Spec must mark the requirement unresolved.

For cross-backend set operations, a source owner may add `identity_bindings` at the top level:

```json
"identity_bindings": [
  {
    "kg_uri_prefix": "https://source.example/id/customer/",
    "sql_source": "customers",
    "sql_field": "customer_id",
    "provenance": "source owner's URI-to-SQL identifier mapping, version 1"
  }
]
```

The binding declares that the IRI suffix in this KG namespace is the exact SQL identifier. Without it, the executor keeps full IRIs and uses exact set keys; it does not guess equivalence from a shared suffix, punctuation, case or an incidental overlapping column. The SQL field must exist in the live schema. Identity bindings should be independently verified against source data before use.

The catalog helps the model interpret named metrics. It does not prove that generated SQL/SPARQL implements a definition correctly; review and held-out evaluation are still required.

## Generic source grounding without a catalog

With `SEMANTIC_CATALOG_FILE=""`, SQL schema loading still reads declared primary and foreign keys and profiles small text domains directly from the configured database. Each DISTINCT probe has an instruction budget and a 32-value limit; large, interrupted or long-text domains are omitted. An omitted domain does not imply that its values are invalid. Published `allowed_values` are complete non-null domains at schema-load time. This metadata uses source data only, not reference answers or grader feedback. Only a unique case-insensitive match in the same field may restore stored spelling; cleanup never moves a value to another field.

This is schema/value evidence, not extraction of business definitions. Units, eligibility definitions, sign conventions and named metric formulas still require explicit question wording or independently supplied source metadata. RDF schema metadata also exposes observed literal datatype URIs, allowing direct typed-date versus string comparisons to be rejected before execution.

The computation contract distinguishes shared `filters` from each measure's `population_filters`. A measure may declare `missing_entity_value: 0` for an absent event count when justified. Internal calculation and ranking aliases can be omitted from `output_schema`; final projection follows that schema. Final-group formulas list intermediate aliases in `formula_fields`. Requirement prose and ledger-reference defects remain visible warnings, while unknown physical fields, unresolved definitions, invalid operations, unknown derived aliases and cyclic dependencies still block execution.

Run instructions for this revision: [generic pipeline v2](generic_pipeline_v2_run.md).


## Computation stages in v3

`operand_kind` distinguishes `physical` source columns from `aliases` of previously computed measures. Computation stage does not determine operand identity: physical aggregates do not need an arithmetic formula. Physical expressions use `formula_stage: row`, while final aggregate-alias expressions use `formula_stage: final_group` with `source_class: derived`.

A measure's `population_filters` operate before aggregation. Its `aggregate_filters` operate after aggregation and declare the owning output alias, operator/value, `stage: entity|final_group` and `scope: population|metric`. A population-scoped entity predicate constrains the shared eligible universe for other metrics too. A metric-scoped predicate affects only that metric. An average threshold must not discard low-valued input rows before calculating the average.

Legacy predicates explicitly marked `source_class: derived` and referencing their owning measure are moved from population_filters into aggregate_filters; indexed ledger references follow the move. Physical thresholds are not automatically reinterpreted. RDF datatype extraction now supplies actual observed literal URIs to the date validator. SQL pre-scan validation first prepares the query with EXPLAIN against the configured read-only database.

Use a fresh output folder and version for [the v3 run](generic_pipeline_v3_run.md); do not append v3 results to v2 reports.


## RDF value grounding and SQL scan repair in v4

RDF startup metadata now includes complete small text domains and source-authored descriptions. Text domains retain their owning class and predicate. Domains over 32 distinct lexical values or containing values longer than 256 characters are omitted; failed endpoint profiling preserves the physical schema without inventing values. Encoded serialization preserves punctuation and delimiter characters. Standard RDF labels remain visible, and colliding predicate local names are represented by full URIs rather than merged.

SQL scan repair preserves the Query_Spec and bound upstream values. Only query defects trigger model regeneration; environment/connection failures remain terminal. Repaired queries pass deterministic shape checks and pre-scan validation before execution. The repair budget is shared across the node's execution, and model repair bypasses the deterministic fast path when failure feedback is present. These checks improve execution reliability; they do not establish business semantics or guarantee a match.

Use a fresh folder and pipeline version for [v4](generic_pipeline_v4_run.md). The v3 commands remain a record of that earlier revision; do not append current-code results to an existing v3 run.
