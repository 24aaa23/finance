**Top level**

- `src/script_diff_llm/`
  - Canonical shared code.
  - This is the active implementation used by `runners/train/run_pipeline.py`.
  - It contains config loading, backend adapters, pipeline logic, DAG planner/executor, evaluation/reporting, and LLM client construction.

- `runners/`
  - Thin entry points.
  - Current canonical runner: [runners/train/run_pipeline.py](/home/kritik/Desktop/neosapiens/script_diff_llm/runners/train/run_pipeline.py)
  - Convenience wrapper for the current experiment: [runners/train/openai_gpt_oss_120b_all_train.py](/home/kritik/Desktop/neosapiens/script_diff_llm/runners/train/openai_gpt_oss_120b_all_train.py)
  - Output: invokes `script_diff_llm.pipeline.core_pipeline.main()`.

- `tests/`
  - Active canonical test suite.
  - `unit/`: config/path and registry-surface checks.
  - `integration/`: SQLite backend checks.
  - `regression/`: DAG behavior checks with stubs.

- `configs/`
  - Canonical YAML configuration.
  - `models/`: model/provider config.
  - `experiments/`: benchmark, KG, SQL asset, and output selection.

- `data/sql/`
  - Canonical SQL asset manifests and schema notes.
  - This is the visible SQL-side home analogous to `kg/`.
  - The physical `.db` file still remains in the historical GPT-OSS experiment directory for compatibility.

- `data/kg/`
  - Canonical KG assets.
  - Contains the KG schema, instance TTL, alias map, and KG summary.

- `data/benchmarks/`
  - Canonical benchmark input files.
  - Replaces `dataset/` as the canonical benchmark asset location.

- `outputs/`
  - Canonical generated reports/logs.
  - The active pipeline writes CSV reports here by default.

- `base_templates/`
  - Historical base implementations and templates.
  - Not part of the canonical runtime path.

- `historical_models/`
  - Archived per-model experiment directories.
  - Contains the old provider/model-specific runner trees that predate the shared canonical pipeline.
  - These are not part of the active `src/` architecture.

- `docs/`, `analysis/`, `tools/`
  - Supporting material, outputs, local tooling, and the bundled Fuseki distribution.

**Canonical package: `src/script_diff_llm/`**

**1. `config/`**
- Files:
  - [src/script_diff_llm/config/paths.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/config/paths.py)
  - [src/script_diff_llm/config/runtime.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/config/runtime.py)
- Responsibility:
  - Resolve project-relative paths.
  - Load `.env`.
  - Load model YAML, experiment YAML, and SQL asset YAML.
  - Build a typed `RuntimeConfig`.
- Used by:
  - `core_pipeline.py` during startup.

**2. `llm/`**
- File:
  - [src/script_diff_llm/llm/clients.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/llm/clients.py)
- Responsibility:
  - Build OpenAI-compatible clients from model config.
  - Expose model capability helpers such as `supports_temperature`.
- Used by:
  - `core_pipeline.py`.

**3. `backends/`**
- Files:
  - [src/script_diff_llm/backends/sql.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/backends/sql.py)
  - [src/script_diff_llm/backends/kg.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/backends/kg.py)

`backends/sql.py`
- Responsibility:
  - SQL generation, validation, and SQLite execution for physical `ATOM_*` tables.
- Input:
  - query, `query_spec`, `sql_schema`, `bound_inputs`, DB path.
- Output:
  - generated SQL, validation result, scan rows.

`backends/kg.py`
- Responsibility:
  - KG metadata loading, Fuseki health/execution, and RDF term validation.
- Input:
  - KG TTL path, Fuseki endpoint, SPARQL query.
- Output:
  - `kg_metadata` and SPARQL execution results.

**4. `pipeline/`**

- [src/script_diff_llm/pipeline/core_pipeline.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/pipeline/core_pipeline.py)
  - Canonical shared orchestrator.
  - Inputs:
    - runtime config, clients, SQLite path, KG files, benchmark file, report file.
  - Outputs:
    - drives the end-to-end benchmark run and writes report rows.

- [src/script_diff_llm/pipeline/gpt_oss_pipeline.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/pipeline/gpt_oss_pipeline.py)
  - Legacy compatibility shim.
  - Re-exports from `core_pipeline.py` for older imports.

- [src/script_diff_llm/pipeline/decomposition.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/pipeline/decomposition.py)
  - `semantic_decompose`
  - Natural-language query -> decomposed subquery nodes.

- [src/script_diff_llm/pipeline/dag/planner.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/pipeline/dag/planner.py)
  - Converts decomposition output into a validated DAG.

- [src/script_diff_llm/pipeline/dag/executor.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/pipeline/dag/executor.py)
  - Executes DAG levels, binds dependencies, runs SQL/KG nodes, and performs set operations.

- [src/script_diff_llm/pipeline/specification.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/pipeline/specification.py)
  - `semantic_build_query_spec`
  - `cleanup_query_spec`
  - Produces the semantic contract used by SQL/KG generation.

- [src/script_diff_llm/pipeline/kg_pipeline.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/pipeline/kg_pipeline.py)
  - KG lifecycle:
    `Retrieve -> Generate SPARQL -> Refine -> Pre_Scan_Validate -> Scan`

- [src/script_diff_llm/pipeline/explanation.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/pipeline/explanation.py)
  - Final answer stage for SQL, KG, hybrid, and set-operation outputs.

- [src/script_diff_llm/pipeline/operators.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/pipeline/operators.py)
  - Deterministic math and set operators.

- [src/script_diff_llm/pipeline/registry.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/pipeline/registry.py)
  - Canonical operator wiring for the active pipeline.
  - Legacy `Validate`, `Classify`, and `Check_Schema` are no longer part of the canonical registry.

**5. `evaluation/`**
- Files:
  - [src/script_diff_llm/evaluation/benchmark_io.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/evaluation/benchmark_io.py)
  - [src/script_diff_llm/evaluation/reporting.py](/home/kritik/Desktop/neosapiens/script_diff_llm/src/script_diff_llm/evaluation/reporting.py)
- Responsibility:
  - benchmark loading
  - row normalization
  - report persistence
  - resume logic
  - per-record execution coordination
