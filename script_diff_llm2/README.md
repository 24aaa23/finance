# SQL/KG hybrid query pipeline

The main pipeline decomposes a question into a subquery DAG, routes each subquery to SQL or an RDF graph, executes dependencies, and combines results. SQL supports SQLite and DuckDB; KG execution uses Apache Jena Fuseki.

Start with [the folder map](docs/PROJECT_STRUCTURE.md), [run commands](docs/guides/v5_run_guide.md), or [your retained results](results/README.md).

## Where things live

| Folder | Purpose |
|---|---|
| `src/script_diff_llm/` | Shared pipeline, decomposition, contracts, SQL/KG backends and model clients |
| `runners/` | Main pipeline, benchmark preparation and grading entry points |
| `configs/` | Main experiment, model and SQL/KG asset configuration |
| `data/` | Question datasets, databases, RDF assets and domain context |
| `ablations/` | Provider/experiment launchers, source snapshots and retained run directories |
| `results/retained/` | Links to the selected raw/graded reports, grouped by G ID |
| `docs/` | Methodology, prompts, architecture, run guides and prior analyses |
| `tests/` | Unit, backend integration and DAG regression checks |
| `analysis/` | Audits, inventories, cleanup records and organization manifest |
| `archive/` | Unretained run metadata/logs and old launcher logs |
| `runtime/` | Local Fuseki state; not pipeline source code |
| `outputs/` | Generated output and legacy grader logs |
| `historical_models/`, `base_templates/` | Older implementation snapshots and compatibility material |
| `tools/` | Local Fuseki distribution |

## Retained experiments

Your selected IDs are **G01, G09, G10, G11, G14, G15 and G16**. They comprise **7 graded files and 6 unique raw files**; G10 and G11 share their raw report. See [results/README.md](results/README.md) for direct links and match accuracy.

The original run paths remain the source of these files. The `results/retained/Gxx/raw.csv` and `graded.csv` entries are symlinks, so there are no extra copies of large reports. Earlier CSV inventories describe the state before cleanup; they are historical records, not a list of currently available reports.

## Datasets and context

- **WM-Investor / WMI:** [1,000-question workbook](data/benchmarks/wmi/questions_1000.xlsx), [605 development questions](data/benchmarks/wmi/questions_development_605.csv), [full reference overrides](data/benchmarks/wmi/full_answers_216.json), [SQL asset](data/sql/wealth_management_diverse/asset.yaml), and RDF assets in `data/kg/`.
- **WM-Firm / NeoWealth:** [question workbook](data/benchmarks/neowealth/questions.xlsx), [prepared evaluation CSV](data/benchmarks/neowealth_test.csv), DuckDB at `data/sql/neowealth/neowealth.duckdb`, and RDF assets in `data/kg/neowealth/`.
- **Domain context:** `data/context/wmi/` and `data/context/neowealth/`; Neowealth primitive YAMLs live in `data/context/neowealth/primitives/`.

Older root asset names remain compatibility symlinks. Context documents retain their original physical paths, with links under `data/context/`, to preserve hash-bound cache identities. This keeps existing launchers and manifests working without changing model prompts or the pipeline workflow. See [data/README.md](data/README.md).

## Run and grade

Use the existing experiment-specific launchers; moving data did not change their arguments:

```bash
# List the main configured experiments; no model inference.
/usr/bin/python3 -B runners/experiments/run_experiment.py --list

# Inspect a main hybrid model/context configuration; no model inference.
/usr/bin/python3 -B ablations/v5_test1000/run_raw.py deepseek_v3_2 without_context --dry-run
```

For execution commands and resume behavior, use:

- [Main v5 run guide](docs/guides/v5_run_guide.md)
- [Reliability v6 guide](docs/guides/reliability_v6.md)
- [Main model/context ablations](ablations/v5_test1000/README.md)
- [Improvement 10 experiments](ablations/improvement10_models/README.md)
- [NeoWealth experiments](ablations/neowealth_hybrid/README.md)

Grader 2 remains in `grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py`; its GPT-5 mini runner is `runners/grade_gpt_5_mini.py`. Grader 3 remains `grader_3.py`. Their code and scoring were not changed by organization.

## Credentials

Keep keys in local environment files, such as `ablations/gemini_3_8_flash/gemini.env` or `ablations/azure_gpt_oss_120b/azure.env`. Existing credential files were left in place and unchanged. Never commit keys. `.env.example` is the public template.

## Local verification

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src /usr/bin/python3 -B -m pytest -q tests
```

Most checks are offline. Real model execution requires valid credentials and the correct Fuseki dataset. Cleanup/organization details are recorded in [the organization manifest](analysis/organization_20261016/organization_manifest.json).
