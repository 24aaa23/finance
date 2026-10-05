# script_diff_llm

For four-model raw-only ablations on the 1,000-query dataset, see [ablations/v5_test1000/README.md](ablations/v5_test1000/README.md).

Research/engineering repository for an agentic SQL/KG query pipeline over a wealth-management dataset.

For combined v5 run commands, optional database context, resume behavior, and changing datasets/databases, see [README_V5_RUN_GUIDE.md](README_V5_RUN_GUIDE.md).

The important architecture is subquery-level routing:

```text
Query -> Decompose -> Subquery DAG -> classify each subquery as SQL or KG
      -> execute independent nodes in parallel
      -> bind dependency outputs
      -> deterministic set operations
      -> final answer and explanation
```

The system does not classify the whole user query as SQL or KG. Hybrid queries are decomposed so different atomic subqueries can run against SQLite or Apache Jena Fuseki, then combine through deterministic operators such as `Set_Intersect`, `Set_Union`, and `Set_Difference`.

## Canonical Entry Path

The shared pipeline is now organized around three explicit surfaces:

- `configs/models/*.yaml`
  - provider/model endpoint settings
- `configs/experiments/*.yaml`
  - which model config, benchmark file, KG assets, SQL asset, and output directory to use
- `src/script_diff_llm/pipeline/core_pipeline.py`
  - canonical model-agnostic orchestration entry point

The preferred runner is:

```bash
python3 runners/train/run_pipeline.py configs/experiments/openai_gpt_oss_120b_all_train.yaml
```

You can also run by experiment name instead of full path:

```bash
python3 runners/experiments/run_experiment.py openai_gpt_oss_120b_all_train
python3 runners/experiments/run_experiment.py --list
```

The existing GPT-OSS named runner still works, but it is now just a thin wrapper around the shared pipeline.

## Layout

- `src/script_diff_llm/`: shared source for the current SQL/KG DAG pipeline.
- `src/script_diff_llm/backends/sql.py`: SQLite SQL generation, validation, execution, and normalization.
- `src/script_diff_llm/backends/kg.py`: KG metadata loading, Fuseki execution, and SPARQL term validation.
- `src/script_diff_llm/pipeline/core_pipeline.py`: canonical shared SQL/KG DAG orchestration.
- `src/script_diff_llm/pipeline/gpt_oss_pipeline.py`: legacy compatibility shim that re-exports the shared pipeline.
- `src/script_diff_llm/pipeline/operators.py`: deterministic set and math operators.
- `src/script_diff_llm/config/paths.py` and `src/script_diff_llm/config/runtime.py`: repo-relative path defaults and runtime configuration loading.
- `src/script_diff_llm/llm/clients.py`: Bedrock/OpenAI-compatible client construction.
- `runners/train/`: canonical runner entry points.
- `tests/unit/`, `tests/integration/`, `tests/regression/`: canonical automated tests.
- `data/benchmarks/`: canonical benchmark splits and metadata.
- `data/sql/`: canonical SQL asset manifests and schema notes for the shared pipeline.
- `data/kg/`: KG schema, graph TTL, summary, and RDF alias map.
- `base_templates/`: historical templates and compatibility wrappers.
- `historical_models/`: archived provider/model-specific experiment snapshots and outputs.
- `analysis/`: comparison/review artifacts and moved model smoke/manifests.
- `tools/apache-jena-fuseki-6.1.0/`: local Fuseki distribution.
- `outputs/`: new generated runtime outputs.
- `docs/architecture.md`: detailed architecture and operational notes.
- `docs/historical_models.md`: how the archived model snapshot directories are grouped and kept compatible.
- `docs/legacy.md`: what is still legacy/reference material versus canonical development surface.

## SQL and KG

SQL uses the physical SQLite schema in `wealth_management_diverse.db`. The expected tables are the real `ATOM_*` tables, including `ATOM_ENTITY_INVESTOR_PROFILE_001`, `ATOM_ENTITY_PORTFOLIO_HOLDING_001`, and `ATOM_EVENT_CASH_FLOW_001`. SQL code refers to this as `sql_schema`.

The canonical SQL asset manifest lives at:

```text
data/sql/wealth_management_diverse/asset.yaml
```

This gives new developers a visible SQL home analogous to `kg/`, even though the physical `.db` file still remains in the historical GPT-OSS experiment directory for compatibility.

KG execution uses Apache Jena Fuseki at `http://127.0.0.1:3030/wealth/query`. KG code uses ontology/class/property metadata from `data/kg/wealth_management_diverse_schema.ttl` and Fuseki metadata queries. KG code refers to this as `kg_metadata`.

The canonical benchmark and KG asset locations are now:

```text
data/benchmarks/
data/kg/
```

## Run

Preferred shared runner:

```bash
TEST_QUERY_LIMIT=1 python3 runners/train/run_pipeline.py configs/experiments/openai_gpt_oss_120b_all_train.yaml
```

Convenience wrapper for the current GPT-OSS experiment:

```bash
TEST_QUERY_LIMIT=1 python3 runners/train/openai_gpt_oss_120b_all_train.py
```

Legacy compatibility runner:

```bash
TEST_QUERY_LIMIT=1 python3 historical_models/openai.gpt-oss-120b-aman/all/train/run_pipeline_openai_gpt_oss_120b_all_train.py
```

Use `TEST_QUERY_LIMIT=3` and `TEST_QUERY_LIMIT=10` for larger smoke windows.

## Configuration

Configuration is now split into:

- model YAML:
  - `configs/models/openai_gpt_oss_120b.yaml`
- experiment YAML:
  - `configs/experiments/openai_gpt_oss_120b_all_train.yaml`
- SQL asset YAML:
  - `data/sql/wealth_management_diverse/asset.yaml`

Common environment variables still override YAML defaults:

- `SQLITE_DB_PATH`: SQLite DB path. Defaults to `historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db`.
- `FUSEKI_ENDPOINT`: defaults to `http://127.0.0.1:3030/wealth/query`.
- `SCHEMA_FILE`: defaults to `data/kg/wealth_management_diverse_schema.ttl`.
- `INSTANCE_FILE`: defaults to `data/kg/wealth_management_diverse_kg.ttl`.
- `INPUT_SAMPLE_FILE`: defaults to `data/benchmarks/verification_results_v2_sql_correct_train_300.xlsx`.
- `PIPELINE_OUTPUT_DIR`: defaults to `outputs/openai.gpt-oss-120b-aman/all/train`.
- `EXPERIMENT_CONFIG`: choose a different experiment YAML without editing code.
- `TEST_QUERY_LIMIT`, `TEST_QUERY_OFFSET`, `TEST_MAX_WORKERS`: benchmark window controls.

Model credentials are read from local `.env` files when present. Do not commit secrets.

## Verification

```bash
python3 -m compileall src runners tests
python3 -c "import sys; sys.path.insert(0, 'src'); from script_diff_llm.pipeline import core_pipeline"
sqlite3 historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db ".tables"
PYTHONPATH=src python3 -m unittest tests.unit.test_paths tests.integration.test_sqlite_backend tests.regression.test_subquery_dag -v
```

Full validation requires Fuseki and model API access, then the 1/3/10-query runs above.
