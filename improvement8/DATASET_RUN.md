# Run the eight dataset categories

From the workspace root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File improvement8/start_dataset_terminals.ps1
```

The launcher checks all eight CSVs, prepares the shared knowledge cache once,
then opens eight visible PowerShell terminals. Each runs one question at a time
with `improvement8/.env` credentials and specialist consultation enabled. Domain
and Query Understanding consultation requests have no count cap;
operators request them only when needed. Repeated requests can keep adding model
calls, cost and time until a plan is returned, an error occurs, or you stop the run.

To test the saved 45-rule cache in a fresh output folder, run this from the
workspace root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File improvement8/start_dataset_terminals.ps1 -KnowledgeCache improvement8/.runtime/knowledge/35c023c8b885dacc9fec89756a317af7778f62a234b1b6932dd1ddc7f66896ae.json -OutputRoot improvement8/pipelien_output_sql/cache45_test
```

The selected cache is validated and reused with zero preparation model requests.
All eight child processes inherit the same selection. The question pipelines
still make their normal model requests. This command preserves the selected
cache's existing 45 rules, including the remaining limitations documented in
`pipelien_output_sql/_preparation/cache_review_45_rules.md`.

| CSV | Questions | Folder under `pipelien_output_sql/` |
|---|---:|---|
| ARC.csv | 58 | at_risk_critical |
| BSQ.csv | 38 | batch_status |
| EC.csv | 59 | enrichment_context |
| MC.csv | 76 | multi_step_comparative |
| RC.csv | 55 | reference_compliance |
| SQA.csv | 53 | scoring_quantitative |
| TT.csv | 37 | temporal_transaction |
| WM.csv | 66 | benchmark |

Counts describe the current dataset (442 total); the launcher recalculates them.
Each folder receives `raw_pipeline_v9.csv`, its debug CSV, corresponding JSONL
sidecars and `terminal.log`. Detailed pipeline logs and timing files are in
`.runtime/logs/`. Reports retain supplied ground truth for separate accuracy
grading; the pipeline itself does not grade answers.

For input validation without model calls or terminal launches, add `-ValidateOnly`.
To run/resume just one category, add `-Type ARC` (or another CSV code).
Completed compatible report rows are skipped on resume. Stop the previous run
before resuming that category; existing report locks prevent concurrent writers.
Changing code or input contents may require a fresh report under the pipeline's
existing run-identity checks. No reports are deleted by this launcher.
