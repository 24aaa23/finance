# V4 operator usage and prompt cleanup

Updated 13 September 2026. Default version: `aop-improvement3-v4-short-prompts`.
See [FINAL_REVIEW.md](FINAL_REVIEW.md) for the subsequent full review: 148 tests,
exact RDF datatype preservation, optional raw properties and executed-query evidence.
An explicit `GPT_OSS_LLM_GRADER_PIPELINE_VERSION` environment variable overrides it.

Operators need not all run on every question. The fixed flow selects sources and
retrieves records; the compiled final plan invokes the calculations it needs.

| Operator | Where it runs | Calls the model in this flow? |
|---|---|---|
| Retrieve | Before the fixed graph: selects schema classes | Yes |
| Decompose | Before the graph: describes source branches | Yes |
| Query_Spec | Each branch: declares raw fields, keys, filters | Yes |
| Generate | Each branch: writes raw SPARQL | Yes |
| Pre_Scan_Validate | Each branch and retrieval repair: parser checks | No |
| Scan | Executes SPARQL against Fuseki | No |
| Refine | Repair after a scan failure | Yes, only on this repair path |
| Processing_Spec | Packages each branch's raw rows without aggregation | No |
| Final_Spec | Plans calculations across the retrieved tables | Yes |
| Filter_Aggregate | Compiled final steps: filtering/count/sum/avg/min/max | No in compiled execution; old standalone planning fallback remains |
| Integrate | Compiled final steps: joins | No in compiled execution; old standalone planning fallback remains |
| Order_By | Compiled final steps: sorting and limits | No in compiled execution; old standalone planning fallback remains |
| Math_Compute | Compiled final steps: arithmetic and copying columns | No |
| Date_Extract | Compiled final steps: date parts | No |
| Bucket | Compiled final steps: explicit numeric bands | No |
| Set_Intersect | Compiled final steps: keep left records with right matches | No |
| Set_Difference / Difference | Compiled final steps: keep left records without right matches | No; names are aliases |
| Set_Union / Union | Compiled final steps: combine records | No; names are aliases |
| Distinct | Handled inside the execution engine | No; not a separately registered operator |
| Combine_Scalars | Compiler-generated combination of single-row measures | No; handled inside execution |
| Validate | Structural checks, plus optional final model review | Model only when FINAL_SEMANTIC_REVIEW=1; still off by default |
| Explain | Returns structured results, or formats prose if configured | No for normal structured output; optional prose path uses the model |
| Classify | Not needed by the fixed flow | File, registration, imports and unused executor handling removed |
| Extract | Not needed by this flow | File, registration and imports removed |
| Link | Its advisory join_conditions are not consumed by the compiled plan | Removed from active registry and package imports |
| Query_Spec_Validate | Redundant branch critic, not called | Removed from active registry and package imports |
| Check_Schema | Not scheduled by the fixed flow | Removed from active registry and package imports; Scan's own term checks remain |

Classify and Extract have now been deleted from V4. The other three inactive
implementation files remain as legacy code, without imports or registrations in
the V4 launcher. No new model operator was added.
The planner builds the fixed graph in Python, without a planner-model call.

## Prompt changes

- Decompose defines source class, branch, record identity, conditions and connection
  fields. It no longer refers to an undefined Query_Spec stage, requests a full metric
  specification, or asks for every output/weighting/null-policy detail up front.
  It retains the small predicates/joins declarations used by existing contract checks.
- Query_Spec defines a retrieval specification before using the name. It receives
  shared predicates and joins once, instead of a complete decomposition plus a second
  copy of answer requirements. Raw fields, optional fields and typed filters are defined.
- Generate receives one active retrieval and one schema block, removing repeated
  full specifications and duplicated schema rule text. Its rules still cover exact
  field aliases, typed identity, optional bindings, filter scope, dates and raw rows.
- Refine preserves the same raw retrieval rules unconditionally. Its prompt and
  both executor timeout hints no longer recommend aggregates or an easier source.
- Retrieve explains its class index and no longer shows a concrete example class
  name that may not exist in the supplied schema.
- Final_Spec retains documented operation syntax. It defines table, step, projection,
  identity representation, existence/absence operations, null helpers, and the missing
  retrieval response. It distinguishes averages across records from averages across
  entity summaries instead of broadly forbidding averages of averages.
- Optional Validate defines IRI and checks entity meaning, not only representation.
- Explain's optional prose prompt is shorter and acknowledges a sample when supplied.
- Shared system prompts state each task directly, without experience/persona claims.

Static template word counts (not token counts, and excluding expanded schema/data):

| Prompt | Before | After |
|---|---:|---:|
| Decompose | 671 | 359 |
| Query_Spec | 541 | 363 |
| Generate | 1057 | 291 |
| Refine | 491 | approximately 205 |
| Explain | 168 | 61 |

Retrieve adds short definitions; Final_Spec retains its operation reference. Making
every prompt shorter at the expense of defining its output format would be unsafe.
The JSON response readers, normalization, compiler and computation semantics remain
compatible with existing plans. Original questions and literal conditions still travel
through the flow. No reference SQL or expected answer was added to a prompt.

## Shared linking keys

`connections.py` carries the decomposition's declared connections into each raw
retrieval in Python, without a model call. It checks endpoint branches, source
fields, equal-length composite keys, and incompatible entity identities when the
schema proves the mismatch. It copies omitted, schema-valid linking fields into
the branch's selected fields and preserves the RDF subject identity. Newly added
property keys are optional so fetching a key does not itself discard base records;
the requested join or explicit filter determines eligibility later.

This is limited to declared connections. It does not invent a missing connection,
choose an undocumented path, or prove two arbitrary literal keys share a domain.
Generate still must bind the selected keys correctly, and Final_Spec must use the
appropriate connections and calculations. The larger connection-discovery and
deterministic retrieval work remains in the correctness plan.

## Checks and limits

All 138 offline tests pass, including six shared-key cases and four comparative-step/handoff cases. Final_Spec now receives declared connections and each branch's task, and its short calculation guidance covers entity-plus-category summaries and ranking after merges. See [comparative review](../diagnosis_20260913/COMPARATIVE_REVIEW.md). The production V4 main module imports successfully
after registry/import cleanup. No external model call or end-to-end grading run was made.
This is prompt simplification, unused-operator cleanup and declared-key preservation, not completion of the larger
correctness plan in `../diagnosis_20260913/V4_CORRECTNESS_PLAN.md`. In particular, the
typed deterministic retrieval builder, schema connection enforcement, branch-local
repair and full data/SQL evaluation are still separate work. Prompt instructions alone
do not guarantee those invariants or establish an accuracy improvement.

Use fresh report files for the next run, so these prompts are not mixed with the saved
192-question baseline. Compare final-answer grades as well as execution completion.
