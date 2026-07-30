# AOP GPT-OSS 120B Pipeline Runner

This folder contains everything needed to run:

`firstcheck_gpt_oss_120b_deterministic_json_grading9_1.py`

The script runs an AOP/SPARQL pipeline over a wealth-management RDF knowledge graph, uses Apache Jena Fuseki for SPARQL execution, and calls GPT-OSS 120B through the AWS Bedrock OpenAI-compatible API.

## Folder Contents

```text
aop_gpt_oss_120b_runner/
  firstcheck_gpt_oss_120b_deterministic_json_grading9_1.py
  requirements.txt
  .env.example
  rdf_id_alias_map.json
  dataset/
    verification_results_v2_sql_correct_train_300.xlsx
  kg_output_fixed/
    wealth_management_diverse_schema.ttl
    wealth_management_diverse_kg.ttl
  pipeline_output/
```

## Required Software

Install these before running:

- Python 3.10 or newer
- Java 11 or newer
- Apache Jena Fuseki
- Git, if cloning from GitHub

## Python Setup

From inside this folder:

```bash
python -m venv .venv
```

Activate the environment.

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Environment Setup

Copy the example environment file:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

Edit `.env` and set:

```text
AWS_BEDROCK_API_KEY=your_real_key
BEDROCK_REGION=us-east-1
BEDROCK_GPT_OSS_MODEL=openai.gpt-oss-120b-1:0
FUSEKI_ENDPOINT=http://127.0.0.1:3030/wealth/query
```

Do not upload `.env` to GitHub.

## Start Apache Jena Fuseki

The script expects Fuseki to run locally with dataset name `wealth`.

From inside this folder, run one of these.

If `fuseki-server` is on your PATH:

```bash
fuseki-server --file=kg_output_fixed/wealth_management_diverse_kg.ttl /wealth
```

Windows example using a local Fuseki folder:

```powershell
C:\apache-jena-fuseki\fuseki-server.bat --file=kg_output_fixed\wealth_management_diverse_kg.ttl /wealth
```

Keep this terminal open while the Python script runs.

Check the endpoint in a browser:

```text
http://127.0.0.1:3030/#/dataset/wealth/query
```

## Run a Quick Test

Start with one row so you can confirm credentials and Fuseki are working:

Windows PowerShell:

```powershell
$env:TEST_QUERY_LIMIT="1"
python firstcheck_gpt_oss_120b_deterministic_json_grading9_1.py
```

macOS/Linux:

```bash
TEST_QUERY_LIMIT=1 python firstcheck_gpt_oss_120b_deterministic_json_grading9_1.py
```

The result CSV and API usage log are written to `pipeline_output/`.

## Run the Full Dataset

The default input file is:

```text
dataset/verification_results_v2_sql_correct_train_300.xlsx
```

Run all 300 rows:

Windows PowerShell:

```powershell
$env:TEST_QUERY_LIMIT="300"
$env:TEST_QUERY_OFFSET="0"
python firstcheck_gpt_oss_120b_deterministic_json_grading9_1.py
```

macOS/Linux:

```bash
TEST_QUERY_LIMIT=300 TEST_QUERY_OFFSET=0 python firstcheck_gpt_oss_120b_deterministic_json_grading9_1.py
```

## Useful Options

You can override paths and runtime settings with environment variables:

```text
INPUT_SAMPLE_FILE=dataset/verification_results_v2_sql_correct_train_300.xlsx
INPUT_SAMPLE_SHEET=
SCHEMA_FILE=kg_output_fixed/wealth_management_diverse_schema.ttl
INSTANCE_FILE=kg_output_fixed/wealth_management_diverse_kg.ttl
RDF_ALIAS_MAP_FILE=rdf_id_alias_map.json
PIPELINE_OUTPUT_DIR=pipeline_output
REPORT_FILE=pipeline_output/custom_report.csv
TEST_QUERY_LIMIT=1
TEST_QUERY_OFFSET=0
TEST_MAX_WORKERS=1
FUSEKI_ENDPOINT=http://127.0.0.1:3030/wealth/query
```

Keep `TEST_MAX_WORKERS=1` unless you intentionally want parallel LLM calls.

## Expected Output

The script writes:

- `pipeline_output/Pipeline_Debug_Report_gpt_oss_120b_difficulty_train_300_v15_grading9_1_full300.csv`
- `pipeline_output/api_usage_log_YYYYMMDD_HHMMSS.json`

If the run stops because of quota or a crash, rerun the same command. The script can resume from the existing report.

## Common Problems

`AWS_BEDROCK_API_KEY is required`

Your `.env` file is missing the Bedrock key, or the key name is incorrect.

`BEDROCK_REGION is required`

Set `BEDROCK_REGION`, for example `us-east-1`.

Fuseki metadata extraction failed

Make sure Fuseki is still running and the dataset URL is `http://127.0.0.1:3030/wealth/query`.

Port 3030 already in use

Stop the other Fuseki process, or start Fuseki on another port and update `FUSEKI_ENDPOINT`.

## GitHub Upload Notes

This folder is ready to upload as one folder in a GitHub repository. The `.env` file should not be committed. The KG TTL file is about 40 MB, which is below GitHub's 100 MB per-file limit, but Git LFS is still a good idea if you plan to add larger datasets later.
