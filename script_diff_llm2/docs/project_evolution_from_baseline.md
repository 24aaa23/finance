# Project Evolution From the Original Baseline

This document reconstructs the major and minor changes made to `script_diff_llm` from the original baseline idea to the current repository state.

Important note:

- The exact "pre-decomposition" baseline is not preserved as a clean standalone branch in the current canonical tree.
- This document is reconstructed from the surviving legacy templates, commit history, the current codebase, and the restructuring work completed in this repository.
- It is meant to explain how the system evolved, why each change was made, and what practical impact it had.

## 0. Original Baseline

### Baseline architecture

The earliest baseline was conceptually much simpler:

```text
user query
  -> one pipeline
  -> one backend choice or one end-to-end generation path
  -> execute
  -> answer
```

The key characteristics of that baseline were:

- the system did not treat the user query as a DAG of atomic subqueries
- SQL/KG routing was not a first-class subquery-level planning problem
- planning, generation, validation, execution, reporting, and explanation lived in very large monolithic files
- model experiments were mostly duplicated across many model-specific folders
- data paths and runtime assumptions were more tightly coupled to those model folders

### Why the baseline was limiting

This baseline was hard to extend for hybrid questions because:

- many benchmark questions naturally mix relational facts and graph relationships
- one-shot routing at whole-query level loses structure
- comparative and multi-step questions need intermediate results, dependencies, and deterministic merges
- copied model directories made maintenance expensive and error-prone

### Baseline impact

- simple end-to-end experiments were easy to run
- model comparison was straightforward at a folder level
- maintainability, reproducibility, and architectural clarity were weak
- hybrid SQL+KG reasoning was under-specified

## 1. Introduced Query Decomposition and the Subquery DAG

### What changed

The most important research change was the move from whole-query handling to subquery-level planning:

```text
user query
  -> semantic decomposition
  -> atomic subqueries
  -> DAG construction
  -> per-node SQL/KG routing
  -> backend execution
  -> dependency propagation
  -> deterministic merge / set operation
  -> final answer
```

### Why it was introduced

This change addressed the central weakness of the original flow:

- many benchmark queries are compositional
- some parts are naturally SQL-shaped
- some parts are naturally KG-shaped
- some parts are deterministic set or aggregation operations and should not be delegated back to the LLM

### Impact

Major impact:

- enabled mixed SQL/KG queries
- enabled parallel execution of independent subqueries
- made dependency handling explicit
- made multi-step logic auditable through node traces and DAG levels

Tradeoff:

- planning complexity increased
- failure analysis moved from "one query failed" to "which node/stage failed"

## 2. Made SQL/KG Routing a Per-Subquery Decision

### What changed

Routing stopped being implicitly whole-query and became explicit per atomic subquery.

The active architecture now supports:

- SQL-only DAGs
- KG-only DAGs
- mixed DAGs
- deterministic `Set_Intersect`, `Set_Union`, and `Set_Difference`

### Why it was introduced

Because decomposition alone is not enough. After splitting a query, the system still needs to decide:

- which nodes should execute against SQLite
- which should execute against Fuseki
- which should execute as deterministic operators

### Impact

- preserved the research idea instead of collapsing everything back into one backend
- reduced forced overuse of either SQL or KG
- made cross-backend hybrid execution possible

## 3. Standardized the KG Backend on Apache Jena Fuseki

### What changed

The current implementation treats Fuseki as the real KG execution backend.

Current KG runtime:

- schema/metadata from `data/kg/wealth_management_diverse_schema.ttl`
- instance graph hosted in Fuseki
- endpoint: `http://127.0.0.1:3030/wealth/query`

### Why it was introduced

Earlier RDF helper paths were useful for local inspection, but they were not the right primary execution path for the production benchmark flow.

The current design needed:

- an actual SPARQL endpoint
- realistic execution behavior
- dynamic metadata extraction from the hosted graph

### Impact

- aligned the code with the real KG backend
- reduced confusion about rdflib vs Fuseki responsibilities
- made KG pre-scan and scan behavior more realistic

## 4. Preserved the Real Physical SQLite Schema

### What changed

The SQL backend was kept grounded in the actual `ATOM_*` tables in:

- `historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db`

The code now consistently distinguishes:

- `sql_schema`: physical SQLite tables/columns
- `kg_metadata`: ontology/classes/properties/relationships

### Why it mattered

There was a real risk of accidentally inventing semantic SQL tables such as `Investor` or `CashFlow` as if they physically existed in SQLite.

That would have made prompts cleaner but execution wrong.

### Impact

- protected the SQL path from schema hallucination
- made SQL generation more trustworthy
- preserved compatibility with the real benchmark database

## 5. Extracted a Canonical Shared Pipeline

### What changed

The codebase moved away from treating one model folder as the main implementation.

The shared runtime now lives under:

- `src/script_diff_llm/`

Key entry point:

- `src/script_diff_llm/pipeline/core_pipeline.py`

Legacy shim:

- `src/script_diff_llm/pipeline/gpt_oss_pipeline.py`

### Why it was introduced

The repository contained many model directories with heavily duplicated pipeline logic. That made it hard to know:

- what was actually shared behavior
- what was model-specific configuration
- what was just archived experiment code

### Impact

- one canonical place for the active pipeline
- model runs can share core logic
- historical trees remain available without defining the active architecture

## 6. Externalized Model and Experiment Configuration

### What changed

Model/runtime config moved into YAML:

- `configs/models/*.yaml`
- `configs/experiments/*.yaml`

Supporting loaders:

- `src/script_diff_llm/config/runtime.py`
- `src/script_diff_llm/config/paths.py`
- `src/script_diff_llm/config/experiments.py`

### Why it was introduced

Previously, too much configuration lived inside runners or model-specific scripts:

- model IDs
- endpoint env names
- benchmark files
- SQL asset paths
- output directories

### Impact

- switching models became largely config-driven
- canonical runners stopped hardcoding experiment details
- environment overrides remained available without baking secrets into code

## 7. Reorganized the Repository Around Clear Responsibilities

### What changed

The repository was restructured into clearer surfaces:

- `src/`: active shared source code
- `runners/`: canonical run entrypoints
- `configs/`: model and experiment configuration
- `data/sql/`: SQL manifests and notes
- `data/kg/`: KG assets
- `data/benchmarks/`: benchmark files
- `tests/`: unit/integration/regression checks
- `outputs/`: generated reports
- `historical_models/`: archived experiments
- `base_templates/`: reference/legacy templates

### Why it was introduced

The previous root was crowded with model trees and duplicated artifacts, which hid the actual architecture.

### Impact

- a new developer can now find the active pipeline quickly
- generated files are separated from source code
- historical experiments remain accessible without dominating the root layout

## 8. Grouped Historical Model Trees Under `historical_models/`

### What changed

Root-level model experiment directories were grouped under:

- `historical_models/`

### Why it was introduced

Those directories are useful for:

- archived outputs
- older prompts
- older grading scripts
- historical comparisons

But they should not be mistaken for the current implementation.

### Impact

- reduced root clutter
- clarified canonical vs archival code
- preserved backward compatibility where still needed

## 9. Normalized Path Handling

### What changed

The active pipeline now uses repo-relative and config-driven path resolution instead of machine-specific absolute paths.

### Why it was introduced

The repository previously carried a risk of breakage from:

- hardcoded home-directory paths
- assumptions tied to a specific model folder
- root-level compatibility directories such as `dataset/` or `kg/`

### Impact

- easier to run on another machine
- fewer path regressions after restructuring
- cleaner interaction between runners, assets, and outputs

## 10. Split the Monolithic Pipeline Into Architectural Modules

### What changed

The earlier large GPT-OSS pipeline module was progressively separated into coherent modules:

- `src/script_diff_llm/pipeline/decomposition.py`
- `src/script_diff_llm/pipeline/specification.py`
- `src/script_diff_llm/pipeline/kg_pipeline.py`
- `src/script_diff_llm/pipeline/explanation.py`
- `src/script_diff_llm/pipeline/registry.py`
- `src/script_diff_llm/pipeline/dag/planner.py`
- `src/script_diff_llm/pipeline/dag/executor.py`
- `src/script_diff_llm/evaluation/benchmark_io.py`
- `src/script_diff_llm/evaluation/reporting.py`

### Why it was introduced

The monolith mixed too many concerns:

- configuration
- benchmark I/O
- decomposition
- DAG planning
- operator wiring
- Query_Spec generation
- KG lifecycle
- explanation
- report persistence

### Impact

- responsibility boundaries became visible
- targeted testing became easier
- future changes can focus on one stage without destabilizing the whole file

## 11. Separated DAG Planning From DAG Execution

### What changed

Planning and execution became distinct responsibilities:

- `dag/planner.py`: what graph should run
- `dag/executor.py`: how the graph runs

### Why it was introduced

The conceptual boundary matters:

- planner decides structure, dependencies, and backend labels
- executor handles ordering, parallelism, binding, retries, and status

### Impact

- easier debugging of graph construction vs graph runtime failures
- cleaner testability
- less orchestration code packed into one file

## 12. Extracted Benchmark Loading and Report Persistence

### What changed

Benchmark/reporting responsibilities moved into:

- `src/script_diff_llm/evaluation/benchmark_io.py`
- `src/script_diff_llm/evaluation/reporting.py`

This covers:

- benchmark row loading
- normalization
- report schema
- incremental CSV persistence
- resume/pending-query behavior

### Why it was introduced

Benchmark I/O is not pipeline semantics. Keeping it in the main orchestrator obscured the actual reasoning pipeline.

### Impact

- preserved resume behavior while clarifying ownership
- made benchmark/report changes safer
- reduced orchestrator complexity

## 13. Extracted Operator Registry Construction

### What changed

Registry wiring moved into:

- `src/script_diff_llm/pipeline/registry.py`

### Why it was introduced

Operator construction and dependency injection are separate from operator implementation.

The system needed a clean answer to:

- what operators exist
- what names they are registered under
- what dependencies each receives

### Impact

- canonical registry is now explicit
- operator naming stayed stable while implementations moved
- orchestration code got simpler

## 14. Extracted Semantic Decomposition

### What changed

`semantic_decompose` was moved to:

- `src/script_diff_llm/pipeline/decomposition.py`

### Why it was introduced

Decomposition answers one question:

- what subqueries are needed

It should not be mixed with:

- DAG graph representation
- Query_Spec generation
- backend execution

### Impact

- planner now consumes decomposition instead of owning it
- decomposition prompt logic has a clear home
- boundary between semantic splitting and DAG construction is explicit

## 15. Extracted Query_Spec Construction and Cleanup

### What changed

The Query_Spec stage moved into:

- `src/script_diff_llm/pipeline/specification.py`

Core functions:

- `semantic_build_query_spec`
- `cleanup_query_spec`

### Why it was introduced

The Query_Spec acts as the semantic contract between natural-language intent and backend query generation.

That is a distinct stage from:

- decomposition
- DAG planning
- query execution

### Impact

- made Query_Spec the visible IR of the system
- made downstream SQL/SPARQL generation easier to reason about
- created the right place for cleanup heuristics and semantic repair

## 16. Extracted the KG Lifecycle as One Module

### What changed

The KG backend-specific lifecycle moved into:

- `src/script_diff_llm/pipeline/kg_pipeline.py`

It now owns the coherent KG path:

```text
Retrieve
  -> Generate SPARQL
  -> Refine
  -> Pre_Scan_Validate
  -> Scan
```

### Why it was introduced

Splitting `semantic_generate_sparql` alone would have been the wrong boundary.

These functions form one backend-specific lifecycle with shared dependencies and repair behavior.

### Impact

- KG execution logic is now grouped coherently
- orchestrator no longer pretends KG stages are unrelated
- easier to improve KG execution without touching unrelated pipeline code

## 17. Extracted Final Answer / Explanation

### What changed

Final answer shaping moved into:

- `src/script_diff_llm/pipeline/explanation.py`

This module owns:

- row cleaning
- list/count detection
- normalization for final answer
- deterministic structured return vs LLM explanation

### Why it was introduced

Explanation is a cross-backend finalization stage, not part of KG generation or SQL execution.

### Impact

- final answer behavior became independent of backend
- SQL, KG, and hybrid outputs reach one normalization/explanation stage
- the orchestrator became closer to pure assembly

## 18. Cleaned the Canonical Operator Surface

### What changed

Legacy operators were removed from the canonical registry:

- `Validate`
- `Classify`
- `Check_Schema`

Their implementations were preserved for historical compatibility, but they are no longer wired into the active canonical pipeline.

### Why it was introduced

Read-only auditing showed these were not part of the canonical GPT-OSS DAG path:

```text
Decompose -> DAG Planner -> DAG Executor -> SQL/KG -> Set Ops -> Explain
```

### Impact

- active architecture became cleaner and more truthful
- historical runners still kept access to legacy logic
- reduced confusion about which operators actually matter today

## 19. Added Canonical Tests and Strengthened Regression Verification

### What changed

The repository now relies on clearer validation layers:

- compile checks
- unit tests
- integration tests
- DAG regression tests
- smoke runs with `TEST_QUERY_LIMIT`

Canonical test areas include:

- paths/config
- SQLite backend
- subquery DAG behavior
- semantic contract behavior
- set-operation key normalization

### Why it was introduced

Compilation alone was never enough for a pipeline this dynamic.

### Impact

- structural refactors were repeatedly verified without breaking behavior
- regressions became easier to localize
- confidence increased when moving code between modules

## 20. Improved Benchmark Resume and Incremental Persistence

### What changed

The pipeline now supports reliable incremental raw reporting and resume behavior in the canonical flow.

### Why it was introduced

Long benchmark runs should not restart from scratch after interruption.

### Impact

- easier to complete large train runs
- lower risk of losing long-running pipeline progress
- safer repeated experimentation

## 21. Added Semantic Contract Validation After Successful Execution

### What changed

A new semantic validation layer was introduced in:

- `src/script_diff_llm/pipeline/semantic_contract.py`

It validates post-execution result shape against Query_Spec expectations.

Examples of checks added:

- missing expected output columns
- grouped query collapsed to a single row
- ranking missing identity or metric
- ranking wrong order or limit
- duplicate entity keys
- bucket/band outputs returned as raw numeric groups
- month-level query leaking raw `date`
- invalid aggregation staging requirements

### Why it was introduced

Execution success does not imply semantic correctness.

Before this layer, the pipeline could return plausible but structurally wrong results and still look healthy.

### Impact

- semantic failures are caught earlier
- repair/self-heal can be triggered with more specific reasons
- better protection for aggregation-heavy and ranking-heavy queries

## 22. Strengthened Query_Spec Cleanup Heuristics

### What changed

`cleanup_query_spec` gained targeted semantic fixes, especially around analytical queries.

Examples:

- preserved identity outputs for ranking and entity-returning queries
- inferred missing `month` grouping for month-grain questions
- inferred missing profile dimensions such as `risk_tolerance`
- removed raw `date` from month-grain final outputs
- enabled bucket strategy metadata for band queries
- disabled null-group preservation for bucket queries
- avoided forcing averages where grouped totals were intended
- simplified cash-flow formulas to signed `SUM(amount)` when the dataset already stores sign
- preserved output schema and group-by consistency

### Why it was introduced

The Query_Spec is the semantic contract. If it is slightly wrong, downstream SQL or SPARQL can be executable but semantically incorrect.

### Impact

- better analytical query specifications
- fewer backend-generation ambiguities
- direct improvement path for comparative, ranking, and temporal queries

## 23. Added Result Normalization for Cross-Backend Comparability

### What changed

Normalization helpers were added for cases where backends represent the same semantics differently.

Examples:

- RDF IRI local-name normalization
- canonical set-operation keys across SQL and KG outputs
- bucket-label normalization
- reshaping some wide "missing-count" outputs into row form
- month-grain output cleanup

### Why it was introduced

SQL and KG do not naturally emit identical surface forms.

### Impact

- improved deterministic set operations
- better benchmark comparability
- fewer false mismatches caused only by representation differences

## 24. Strengthened Aggregation / Fanout Guards

### What changed

The pipeline added deterministic checks for aggregation shape, especially for fanout-sensitive analytical queries.

Key idea:

- when Query_Spec requires two-level aggregation, the generated query must stage aggregation before final grouping

### Why it was introduced

Flat joins across one-to-many tables silently inflate aggregates.

These are dangerous failures because the query executes and returns plausible numbers.

### Impact

- catches a class of high-cost semantic errors before results are accepted
- especially important for multi-table analytical queries

## 25. Preserved A/B2 Execution Reliability Improvements

### What changed

The pipeline retained the stronger execution behavior achieved in the earlier A/B work, especially around pre-scan/scan reliability.

### Why it mattered

Once execution reliability improved, the bottleneck moved from "can the query run?" to "did it answer correctly?"

### Impact

- pre-scan and scan success improved materially
- current bottleneck became semantic correctness rather than basic executability

## 26. Clarified Raw Pipeline vs Grader Responsibilities

### What changed

The repository now more clearly separates:

- raw pipeline execution reports
- separate grading/evaluation scripts

### Why it was introduced

These serve different purposes:

- raw report answers: did the system run and what did it produce?
- grader answers: how closely does the output match the benchmark?

### Impact

- easier to distinguish execution problems from grading problems
- easier to compare different graders or grading settings

## 27. Improved Grader Configurability

### What changed

The user workflow was updated to support grader model overrides such as:

- `LLM_GRADER_MODEL=gpt-5.6-terra`

### Why it was introduced

The grading stage itself can materially affect reported benchmark metrics.

### Impact

- easier A/B evaluation at the grader layer
- better separation between pipeline quality and grading-model behavior

## 28. Normalized Asset Layout Under `data/`

### What changed

Canonical assets now live under:

- `data/sql/`
- `data/kg/`
- `data/benchmarks/`

Root-level compatibility folders such as `kg/` and `dataset/` were removed after callers were updated.

### Why it was introduced

This made the repository more understandable and reduced duplicate entry points to the same assets.

### Impact

- fewer ambiguous asset locations
- easier onboarding for new contributors
- cleaner path resolution

## 29. Added Better Documentation for Current vs Legacy Code

### What changed

Documentation was added or expanded:

- `README.md`
- `structure.md`
- `docs/architecture.md`
- `docs/legacy.md`
- `docs/historical_models.md`
- this file

### Why it was introduced

The repository evolved substantially and needed architectural documentation, not just runnable code.

### Impact

- easier to understand active vs archival code
- easier to find canonical runners, assets, and tests
- lower onboarding cost

## 30. Current State

### Current canonical architecture

```text
user query
  -> decomposition
  -> subquery DAG planning
  -> per-node SQL/KG routing
  -> DAG execution with dependency binding
  -> deterministic set operators where needed
  -> result normalization / semantic contract checks
  -> final explanation
  -> raw report
  -> separate grading
```

### Current canonical source surfaces

- `src/script_diff_llm/pipeline/core_pipeline.py`
- `src/script_diff_llm/pipeline/decomposition.py`
- `src/script_diff_llm/pipeline/specification.py`
- `src/script_diff_llm/pipeline/kg_pipeline.py`
- `src/script_diff_llm/pipeline/explanation.py`
- `src/script_diff_llm/pipeline/semantic_contract.py`
- `src/script_diff_llm/pipeline/dag/planner.py`
- `src/script_diff_llm/pipeline/dag/executor.py`
- `src/script_diff_llm/pipeline/registry.py`
- `src/script_diff_llm/backends/sql.py`
- `src/script_diff_llm/backends/kg.py`
- `src/script_diff_llm/evaluation/benchmark_io.py`
- `src/script_diff_llm/evaluation/reporting.py`

## Summary of Overall Impact

### Major gains

- the system now reflects the actual research idea: subquery-level hybrid routing
- shared core logic is separated from model-specific experiments
- code ownership boundaries are clearer
- benchmark/reporting behavior is more reliable
- semantic correctness guards are stronger
- SQL/KG/hybrid outputs are more comparable

### Remaining limitations

- LLM outputs remain nondeterministic
- comparative and multi-step analytical correctness still need continued improvement
- grading can still change the reported picture substantially
- historical model trees still exist because they preserve experiment history and old runner compatibility

## Short Timeline View

1. Original monolithic baseline without explicit subquery decomposition.
2. Introduced decomposition, DAG planning, and per-subquery SQL/KG routing.
3. Standardized execution around real SQLite and Fuseki backends.
4. Extracted a canonical shared pipeline from model-specific copies.
5. Reorganized the repository into `src`, `configs`, `runners`, `data`, `tests`, `outputs`, and `historical_models`.
6. Split the monolithic pipeline into decomposition, Query_Spec, KG lifecycle, DAG, explanation, registry, and evaluation modules.
7. Removed legacy operators from the canonical registry while preserving historical compatibility.
8. Added semantic contract validation and stronger Query_Spec cleanup to improve post-execution correctness.
9. Continued A/B-style semantic and grading improvements without rewriting the core workflow.

