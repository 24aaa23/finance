# Main hybrid pipeline with Gemini 3.8 Flash

Fill `GEMINI_API_KEY` in `gemini.env`. The file is ignored by Git and restricted to its owner. Exported GEMINI variables take precedence over this file. The launcher then loads the project environment for other settings.

From `script_diff_llm2`, test one small billed request:

```bash
bash ablations/gemini_3_8_flash/run_raw.sh --check-connection
```

Run all 1,000 questions without business context:

```bash
bash ablations/gemini_3_8_flash/run_raw.sh without_context --run-tag run_01 --workers 4 --dag-workers 1
```

For business context, replace `without_context` with `with_context`. Context preparation uses the existing agent and per-model cache; existing quarantine and approval rules still apply. It must have active entries to start a required-context run.

SQL database, workbook, RDF schema, instance TTL and alias map are the same sources as the main v5 ablation launcher. Experiment YAMLs explicitly name the SQL asset and KG paths. The launcher prints resolved input paths at startup. Fuseki must serve the main KG at `http://127.0.0.1:3030/wealth/query`; override with `--fuseki-endpoint` if needed.

Each of four query workers processes one question at a time. `--dag-workers 1` executes operators within each question sequentially. The current decomposition retry logic and all other main pipeline stages remain unchanged; all model stages use Gemini. No grader starts.

Outputs: `runs/gemini_3_8_flash/<condition>/run_01/raw_pipeline.csv`, `pipeline.log`, and `run_manifest.json`. Repeat the same command to resume saved rows. A new run tag starts a fresh experiment; changed configurations cannot be mixed with existing results. Use `--dry-run` to inspect paths without inference. Saved error rows follow the existing main runner's resume policy.

Google API documentation: https://ai.google.dev/gemini-api/docs/openai
