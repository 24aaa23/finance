# Experiment launchers

| Folder | Experiment |
|---|---|
| `v5_test1000/` | Main hybrid pipeline, model/context ablations on WMI's 1,000 questions |
| `improvement10_models/` | SQL-only Improvement 10 snapshots with model/provider adapters |
| `improvement11_gpt_oss_120b/` | KG-only Improvement 11 snapshot and continuation adapters |
| `hybrid_sql_only/` | SQL-only ablation of the main hybrid pipeline |
| `improvement10_11_hybrid/` | Hybrid derivative joining the Improvement 10/11 execution approach |
| `neowealth_hybrid/` | Main hybrid on NeoWealth DuckDB/RDF and adaptive context retries |
| `gemini_3_8_flash/` | Gemini provider configuration, key file and WMI launcher |
| `azure_gpt_oss_120b/` | Azure provider configuration, key file and launcher |
| `openai_gpt_6_1_sol/` | OpenAI provider experiment launcher |

Only selected-result run folders remain in their original `runs/` locations. Other runs' remaining logs/input snapshots were moved to `archive/experiments/`; their report CSVs were already deleted. No launcher or native source snapshot was changed by this organization.

See [retained results](../results/README.md), [the main execution guide](../docs/guides/v5_run_guide.md), and the README inside each experiment folder. Do not launch archived checkpoints expecting deleted report files to exist.
