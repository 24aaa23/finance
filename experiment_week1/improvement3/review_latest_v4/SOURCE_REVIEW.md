# Source review coverage and change targets

Inventory is generated from every Python source below run_pipeline_v4. Test files were inventoried and the suite executed; this is not a claim that mocked tests cover generated query semantics.

| File | Lines | Review disposition |
|---|---:|---|
| __init__.py | 2 | Package exports reviewed for active dispatch; no correctness change proposed. |
| __main__.py | 5 | Low-priority documentation correction: module docstring still refers to run_pipeline_v3. |
| clients.py | 48 | No primary correctness rewrite proposed; keep deterministic call configuration and record request provenance. |
| common.py | 192 | Keep runtime configuration stable during correctness comparison; no credential changes are needed for this review. |
| config.py | 28 | Keep cohort/model flags fixed for regression attribution; expose new contract modes explicitly when implemented. |
| connections.py | 82 | P1/P3: resolve missing schema paths and validate entity/composite join identity, beyond retaining already-declared keys. |
| dag.py | 6 | Keep compatibility export; no direct semantic failure found. |
| docs/completed_run_audit/audit_completed.py | 110 | Historical audit helper; do not mix its older cohort/results with latest 192-question evidence. |
| docs/completed_run_audit/replay_final_plans.py | 112 | Historical audit helper; do not mix its older cohort/results with latest 192-question evidence. |
| execution.py | 130 | Preserve operator dispatch; propagate new plan validation and intermediate diagnostics consistently. |
| executor.py | 810 | P5: route repairs to earliest responsible stage, expand schema when needed, preserve failing FinalSpec trace before return; add intermediate identity/null statistics. |
| grade_final_answers.py | 452 | P0: validate complete reference JSON; deterministic grouped/set/numeric/rank checks before optional semantic judgement; avoid universal numeric tolerance and prompt truncation. |
| llm_operators/__init__.py | 15 | Package exports reviewed for active dispatch; no correctness change proposed. |
| llm_operators/decompose.py | 222 | P1/P3: produce full metric/eligibility contract alongside raw branches; distinguish row versus aggregate predicates and canonical classes. |
| llm_operators/explain.py | 70 | Low priority: saved numeric final output is determined upstream; preserve deterministic presentation while fixing retrieval/plans. |
| llm_operators/filter_aggregate.py | 268 | P3/P4: retain strict SQL aggregation/null behavior; reject malformed intent such as != null upstream and support conditional aggregates through explicit expressions. |
| llm_operators/final_spec.py | 182 | P3/P4: consume metric contracts and construct independent summaries then eligibility joins then final groups; validate every requested metric. |
| llm_operators/generate.py | 104 | P2: render supported raw retrieval deterministically from the typed QuerySpec; validate any fallback against that contract. |
| llm_operators/integrate.py | 199 | P3/P4: active strict path uses relational runtime; improve upstream join planning, not legacy fuzzy merge/dedup behavior. |
| llm_operators/link.py | 38 | Legacy helper is not the main V4 connection mechanism; consolidate schema path logic only if brought into active execution. |
| llm_operators/order_by.py | 111 | P4: rank only complete correctly calculated candidates; specify typed sort and tie policy. |
| llm_operators/pre_scan_validate.py | 74 | P2: validate expanded class/property IRIs, bound-variable provenance, OPTIONAL/filter scope and exact retrieval contract, beyond SELECT syntax/projection. |
| llm_operators/processing_spec.py | 32 | Preserve deterministic raw-row pass-through; keep identity/grain metadata accurate. No extra branch LLM planner is necessary. |
| llm_operators/query_spec.py | 363 | P1/P2: strict operator/value/datatype validation; reject undeclared predicates and cross-branch reference strings; include repaired source schema. |
| llm_operators/query_spec_validate.py | 71 | P1/P2: retain semantic critique, but deterministic schema/domain checks must enforce source and requirement coverage. |
| llm_operators/refine.py | 75 | P2/P5: repairs must preserve original meaning and use structured failure reasons; do not reinforce incorrect decomposition requirements. |
| llm_operators/retrieve.py | 59 | P1: use meaningful schema descriptions and categorical domains; expand required neighbor classes during repair. |
| llm_operators/validate.py | 162 | P3/P5: semantic review can assist but cannot substitute for enforced metric, predicate and population contracts. |
| main.py | 678 | P0/P5: preserve run and grade provenance separately; store all attempt traces and avoid treating last-branch summary as complete evidence. |
| non_llm_operators/__init__.py | 9 | Package exports reviewed for active dispatch; no correctness change proposed. |
| non_llm_operators/bucket.py | 42 | P4: explicit ELSE/default/null policy and precise boundaries; do not invent undocumented bands. |
| non_llm_operators/check_schema.py | 24 | Legacy prefix/keyword guard is insufficient; use active expanded-IRI parser validation instead of relying on required prefix text. |
| non_llm_operators/date_extract.py | 30 | Retain existing extraction; ensure source date filters are applied before extraction and contract states month versus year-month. |
| non_llm_operators/difference.py | 126 | Retain strict relational set-difference path; choose entity-set output explicitly and reject cross-branch filter pseudo-references. |
| non_llm_operators/fuseki.py | 114 | Retain timeout/health handling. No evidence these transport paths explain the dominant semantic failures; snapshot identity is useful. |
| non_llm_operators/math_compute.py | 226 | P4: add validated conditional expressions where needed; preserve null subtraction and source-qualified operands, avoid implicit zero filling. |
| non_llm_operators/scan.py | 247 | P2/P5: verify declared keys/grain and query fidelity; retain null/numeric support; record complete scan schema and identity statistics. |
| non_llm_operators/set_intersect.py | 141 | Retain strict relational intersection; validate entity keys and distinguish set answers from repeated fact rows. |
| non_llm_operators/union.py | 30 | Retain explicit distinct_on semantics; avoid using duplicate branches as an implicit answer-shape repair. |
| planner.py | 36 | Keep fixed V4 DAG; semantic fixes belong in explicit contracts and compiler rather than model-generated operator routing. |
| relational.py | 227 | P3/P4: keep SQL null-unequal entity joins; use null-safe joins only for compatible aggregate group keys; expose cardinality assertions. |
| reporting.py | 13 | P0/P5: reference artifacts outside Excel cells; explicit invalid-reference status and durable linked report/debug artifacts. |
| run.py | 8 | No functional change required to direct launcher. |
| run_identity.py | 23 | P0: separate inference-source and grader fingerprints; bind reports to cohort and graph snapshot. |
| schema_loader.py | 290 | P1: populate source/field descriptions, owning class, ranges, optionality, and relationship cardinality in retrieval index; avoid multivalued connector projection inflation. |
| spec_contracts.py | 296 | P1/P3: extend contracts with predicate scope, metric expression/units, inner/outer aggregation, source lineage and participant population. |
| spec_runtime.py | 407 | P3: propagate grain, identity and column lineage; enforce metric coverage, unique summary keys and collision-safe explicit aliases. |
| tests/support.py | 77 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_comparative_steps.py | 156 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_connection_keys.py | 80 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_correctness.py | 358 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_final_review.py | 118 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_rdf_metadata.py | 98 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_rerun_query_spec.py | 94 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_rerun_spec_shapes.py | 120 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_simplified_flow.py | 145 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_v4_grader.py | 187 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_v4_planning.py | 112 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_v4_retrieval.py | 97 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| tests/test_v4_runtime.py | 124 | Existing offline tests: preserve and add source-to-query fidelity, unequal fact multiplicity, null/default, eligibility and positive-witness coverage. tests/support.py stubs term validation; these tests are not live end-to-end verification. |
| utils.py | 412 | P2: replace wm:-only term extraction with expanded-IRI AST checks and source property ownership; preserve exact literals during repair. |

Additional wrapper reviewed: ../grade_v4_3_files_terra.py. Its combine_graded_files() uses the original FILES_TO_GRADE even when --latest selects latest inputs. Pass the selected file list through combination or use one canonical batch runner; test --latest --combine without service calls.

Full file hashes and definition inventory are retained in evidence.json.