# Project structure

Use this map for the current project layout. Earlier structure documents and the old root README are preserved under `docs/history/`.

```text
script_diff_llm2/
├── README.md                         # Start here
├── src/script_diff_llm/              # Main pipeline implementation
│   ├── backends/                    # Read-only SQL and Fuseki access
│   ├── config/                      # Runtime configuration and path resolution
│   ├── evaluation/                  # Dataset loading, reports and grading support
│   ├── llm/                         # Model clients
│   └── pipeline/                    # QuerySpec, context, DAG planning/execution
├── runners/                         # Pipeline, preparation and grading commands
├── configs/                         # Experiment and model YAMLs
├── data/
│   ├── benchmarks/
│   │   ├── wmi/                     # 1,000-test/605-development question sources
│   │   └── neowealth/               # Original NeoWealth workbook
│   ├── context/
│   │   ├── wmi/                     # Domain intro and phase0 rules
│   │   └── neowealth/               # Combined domain/rules and primitive YAMLs
│   ├── kg/neowealth/                # NeoWealth RDF schema/instance/summary
│   └── sql/neowealth/               # Native DuckDB and SQL asset manifest
├── ablations/                       # Experiment-specific code and source snapshots
├── results/
│   └── retained/Gxx/                # raw.csv / graded.csv links for selected IDs
├── docs/
│   ├── guides/                      # Main execution guides
│   ├── history/                     # Previous root documentation
│   └── *.md                         # Architecture, methodology, prompts, analyses
├── analysis/                        # Audits, inventories and organization records
├── archive/
│   ├── experiments/                 # Unretained run metadata/logs/input snapshots
│   └── launcher_logs/               # Older supervisor logs
├── runtime/fuseki/                  # Local persistent Fuseki state
├── outputs/                         # Generated reports and legacy grader logs
├── tests/                           # Offline unit/integration/regression checks
├── historical_models/               # Historical implementations/source database
├── base_templates/                  # Historical templates
└── tools/                           # Fuseki software
```

The SQL source database for WMI remains at its existing historical location because configuration and tests depend on it. Main source code, model configurations, grader implementations, experiment source snapshots, selected reports and credential files remain unchanged.

Root filenames such as `neowealth.duckdb`, `wealth_management_1000_test_set_questions.xlsx`, `domain_intro.prompt`, `primitves_updated_final`, `kg_output_neowealth` and `run` are compatibility symlinks into the canonical directories. They occupy almost no space and preserve existing commands. Do not remove them until every dependent launcher/configuration has been deliberately migrated.

Unretained run folders were archived after their report CSVs had already been removed at the user's request. Archives contain remaining provenance, settings, input snapshots and logs; they are not complete runnable checkpoints. Original paths and archive destinations are recorded in `analysis/organization_20261016/organization_manifest.json`.

The retained results are described in [the results index](../results/README.md). Do not rerun the old pre-cleanup inventory scripts expecting the same G numbering; the historical index is retained to preserve those IDs.

The three domain/rules documents are an exception: physical files stay at their original root paths, and `data/context/` links to them, because preparation/approval identities include the resolved document path.
