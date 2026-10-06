# Improvement11 KG pipeline

This copy runs the whole dataset sequentially in one terminal. All default project
files are local to `improvemnt11kgfixed`. The fixed AOP stages and supplied domain
and business documents are unchanged. The runtime is `aop-improvement11-kg-v3`.

## Run from CMD

```cmd
cd /d "C:\Users\AMAN KUMAR SINGH\Desktop\financial\improvemnt11kgfixed"
powershell -NoProfile -ExecutionPolicy Bypass -File start_kg.ps1
run_dataset.cmd
```

The first command starts or verifies/reuses the project-local background Fuseki
server. The dataset command prepares a single manifest, compiles or reuses the
shared knowledge cache, and processes all 1000 questions one at a time. First-time
knowledge preparation can take several minutes. No additional terminals open.

The workbook contains eight categories, retained as metadata within one combined
input and one report. Full answers for 216 question IDs override the workbook's
answers. They remain local and are not sent to planning models.

Normal runs resume compatible saved reports. To retry saved execution errors:

```cmd
run_dataset.cmd --retry
```

Retries back up the report and retain successful rows. Input preparation refuses
to overwrite a changed saved question manifest. Code/data/knowledge changes can
also make normal resume incompatible; preserve old outputs before a fresh run.

To inspect server logs in a terminal, use `start_fuseki.cmd`. Ctrl+C closes the
log view while the managed background server continues running.

## Local files

- Code: `run_pipeline_v2_kg/`
- Credentials: `.env`
- Domain/rules: `domain_intro_latest.prompt`, `business_rules_addendum.md`
- Ontology: `kg_output_fixed/wealth_management_diverse_schema.ttl`
- Instance graph: `kg_output_fixed/wealth_management_diverse_kg.ttl`
- Questions: `datatset/wealth_management_1000_test_set_questions.xlsx`
- Full-answer overrides: `datatset/216_questions_full_results.json`
- Fuseki: `tools/apache-jena-fuseki-6.1.0/fuseki-server.jar`
- Caches, pipeline logs and internal dataset preparation: `.runtime/`
- Fuseki logs/config/PID: `.runtime/fuseki/`
- Combined input: `pipeline_output_kg_v11/input_questions.jsonl`
- Combined report: `pipeline_output_kg_v11/raw_pipeline_v9.csv`
- JSONL/debug/telemetry: alongside that report

The `datatset` spelling matches the supplied directory. The old report filename
is retained for compatibility with existing tools. Python 3.10+ and Java 21+
must be available in PATH. Dependencies are in `requirements.txt` in this package.

## Isolation

The endpoint is `http://127.0.0.1:3041/improvemnt11kgfixed/query`, separate from
improvement9. The server launcher loads this project's absolute KG path and
reuses only a matching read-only process. It never stops an unrelated server.
CLI defaults reset inherited credential/cache/output/sidecar/input paths from
older experiments. Explicit custom input/output/endpoint CLI options remain
available. Planning models receive declared metadata and supplied rules, not live
rows, statistics or ground-truth answers. No model-based result review is enabled.

## Checks without model calls

```cmd
run_dataset.cmd --check
python -u -B run_pipeline_v2_kg\run.py --env-file .env --check-kg
```

Tests against the local server:

```cmd
set KG_TEST_ENDPOINT=http://127.0.0.1:3041/improvemnt11kgfixed/query
python -B -m unittest discover -s run_pipeline_v2_kg\tests -p "test_*.py"
```

`prepare_knowledge.cmd` remains available if you want to prepare knowledge alone.
The older per-type Python scripts remain optional tools; the main CMD workflow
uses a single combined run.
