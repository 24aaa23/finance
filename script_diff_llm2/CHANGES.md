# Repository Restructuring Change Log

This file records the current repository-level restructuring, not older model-specific intermediate experiments.

## Current repository state

The repository is now organized around a canonical shared pipeline plus archived historical experiment trees.

### Canonical surfaces

- `src/script_diff_llm/`
- `configs/models/`
- `configs/experiments/`
- `runners/`
- `data/sql/`
- `data/kg/`
- `data/benchmarks/`
- `tests/`
- `outputs/`

### Legacy/reference surfaces

- `historical_models/`
- `base_templates/`

## Major structural changes completed

### 1. Shared canonical pipeline extracted

The active pipeline is no longer centered on a single model-specific directory.

- canonical entrypoint:
  - `src/script_diff_llm/pipeline/core_pipeline.py`
- compatibility shim:
  - `src/script_diff_llm/pipeline/gpt_oss_pipeline.py`

The shared orchestration now serves model configuration through YAML rather than by copying pipeline implementations per model directory.

### 2. Pipeline responsibilities split into modules

The previous monolithic pipeline surface was separated into coherent modules:

- `src/script_diff_llm/pipeline/decomposition.py`
- `src/script_diff_llm/pipeline/specification.py`
- `src/script_diff_llm/pipeline/kg_pipeline.py`
- `src/script_diff_llm/pipeline/explanation.py`
- `src/script_diff_llm/pipeline/registry.py`
- `src/script_diff_llm/pipeline/dag/planner.py`
- `src/script_diff_llm/pipeline/dag/executor.py`
- `src/script_diff_llm/evaluation/benchmark_io.py`
- `src/script_diff_llm/evaluation/reporting.py`

### 3. Canonical config layer added

Model and experiment wiring is now explicit:

- `configs/models/*.yaml`
- `configs/experiments/*.yaml`
- `src/script_diff_llm/config/runtime.py`
- `src/script_diff_llm/config/paths.py`
- `src/script_diff_llm/config/experiments.py`

### 4. Canonical data layout established

Canonical asset locations now are:

- SQL manifests:
  - `data/sql/`
- KG assets:
  - `data/kg/`
- benchmark assets:
  - `data/benchmarks/`

The root-level `kg/` and `dataset/` compatibility links were removed after the codebase and archived runners were updated to use canonical `data/...` locations.

### 5. Historical model trees grouped

Old provider/model experiment trees were moved under:

- `historical_models/`

This removed root clutter and made the shared architecture visible immediately.

### 6. Root clutter reduced

Removed or consolidated:

- root-level historical model aliases
- root-level duplicate `run/` tree
- root-level temporary compatibility links for `kg/` and `dataset/`
- cache directories and editor lockfiles

Moved/generated artifacts were grouped into:

- `analysis/output/`
- `outputs/`
- `docs/research/`

### 7. Archived runner asset paths normalized

Archived `run_pipeline_*.py` runners in `historical_models/` were updated to default to:

- `data/kg/...`
- `data/benchmarks/...`

This removed dependence on deleted root compatibility directories.

### 8. Base template asset defaults normalized

`base_templates/` default paths were updated to canonical asset locations under `data/`.

## Canonical runtime commands

Preferred runner:

```bash
python3 runners/train/run_pipeline.py configs/experiments/openai_gpt_oss_120b_all_train.yaml
```

Experiment-name runner:

```bash
python3 runners/experiments/run_experiment.py --list
python3 runners/experiments/run_experiment.py openai_gpt_oss_120b_all_train
```

Legacy compatibility runner:

```bash
python3 historical_models/openai.gpt-oss-120b-aman/all/train/run_pipeline_openai_gpt_oss_120b_all_train.py
```

## Verification status

Current repeated verification checks have passed:

- `python3 -m compileall src runners tests base_templates historical_models docs`
- `PYTHONPATH=src python3 -m unittest tests.unit.test_paths tests.integration.test_sqlite_backend tests.regression.test_subquery_dag -v`

The canonical automated suite currently passes:

- `23/23` tests

End-to-end pipeline runtime remains dependent on external Fuseki availability at:

- `http://127.0.0.1:3030/wealth/query`

## Notes

- SQL still uses the physical SQLite `ATOM_*` tables.
- KG still uses Fuseki as the actual execution backend.
- Subquery-level SQL/KG routing, DAG execution, cross-backend dependencies, and deterministic set operations remain intact.
- `historical_models/` is retained for experiment history and legacy runner compatibility, but it is not the primary development surface.
