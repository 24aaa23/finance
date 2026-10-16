# Data assets

| Dataset | Questions | SQL | KG | Domain context |
|---|---|---|---|---|
| WMI | `benchmarks/wmi/questions_1000.xlsx`, `questions_development_605.csv`, `full_answers_216.json` | `sql/wealth_management_diverse/asset.yaml`; database stays in its historical source directory | Wealth-management schema/instance TTL and alias map in `kg/` | `context/wmi/domain_intro.prompt`, `phase0_business_rules.md` |
| NeoWealth / WMF | `benchmarks/neowealth/questions.xlsx`; prepared `benchmarks/neowealth_test.csv` | `sql/neowealth/neowealth.duckdb`, `asset.yaml` | `kg/neowealth/` | `context/neowealth/domain_and_business_rules.md`, `primitives/*.yaml` |

Reference answers are evaluation data. Moving them under `data/` does not add them to model prompts. The pipeline's existing loading and context policies remain unchanged.

Older root asset paths remain relative symlinks for compatibility. The duplicate NeoWealth workbook `(1)` was verified byte-identical and replaced by a link to the same canonical workbook. Existing Neowealth launchers continue to use their original paths through these links.

The original WMI/NeoWealth databases and graph contents were not modified. Main WMI Fuseki is normally `http://127.0.0.1:3030/wealth/query`; NeoWealth is `http://127.0.0.1:3031/neowealth/query`. Launching a pipeline requires the graph for the selected dataset.

Context documents retain their original physical root paths because context cache/approval identities include the resolved document path. Their organized entries under `data/context/` are links; content is unchanged.
