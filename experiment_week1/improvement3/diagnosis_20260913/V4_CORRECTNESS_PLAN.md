# V4 correctness review and implementation plan

Reviewed 13 September 2026. This document is a plan, not a claim that the changes below have been implemented. Production V4 files and saved reports were not modified in this review. The accompanying `audit_v4.py` reads saved reports and reference SQL, queries local Fuseki, and writes `evidence.json`.

## What was verified

All three saved V4 source manifests match the current source files. The reports cover 192 unique questions, not the full 442-question workbook.

| Outcome | All 192 | Comparative subset, 76 |
|---|---:|---:|
| MATCH | 64 | 1 |
| PARTIAL | 31 | 5 |
| MISMATCH | 55 | 33 |
| Execution failure | 42 | 37 |

These are the existing grader's verdicts. There are 150 completed executions, 31 final-plan failures, 10 retrieval-spec failures, and one pre-scan failure. Of the 31 final-plan failures, 28 report missing retrieval requirements. Failure categories overlap; do not add individual semantic causes to obtain a total.

### Direct database and reference checks

1. **MC-001, averages of goal measures:** local Fuseki contains 4,865 goal subjects. The saved mandatory bindings retain only 4,306, dropping 559 records before aggregation. Independently optional measure bindings and per-column null-aware averages reproduce all seven reference groups and all 21 rounded metrics exactly.
2. **WM-1T-013, cash-flow counts and totals:** preserving all 7,828 subjects, optional amount values, and missing type relationships reproduces all nine reference groups, their counts, and their totals exactly. There are 391 records with no type relationship. Requiring amount also loses transactions whose amount is null, changing COUNT(*) even when SUM(amount) happens to remain correct.
3. **WM-1T-020, dates:** the RDF date property is `xsd:date`. Replaying the saved string-boundary comparison gives zero matches. Using typed date bounds for the same calendar year gives 1,448 matches. This count tests retrieval, not the full monthly answer.
4. **MC-006 and MC-035, comparative calculations:** retrieved raw RDF subjects for Investor (1,550), PortfolioHolding (15,102), InvestmentGoal (4,865), and PortfolioHealth (1,550), preserved nulls, and loaded temporary in-memory SQLite tables using explicit evaluation-only column mappings. Executing the supplied reference SQL unchanged reproduces all six groups and every rounded metric for each question. Checked that selected RDF properties did not multiply subject rows in this reconstruction.

The last check establishes that the current RDF data can support those two comparative reference answers. It does not establish parity for the entire dataset, and it does not make SQL/ground truth part of inference. The checked-in audit mappings are diagnostic fixtures only.

## Root causes and corrections to the earlier diagnosis

### Source meaning and paths are lost before calculation

- WM-2T-002 changes Conservative risk tolerance into `Investor.category = "Conservative"` during decomposition. Current investor category values contain no Conservative category.
- MC-035 selects Category, InvestmentGoal, and PortfolioHealth, omits the Investor connection, then treats a Category subject as an Investor subject. Merely checking that both join values are IRIs is insufficient: their target entity classes differ.
- MC-074 asks for an investor ID on the Category dimension. The missing requirement is a relationship path through the profile source, not permission to invent that column on Category.
- MC-006 uses holding category instead of investor profile category. A valid join and an existing column can still express the wrong business meaning.

Source metadata is weak: `schema_loader.py` initializes class descriptions to empty strings, while `get_lightweight_table_index` passes only names of columns. The schema file has useful business descriptions on Primitive metadata nodes, not directly on every OWL class. A fix must establish a valid metadata-to-class association; it must not blindly attach a similarly named description. Exact RDF datatypes are collapsed into broad numeric/categorical types, which loses the date distinction needed by filters.

The saved `Debug Retrieved Classes` entries are empty even for successful multi-source plans. This is a logging defect: executor initializes `retrieved_classes=[]`, and main's `setdefault` does not replace that empty list with the pre-DAG Retrieve output. These cells do **not** prove Retrieve selected no classes. Fix the provenance before attributing particular source-selection failures to Retrieve rather than Decompose.

### Prompts repeat decisions instead of making them durable

Decompose currently specifies retrievals, metrics, populations, weighting, joins, output grain, null policy, sorting, projection, and predicates. Query_Spec receives the complete decomposition and a second copy of answer requirements. Generate interprets the original question again alongside those declarations. Each transition permits another interpretation of the same condition.

The existing optional-field instructions did not enforce optional retrieval in the saved examples. Pre_Scan_Validate checks syntax and projection, so a syntactically valid population-changing query passes. Refine still contains older instructions that allow choosing the most relevant class if joining is difficult; this contradicts preserving the original question.

### Comparative calculations have distinct levels

For MC-006 the reference is: sum holdings per investor, join to investor profile, then average investor totals by profile category. For MC-068 allocation concentration means maximum allocation per investor followed by a group average. V4 can execute these operators, but chooses a different plan.

Do not replace this with a blanket rule to aggregate every table before every join. That can also change the answer. Distinguish:

- Average across observations: each non-null fact contributes; combining partial averages requires their non-null counts.
- Average across entities: each qualifying entity contributes one summary; averaging entity averages is appropriate when that is the requested definition.
- Independent measures: each measure ignores its own missing inputs, without dropping records needed by other measures.
- Existence and absence: use semi/anti joins, preserving the requested base population, rather than multiplying fact rows.

### Some expected semantics are unstated

MC-002 does not state the reference's 33/67 band boundaries. MC-006 says compare, while SQL chooses averages of per-investor totals. Other comparative questions rely on definitions such as allocation concentration. Treat these as documented business semantics or clarify the question. Do not encode question IDs, hidden expected answers, or a rule that every comparison means AVG.

## Implementation order

### 1. Make the existing retrieval contract reliable

Files: `schema_loader.py`, `llm_operators/query_spec.py`, `llm_operators/generate.py`, `llm_operators/pre_scan_validate.py`, `llm_operators/refine.py`, and provenance in `executor.py`/`main.py`.

- Keep exact observed RDF datatypes alongside normalized logical types. Build date/numeric filter literals from those types, including explicit treatment of date versus datetime and calendar intervals.
- Retain the typed subject as observation identity. Display fields, measures, grouping fields, and optional relationship attributes must not become row-presence conditions merely because they are projected. Explicit predicates and required relationships still control eligibility.
- Generate the supported single-source raw SELECT deterministically from the validated branch contract: subject binding, exact predicates, optional bindings, and an explicit filter expression tree. This replaces interpretation inside Generate; it is not an additional model stage. Do not flatten OR/AND/NOT into a list, add DISTINCT, or coerce unknown filters to a different operation. Unsupported constructs must return a precise contract error for bounded repair.
- Preserve raw projected values when filters require casts. Check subject/property cardinality before assuming one RDF subject produces one tabular row; never use DISTINCT to hide multiplication from multivalued properties.
- Persist the SPARQL actually executed after repair and the corresponding branch contract. Correct the empty retrieved-class debug field.

Acceptance: generic null/optional/date fixtures agree with SQL; the confirmed population errors above disappear under local replay. No whole-question semantic critic is added to each raw branch.

### 2. Resolve connections before fetching branches

Files: schema metadata helpers, `decompose.py`, `query_spec.py`, `final_spec.py`, and compiler join metadata.

- Expose a compact relation catalogue: source class, exact property, target class, key representation, and available cardinality/nullability evidence.
- Decompose selects sources and the meaning of their connections. Code resolves these against actual schema paths and requires both ends of each selected connection in the branch fields.
- Prefer a declared direct relationship or a verified common key domain. Matching field names, both values being IRIs, or picking the shortest path alone does not prove semantic equivalence.
- Add a necessary connecting source when the selected relationship requires it; do not enumerate unrelated classes. If multiple paths represent different meanings, repair that choice locally instead of guessing.
- Pass connection metadata through aggregation lineage: an investor reference grouped into a summary still identifies investors, while a Category subject still identifies categories.
- A missing field on an existing source repairs that branch. A missing source/path repairs the source selection. Reuse unaffected scans; avoid rerunning the entire decomposition for every missing key.

Acceptance: disconnected category/fact plans are corrected before final execution; joins between incompatible entity types are rejected. A legitimate literal-ID join still works where the domain is established. Empty results remain valid when the correct relationship and predicates yield no matches.

### 3. Shorten prompts by assigning each stage one responsibility

- **Retrieve:** compact schema selection with meanings and possible connections.
- **Decompose:** which source branches are needed and why, preserving the original conditions and relationship scope. Remove global metric JSON, output aliases, null-policy prose duplication, and DAG/operator planning.
- **Query_Spec:** one active branch's fields, identity, required linking fields, and typed filters. Supply that branch's relevant schema and connection requirements instead of the full duplicated decomposition.
- **Generate:** the deterministic contract-to-SPARQL function from step 1.
- **Final_Spec:** one ordered calculation plan over actual available tables, their meanings, connections, and the original question. This is where aggregations, formulas, grouping, sorting, and final projection are chosen.

Keep original text available as the authority without instructing every stage to redesign the whole answer. Preserve a small source-scoped predicate contract so shortening prompts does not weaken condition checking.

### 4. Make comparative meaning explicit in the final plan

Files: `final_spec.py`, supported operator schemas, and compiler metadata.

- Represent per-entity summaries and final group calculations as ordinary ordered existing steps. The operator engine already supports sums, averages, maxima, joins, formulas, filters, and sorting.
- Give each metric its necessary grain and population, using small examples with unrelated names. Avoid a second large semantic specification duplicating every step.
- Preserve the appropriate join population: inner for explicitly required participation, left for retaining a base population with missing related facts, and semi/anti joins for existence/absence.
- Use verified domain definitions for terms such as concentration or net cash flow when available. Store definitions with schema/business documentation, not benchmark IDs. Record unresolved ambiguity instead of silently inventing a metric.
- Do not add a new operator unless a reproducible required calculation cannot be represented by current primitives.

Acceptance: synthetic two-fact examples with uneven observations per entity, missing values, and unequal participation match independently written SQL. Measure the separate 76-question comparative subset in subsequent model runs, not just overall execution success.

### 5. Remove inactive code after the contracts are stable

- Remove Classify, Extract, the old advisory Link, and the redundant Query_Spec_Validate from V4 imports/registration and remove their files only after checking references. Adding these LLM calls does not enforce the missing invariants.
- Fold Processing_Spec's pass-through behavior into dataset packaging if its contracts and report lineage can be preserved. Do not create another computation planner in its place.
- Retain Filter_Aggregate, Integrate, Math_Compute, Order_By, Date_Extract, Bucket, distinct, and set operations. They are called from compiled Final_Spec steps even if absent as top-level DAG nodes. Zero usage in one sample is not evidence an operation is globally unnecessary.
- A useful connection resolver replaces the responsibility of Link; simply wiring the existing unconsumed `join_conditions` output into the DAG is insufficient.

### 6. Evaluate correctness after each meaningful increment

- Freeze the current 192-row scores as the baseline and use fresh report filenames and source/input hashes.
- First use local SQL differential fixtures and the recorded failure replays. Then evaluate a fixed mixed subset covering existing matches, null groups, dates, profile dimensions, existence, and multilevel comparisons.
- Grade every completed final candidate, including reviewer-rejected candidates, to avoid reporting accuracy only on a selected subset. Keep runtime completion, optional reviewer verdict, and independent grade separate.
- A model reviewer is fallible. If retained, supply actual executed SPARQL, predicates, connection meanings, compiled calculations and row counts; a final-row sample alone cannot establish correctness. Do not use repeated critic loops as the main repair mechanism.
- Track MATCH out of all attempted rows and comparative MATCH separately; PARTIAL is not a correct answer for the target. Report execution failures separately. Run all 442 only after the changes improve the fixed comparison without unexplained regressions, then evaluate the remaining unseen questions without tuning to their answers.

## Intended flow

```mermaid
flowchart LR
    Q[Question] --> S[Select sources and connections]
    S --> B[Small branch contracts]
    B --> R[Build typed raw retrievals and scan]
    R --> F[One final calculation plan]
    F --> E[Compile and execute existing operators]
    E --> A[Final rows and execution evidence]
    A --> G[Independent correctness grading]
```

Connection checking and retrieval generation are Python helpers within this flow, not additional LLM planners. The goal is fewer places where the model can reinterpret a decision.

## Limits

Four checked examples reproduce reference results from the current RDF data; that is strong evidence for the corresponding fixes, not an end-to-end model accuracy improvement. No new external model run or grading call was made during this review. No claim of 350 correct answers is justified until a fresh full evaluation measures it.
