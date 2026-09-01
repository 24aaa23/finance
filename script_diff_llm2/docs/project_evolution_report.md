# Project Evolution Report

This is a condensed report version of the project evolution document. It focuses on what changed from the original baseline, why each change was made, what impact it had, and which files or folders carry that change today.

## 1. Original Baseline

### Before

- The repository was organized primarily around model-specific experiment folders.
- The pipeline logic lived in large monolithic scripts.
- Query handling was effectively one end-to-end flow, without explicit subquery DAG decomposition as the core architecture.
- SQL/KG boundaries were less explicit at the repository-architecture level.

### Change

- The repository was reorganized around one canonical shared pipeline.

### Why

- The original shape was workable for experiments, but hard to maintain, test, or extend for hybrid reasoning.

### Impact

- The active architecture is now visible and maintainable.
- Historical experiments remain available without defining the current code path.

### Files / folders involved

- `src/`
- `runners/`
- `configs/`
- `data/`
- `historical_models/`
- `base_templates/`

## 2. Introduced Subquery Decomposition

### Before

- A user query was not treated as a structured graph of dependent subproblems.

### Change

- Added semantic decomposition:

```text
query -> subqueries -> dependencies
```

### Why

- Many benchmark questions are multi-step and cannot be handled cleanly as one flat backend call.

### Impact

- The system can now represent mixed, dependent reasoning steps explicitly.
- Independent steps can run in parallel.

### Files / folders involved

- `src/script_diff_llm/pipeline/decomposition.py`
- `src/script_diff_llm/pipeline/dag/planner.py`

## 3. Introduced the Subquery DAG

### Before

- Dependencies between subproblems were implicit or buried inside one large execution flow.

### Change

- Built an explicit DAG layer with node dependencies and execution levels.

### Why

- Multi-step questions need dependency tracking, topological ordering, and reproducible execution.

### Impact

- The execution order is auditable.
- Cross-node data propagation is now explicit.

### Files / folders involved

- `src/script_diff_llm/pipeline/dag/planner.py`
- `src/script_diff_llm/pipeline/dag/executor.py`

## 4. Moved SQL/KG Routing to the Subquery Level

### Before

- Backend selection was not the defining architectural contract.

### Change

- Each subquery is now routed independently to SQL, KG, or a deterministic operator.

### Why

- Hybrid questions require different substrates for different pieces of the same user query.

### Impact

- The system supports:
  - SQL-only subqueries
  - KG-only subqueries
  - hybrid SQL/KG DAGs
  - deterministic merge steps

### Files / folders involved

- `src/script_diff_llm/pipeline/dag/planner.py`
- `src/script_diff_llm/pipeline/dag/executor.py`
- `src/script_diff_llm/pipeline/operators.py`

## 5. Preserved Deterministic Set Operations

### Before

- Set-style logic could easily be buried inside prompt behavior.

### Change

- `Set_Intersect`, `Set_Union`, and `Set_Difference` are explicit deterministic operators.

### Why

- These are execution semantics, not LLM reasoning tasks.

### Impact

- Better reproducibility.
- Lower semantic drift for merge steps.

### Files / folders involved

- `src/script_diff_llm/pipeline/operators.py`
- `src/script_diff_llm/pipeline/dag/executor.py`

## 6. Standardized the Real SQL Backend

### Before

- There was risk of drifting toward semantic table names instead of the actual database schema.

### Change

- The canonical SQL path stayed grounded in the real physical SQLite `ATOM_*` tables.

### Why

- Prompt cleanliness is less important than execution correctness.

### Impact

- Prevented invalid SQL assumptions.
- Preserved compatibility with the actual benchmark DB.

### Files / folders involved

- `src/script_diff_llm/backends/sql.py`
- `data/sql/wealth_management_diverse/asset.yaml`
- `historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db`

## 7. Standardized the Real KG Backend

### Before

- Legacy RDF helper paths existed and could be confused with the active execution backend.

### Change

- Apache Jena Fuseki became the canonical KG execution backend.

### Why

- The benchmarked KG path should run against a real SPARQL service.

### Impact

- More realistic KG execution behavior.
- Cleaner separation between metadata helpers and actual graph execution.

### Files / folders involved

- `src/script_diff_llm/backends/kg.py`
- `src/script_diff_llm/pipeline/kg_pipeline.py`
- `tools/apache-jena-fuseki-6.1.0/`
- `data/kg/`

## 8. Extracted a Canonical Shared Pipeline

### Before

- The active implementation was entangled with model-specific directories.

### Change

- Created one shared canonical runtime under `src/script_diff_llm/`.

### Why

- Shared logic should be implemented once, not copied across model trees.

### Impact

- New work now lands in the canonical codebase.
- Historical model trees remain archival.

### Files / folders involved

- `src/script_diff_llm/pipeline/core_pipeline.py`
- `src/script_diff_llm/pipeline/gpt_oss_pipeline.py`

## 9. Added Config-Driven Model and Experiment Wiring

### Before

- Model endpoints, IDs, and experiment paths were too embedded in scripts.

### Change

- Moved runtime wiring into YAML configs.

### Why

- Model selection should be a configuration problem, not a code-copy problem.

### Impact

- Easier to switch models by changing config.
- Cleaner separation of logic vs environment.

### Files / folders involved

- `configs/models/*.yaml`
- `configs/experiments/*.yaml`
- `src/script_diff_llm/config/runtime.py`
- `src/script_diff_llm/config/experiments.py`
- `src/script_diff_llm/config/paths.py`

## 10. Reorganized the Repository Layout

### Before

- The root contained many model-specific experiment trees and mixed responsibilities.

### Change

- Reorganized around:
  - `src/`
  - `runners/`
  - `configs/`
  - `data/`
  - `tests/`
  - `outputs/`
  - `historical_models/`

### Why

- A new developer should be able to locate the active pipeline immediately.

### Impact

- The canonical architecture is now legible from the root.

### Files / folders involved

- repository root layout
- `historical_models/`
- `data/sql/`
- `data/kg/`
- `data/benchmarks/`

## 11. Grouped Historical Experiment Trees

### Before

- Historical model folders cluttered the repository root.

### Change

- Moved old model/provider experiment directories under `historical_models/`.

### Why

- They are still useful, but they should not obscure the active path.

### Impact

- Root clutter dropped.
- The current code path became much clearer.

### Files / folders involved

- `historical_models/`
- `docs/historical_models.md`

## 12. Normalized Asset Paths

### Before

- Paths were more brittle and more closely tied to older folder layouts.

### Change

- Standardized canonical asset locations under `data/`.

### Why

- Path correctness should survive restructuring.

### Impact

- Fewer machine-specific or layout-specific breakages.

### Files / folders involved

- `data/sql/`
- `data/kg/`
- `data/benchmarks/`
- `src/script_diff_llm/config/paths.py`

## 13. Separated Benchmark I/O and Reporting

### Before

- Benchmark loading, resume logic, and report persistence were mixed into the main pipeline file.

### Change

- Extracted evaluation/reporting concerns into dedicated modules.

### Why

- Benchmark I/O is not core reasoning logic.

### Impact

- Cleaner orchestrator.
- Resume behavior remained intact while becoming easier to maintain.

### Files / folders involved

- `src/script_diff_llm/evaluation/benchmark_io.py`
- `src/script_diff_llm/evaluation/reporting.py`

## 14. Separated Operator Registry Construction

### Before

- Operator registration and dependency injection lived inside the orchestration surface.

### Change

- Extracted registry building into its own module.

### Why

- "What operators exist and how they are wired" is a separate concern from pipeline orchestration.

### Impact

- Cleaner dependency injection.
- Easier to audit active operator surfaces.

### Files / folders involved

- `src/script_diff_llm/pipeline/registry.py`

## 15. Separated Decomposition From Planning

### Before

- Decomposition logic and DAG logic were too close together.

### Change

- Moved semantic decomposition into its own module.

### Why

- These are different questions:
  - decomposition: what subqueries exist?
  - planning: how are they connected?

### Impact

- Better conceptual separation.
- Easier decomposition-specific testing and future tuning.

### Files / folders involved

- `src/script_diff_llm/pipeline/decomposition.py`
- `src/script_diff_llm/pipeline/dag/planner.py`

## 16. Separated Query_Spec as the Semantic Contract

### Before

- Query semantic specification was embedded in the larger orchestration flow.

### Change

- Extracted Query_Spec generation and cleanup into one dedicated module.

### Why

- Query_Spec is the IR between NL intent and backend query generation.

### Impact

- Downstream SQL/SPARQL generation now has a clearer contract.
- Semantic cleanup now has a proper home.

### Files / folders involved

- `src/script_diff_llm/pipeline/specification.py`

## 17. Grouped the KG Lifecycle Into One Module

### Before

- KG stages were present but not cleanly grouped by lifecycle responsibility.

### Change

- Extracted the coherent KG path:

```text
Retrieve -> Generate -> Refine -> Pre_Scan_Validate -> Scan
```

### Why

- These functions share dependencies, repair behavior, and backend-specific semantics.

### Impact

- KG work is now isolated from unrelated orchestration code.

### Files / folders involved

- `src/script_diff_llm/pipeline/kg_pipeline.py`

## 18. Separated Final Answer / Explanation

### Before

- Final explanation and output shaping were buried in the main pipeline.

### Change

- Extracted explanation and final answer formatting into a dedicated cross-backend module.

### Why

- Final answer shaping should not be tied to SQL or KG implementation details.

### Impact

- SQL, KG, and hybrid outputs now share one finalization stage.

### Files / folders involved

- `src/script_diff_llm/pipeline/explanation.py`

## 19. Cleaned the Canonical Registry Surface

### Before

- Legacy operators still appeared in the canonical operator surface.

### Change

- Removed `Validate`, `Classify`, and `Check_Schema` from the canonical registry while preserving old compatibility paths.

### Why

- Read-only auditing showed they were not part of the active canonical DAG execution path.

### Impact

- The canonical architecture now reflects what actually runs.

### Files / folders involved

- `src/script_diff_llm/pipeline/registry.py`
- legacy compatibility code in historical surfaces

## 20. Added Semantic Contract Validation

### Before

- Successful execution could still produce semantically wrong output shapes.

### Change

- Added deterministic post-execution semantic checks.

### Why

- "Executed successfully" and "answered correctly" are different.

### Impact

- The pipeline can now reject structurally wrong results even after a successful SQL or SPARQL execution.

### Files / folders involved

- `src/script_diff_llm/pipeline/semantic_contract.py`
- `src/script_diff_llm/pipeline/dag/executor.py`

## 21. Strengthened Query_Spec Cleanup

### Before

- Query_Specs were more likely to be executable but semantically underspecified or slightly wrong.

### Change

- Added targeted cleanup heuristics around:
  - group-by inference
  - month-grain handling
  - identity preservation
  - bucket queries
  - aggregation semantics
  - signed cash-flow handling

### Why

- Small semantic defects in Query_Spec create large downstream answer errors.

### Impact

- Better backend query generation.
- Better output shape consistency.

### Files / folders involved

- `src/script_diff_llm/pipeline/specification.py`

## 22. Added Cross-Backend Result Normalization

### Before

- SQL and KG could express equivalent results in different surface forms.

### Change

- Added normalization for:
  - RDF IRI local names
  - canonical set-operation keys
  - bucket labels
  - month-grain cleanup
  - reshaped structured outputs

### Why

- Some mismatches were representational rather than semantic.

### Impact

- Better comparability across SQL, KG, and hybrid outputs.

### Files / folders involved

- `src/script_diff_llm/pipeline/semantic_contract.py`

## 23. Added Aggregation/Fanout Guards

### Before

- Flat joins could silently inflate aggregates while still executing successfully.

### Change

- Added deterministic checks for staged aggregation when Query_Spec requires it.

### Why

- Many-to-many and one-to-many joins can corrupt analytical queries without obvious runtime failure.

### Impact

- Better protection for comparative, ranking, and aggregation-heavy questions.

### Files / folders involved

- `src/script_diff_llm/pipeline/semantic_contract.py`
- `src/script_diff_llm/backends/sql.py`
- `src/script_diff_llm/pipeline/kg_pipeline.py`

## 24. Strengthened Test and Regression Coverage

### Before

- Compile success alone could be mistaken for correctness.

### Change

- Added or strengthened unit, integration, and regression tests around active architecture surfaces.

### Why

- Structural refactors need behavioral protection.

### Impact

- Multiple large refactors were completed without breaking the canonical path.

### Files / folders involved

- `tests/unit/`
- `tests/integration/`
- `tests/regression/`

## 25. Clarified Raw Pipeline vs Grader Responsibilities

### Before

- It was easier to conflate pipeline quality with grader behavior.

### Change

- Kept pipeline execution and grading as separate stages with separate artifacts.

### Why

- A raw report shows what the pipeline produced; a graded report shows how it was judged.

### Impact

- Easier debugging of execution issues vs evaluation issues.

### Files / folders involved

- `outputs/.../raw_pipeline_*.csv`
- `outputs/.../graded_*.csv`
- `historical_models/.../grade_*.py`

## 26. Enabled More Controlled Benchmarking and Resume

### Before

- Long benchmark runs were more brittle.

### Change

- Preserved and clarified resume behavior and incremental report writing.

### Why

- Large runs like the 442-query benchmark should survive interruption.

### Impact

- More practical experimentation on long runs.

### Files / folders involved

- `src/script_diff_llm/evaluation/reporting.py`
- `src/script_diff_llm/evaluation/benchmark_io.py`

## 27. Current State

### Before

- The project started as a monolithic, experiment-heavy codebase with less explicit hybrid-query structure.

### Change

- It is now a shared, config-driven, decomposed SQL/KG DAG pipeline with clearer module ownership.

### Why

- To preserve the research idea while making the system maintainable, testable, and extensible.

### Impact

- The current architecture is much easier to reason about and improve systematically.

### Files / folders involved

- `src/script_diff_llm/`
- `runners/`
- `configs/`
- `data/`
- `tests/`
- `outputs/`
- `historical_models/`

## Bottom-Line Impact

### Biggest architectural impacts

1. The system now matches the intended research design: subquery-level hybrid routing.
2. Core pipeline logic is separated from model-specific experiment history.
3. Query_Spec is now visible as the semantic contract.
4. KG execution is grouped into a coherent backend lifecycle.
5. Post-execution semantic validation now catches wrong-but-executable answers.
6. The repository is significantly easier for a new developer to navigate.

### Biggest practical impacts

1. Hybrid SQL/KG DAG execution is explicit and testable.
2. Long benchmark runs are easier to manage and resume.
3. Semantic correctness issues can now be attacked stage by stage instead of treating every miss as a generic failure.
4. Model switching is increasingly configuration-driven rather than copy-paste-driven.

