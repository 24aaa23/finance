# How to run the Improvement11 KG pipeline

Use **Windows Command Prompt (CMD)**. The complete dataset runs in one terminal,
with one question processed at a time.

## Before the first run

You need Python 3.10 or newer, Java 21 or newer, and working model credentials
in this folder's `.env`. Internet access is needed for model requests.
Fuseki is already included in `tools/apache-jena-fuseki-6.1.0/`.

Open CMD and enter the project folder:

```cmd
cd /d "C:\Users\AMAN KUMAR SINGH\Desktop\financial\improvemnt11kgfixed"
```

If this project is copied to another computer, use its new folder path instead.
You can check Python and Java with:

```cmd
python --version
java -version
```

Install the Python dependencies once if they are not already installed:

```cmd
python -m pip install -r run_pipeline_v2_kg\requirements.txt
```

## Start the server and run the dataset

Paste these commands into the same CMD terminal:

```cmd
cd /d "C:\Users\AMAN KUMAR SINGH\Desktop\financial\improvemnt11kgfixed"
powershell -NoProfile -ExecutionPolicy Bypass -File start_kg.ps1
run_dataset.cmd
```

1. `start_kg.ps1` starts this project's Fuseki server in the background, or reuses
   a verified matching server. Wait for `Endpoint ready` and the CMD prompt to return.
2. `run_dataset.cmd` prepares all **1,000 questions** from the local workbook as
   one input. It builds or reuses the knowledge cache, then runs the questions.

The endpoint is `http://127.0.0.1:3041/improvemnt11kgfixed/query`.
The first knowledge build can take several minutes. Messages such as
`Whole-document compilation ... waiting for model` mean knowledge preparation is
still running. Later launches show a cache hit when the inputs are unchanged.
Changing the ontology, domain document or business rules can require rebuilding it.

The file `216_questions_full_results.json` supplies full reference answers for
216 question IDs; the run still includes all 1,000 workbook questions.

## Find the results

The main report is:

```text
pipeline_output_kg_v11\raw_pipeline_v9.csv
```

The `v9` filename is retained for compatibility with existing tools.
Related JSONL results, debug files and telemetry are saved alongside the report.
Pipeline logs are in `.runtime/logs/`. The terminal prints the log path for each run.

## Resume or retry

To continue an interrupted run, use:

```cmd
run_dataset.cmd
```

This resumes a compatible saved report. Code, data or knowledge changes can make
an older run incompatible; preserve the old results before starting a fresh run.

To retry **only saved execution errors**, use:

```cmd
run_dataset.cmd --retry
```

Retry requires an existing report, backs it up, and keeps successful rows.
If there are no saved execution errors, it exits without model calls.
Retry does not process questions that have never been attempted.

## Optional checks

Check the input files without model calls:

```cmd
run_dataset.cmd --check
```

Check the running KG without model calls:

```cmd
python -u -B run_pipeline_v2_kg\run.py --env-file .env --check-kg
```

To view Fuseki logs in a terminal, run `start_fuseki.cmd`.
Ctrl+C closes that log view while the background server keeps running.

## Project files

| Purpose | Location |
| --- | --- |
| Pipeline code | `run_pipeline_v2_kg/` |
| Credentials | `.env` |
| Domain knowledge | `domain_intro_latest.prompt` |
| Business rules | `business_rules_addendum.md` |
| Ontology | `kg_output_fixed/wealth_management_diverse_schema.ttl` |
| KG data | `kg_output_fixed/wealth_management_diverse_kg.ttl` |
| Question workbook | `datatset/wealth_management_1000_test_set_questions.xlsx` |
| Full reference answers | `datatset/216_questions_full_results.json` |
| Fuseki installation | `tools/apache-jena-fuseki-6.1.0/` |
| Caches and logs | `.runtime/` |
| Results | `pipeline_output_kg_v11/` |

The `datatset` spelling matches the actual folder. All default project files stay
inside `improvemnt11kgfixed`; Python and Java are system prerequisites.
For further details, see [pipeline instructions](run_pipeline_v2_kg/RUN.md).
