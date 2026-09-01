# Legacy Surfaces

This repository now has a clear canonical surface and a separate legacy/reference surface.

## Canonical

Active development should start here:

- `src/script_diff_llm/`
- `configs/models/`
- `configs/experiments/`
- `runners/`
- `data/sql/`
- `data/kg/`
- `data/benchmarks/`
- `tests/`
- `outputs/`

These locations define the current shared SQL/KG DAG pipeline.

## Legacy

These locations are not the primary architecture:

- `historical_models/`
- `base_templates/`

### `historical_models/`

Contains older per-model experiment trees that predate the shared canonical pipeline.

What they are:

- archived experiment runners
- archived grading scripts
- archived raw outputs and reports
- compatibility entrypoints that still help compare older experiments

What they are not:

- the canonical implementation
- the best place to add new features
- the source of truth for current path/layout decisions

### `base_templates/`

Contains older template-style pipeline files and compatibility/reference implementations.

Use cases:

- compare current shared code against earlier monolithic implementations
- recover older prompt/operator behavior for research comparison
- inspect previous end-to-end pipeline structure

Do not treat `base_templates/` as the main runtime path for new work.

## Compatibility expectation

The project still preserves limited legacy usability:

- historical GPT-OSS wrapper paths still work
- archived model runners now point at canonical asset locations under `data/`

But compatibility is best-effort. The canonical contract is the shared pipeline under `src/` with config-driven runners under `runners/`.
