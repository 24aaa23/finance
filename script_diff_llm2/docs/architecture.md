# Architecture

`script_diff_llm` evaluates an agentic query-processing pipeline for a wealth-management dataset.

The current validated architecture routes at subquery level, not whole-query level:

```text
natural-language query
  -> semantic decomposition
  -> atomic subqueries
  -> subquery DAG
  -> SQL/KG classification per subquery
  -> backend execution
  -> dependency binding
  -> deterministic set operations
  -> final answer and explanation
```

Independent DAG nodes can run in parallel. Dependent nodes consume upstream outputs. `Set_Intersect`, `Set_Union`, and `Set_Difference` are deterministic operators, not LLM calls.

## Data Substrates

The SQL backend uses SQLite and the physical `ATOM_*` tables in `wealth_management_diverse.db`. SQL prompts and validators should refer to this as `sql_schema`.

The KG backend uses Apache Jena Fuseki at `http://127.0.0.1:3030/wealth/query`. KG prompts and validators should refer to ontology and graph metadata as `kg_metadata`.

Canonical asset locations are now:

- `data/sql/`
- `data/kg/`
- `data/benchmarks/`

Do not collapse these into one ambiguous schema abstraction. SQLite table/column names and KG class/property names are intentionally different.

## Repository Roles

- `src/script_diff_llm/`: shared source code for the current SQL/KG DAG pipeline.
- `src/script_diff_llm/backends/sql.py`: SQLite SQL generation, validation, execution, and result normalization.
- `src/script_diff_llm/backends/kg.py`: KG schema metadata loading, Fuseki execution, and term validation.
- `src/script_diff_llm/pipeline/core_pipeline.py`: canonical shared SQL/KG DAG orchestration entry point.
- `src/script_diff_llm/pipeline/gpt_oss_pipeline.py`: legacy compatibility shim that re-exports the shared pipeline.
- `src/script_diff_llm/pipeline/operators.py`: deterministic set and math operators.
- `src/script_diff_llm/config/paths.py`: repo-relative default path resolution.
- `src/script_diff_llm/config/runtime.py`: runtime configuration loading from model YAML, experiment YAML, SQL asset YAML, and environment overrides.
- `src/script_diff_llm/llm/clients.py`: model-client construction and model capability helpers.
- `runners/train/`: canonical runnable entry points for shared pipeline experiments.
- `configs/models/`: model/provider config such as model env, base URL env, and API key env names.
- `configs/experiments/`: experiment-level config such as benchmark file, KG files, SQL asset, and output directory.
- `data/sql/`: canonical SQL asset manifests and human-readable schema notes.
- `tests/unit/`, `tests/integration/`, `tests/regression/`: canonical automated tests.
- `data/benchmarks/`: benchmark question splits and split metadata.
- `data/kg/`: RDF/KG schema, instance TTL, KG summary, and RDF ID alias map.
- `historical_models/`: archived model-specific experiment snapshots, raw outputs, and grading outputs.
- `base_templates/`: historical templates plus compatibility wrappers that forward to canonical shared code or tests.
- `analysis/`: analysis outputs over benchmark/evaluation results, including moved model manifest/smoke artifacts.
- `tools/apache-jena-fuseki-6.1.0/`: local Fuseki distribution.
- `outputs/`: new generated pipeline logs and reports.
- `docs/historical_models.md`: notes on the archived historical model directories.
- `docs/legacy.md`: canonical-versus-legacy guidance for contributors.

## Canonical Runtime Path

The preferred shared runner is:

```bash
python3 runners/train/run_pipeline.py configs/experiments/openai_gpt_oss_120b_all_train.yaml
```

There is also a name-based experiment runner:

```bash
python3 runners/experiments/run_experiment.py --list
python3 runners/experiments/run_experiment.py deepseek_v3_2_all_train
```

That runner resolves:

1. experiment YAML
2. model YAML
3. SQL asset YAML
4. shared pipeline entrypoint at `src/script_diff_llm/pipeline/core_pipeline.py`

The historical GPT-OSS-named runner still works, but it is now only a convenience wrapper around this shared path.

## Current Compatibility

The legacy active command still works:

```bash
python3 historical_models/openai.gpt-oss-120b-aman/all/train/run_pipeline_openai_gpt_oss_120b_all_train.py
```

The GPT-OSS convenience wrapper also still works:

```bash
python3 runners/train/openai_gpt_oss_120b_all_train.py
```

Use `TEST_QUERY_LIMIT=1`, `TEST_QUERY_LIMIT=3`, or `TEST_QUERY_LIMIT=10` for limited runs.

## Configuration

The runtime is now layered:

- model config:
  - `configs/models/openai_gpt_oss_120b.yaml`
- experiment config:
  - `configs/experiments/openai_gpt_oss_120b_all_train.yaml`
- SQL asset manifest:
  - `data/sql/wealth_management_diverse/asset.yaml`

Important environment variables still override YAML:

- `SQLITE_DB_PATH`: SQLite database path. Defaults to the existing active DB at `historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db`.
- `FUSEKI_ENDPOINT`: Fuseki query endpoint. Defaults to `http://127.0.0.1:3030/wealth/query`.
- `SCHEMA_FILE`: KG schema TTL. Defaults to `data/kg/wealth_management_diverse_schema.ttl`.
- `INSTANCE_FILE`: KG instance TTL. Defaults to `data/kg/wealth_management_diverse_kg.ttl`; the active Scan backend is Fuseki.
- `INPUT_SAMPLE_FILE`: benchmark input file. Defaults to `data/benchmarks/verification_results_v2_sql_correct_train_300.xlsx`.
- `PIPELINE_OUTPUT_DIR`: generated report/log directory. Defaults to `outputs/openai.gpt-oss-120b-aman/all/train`.
- `EXPERIMENT_CONFIG`: alternate experiment YAML.
- `TEST_QUERY_LIMIT`, `TEST_QUERY_OFFSET`, `TEST_MAX_WORKERS`: benchmark window controls.

Model credentials are loaded from the active experiment `.env`, repo `.env`, or `env/.env` when present. Do not commit secrets.

## Fuseki

The pipeline expects the wealth graph to be available at `/wealth/query`. Start Fuseki with the repo KG TTL loaded into dataset `/wealth`, then verify:

```bash
curl -s http://127.0.0.1:3030/wealth/query
```

## Verification

Recommended checks after changes:

```bash
python3 -m compileall src runners tests
python3 -c "import sys; sys.path.insert(0, 'src'); from script_diff_llm.pipeline import core_pipeline"
sqlite3 historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db ".tables"
PYTHONPATH=src python3 -m unittest tests.unit.test_paths tests.integration.test_sqlite_backend tests.regression.test_subquery_dag -v
TEST_QUERY_LIMIT=1 python3 runners/train/run_pipeline.py configs/experiments/openai_gpt_oss_120b_all_train.yaml
TEST_QUERY_LIMIT=3 python3 runners/train/run_pipeline.py configs/experiments/openai_gpt_oss_120b_all_train.yaml
TEST_QUERY_LIMIT=10 python3 runners/train/run_pipeline.py configs/experiments/openai_gpt_oss_120b_all_train.yaml
```
