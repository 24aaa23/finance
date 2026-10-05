# How to run the pipeline (Windows PowerShell)

## 1. Put the code and inputs in this layout

You can share `run_pipeline_v2_sql` as the code package. The recipient must also
provide these external inputs, a question dataset, and their own model credentials.
The code folder alone is not a complete runnable dataset. No separate launcher
script outside the package is needed for the commands below.

```text
project/
  run_pipeline_v2_sql/          # Entire code folder, including requirements.txt
  table_medatada/               # Correct YAML schema and domain metadata
  business_rules_addendum.md
  domain_intro_latest.prompt
  wealth_management_diverse.db  # SQLite database matching the YAML
  .env                         # Recipient's model credentials
  dataset/
    ARC.csv
    BSQ.csv
    EC.csv
    MC.csv
    RC.csv
    SQA.csv
    TT.csv
    WM.csv
```

YAML is authoritative for planning. The database is used for SQL execution.
For your own question CSV, include `global_question_id`, `question`, and
`ground_truth_answer` columns. Ground truth can be blank and is used for reporting,
not supplied to the model as an answer. JSONL with the same fields is also supported.

## 2. Open PowerShell in the parent folder

On the current computer:

```powershell
Set-Location "C:\Users\AMAN KUMAR SINGH\Desktop\financial\improvement8"
```

On another computer, replace that path with the `project` folder containing
`run_pipeline_v2_sql`. Use this same working directory in every terminal below.

## 3. Install dependencies once

Use Python 3.10 or newer. These commands create a local environment; activation
is not required because subsequent commands use its Python executable directly.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\run_pipeline_v2_sql\requirements.txt
```

## 4. Configure model access

Keep your existing working `.env`. On another computer, create `.env` beside
the code folder with the recipient's own values:

```dotenv
AWS_BEDROCK_API_KEY=YOUR_BEDROCK_API_KEY
BEDROCK_REGION=YOUR_BEDROCK_REGION
BEDROCK_GPT_OSS_MODEL=openai.gpt-oss-120b-1:0
```

The configured Bedrock region/account must provide access to this model.
The code supports `BEDROCK_BASE_URL` instead of constructing an endpoint from
the region. Do not distribute your personal `.env` with the code package.

## 5. Check the documents and YAML (no model calls)

```powershell
.\.venv\Scripts\python.exe -B .\run_pipeline_v2_sql\run.py --check-inputs
```

This validates the documents and YAML; it does not compare the YAML with SQLite.

## 6. Prepare the shared business-rule cache once

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\prepare_knowledge.py --env-file .\.env
```

The dedicated script uses `simple` mode and normally makes two model requests
for a new cache. It reuses a matching generated cache on later runs; changing
the input documents, YAML schema or model creates a new cache identity.
The first receives all original documents and the YAML physical schema, with
instructions to inventory useful knowledge across every source and subsection.
The second receives those same documents and the draft rules to find omissions,
correct oversimplifications, and check conceptual names against physical YAML
columns. It returns additions and individual corrections; other draft rules
remain available. Python applies these additions and corrections to save the
final JSON. The review checks numeric scopes, tolerances, normalization guards
and column mappings against the sources; there is no third regeneration call.
These stages run during creation, not for every question.

Rules can include optional document source IDs, fields, citations and unresolved
conflicts. Source IDs provide traceability without exact quotations. Python
assigns rule IDs; complete JSON and usable nonempty rule text remain required.
Prose can be summarized; formulas, conditions and exceptions should be preserved.
There is no required rule count, section coverage or exact-quote copying gate.
Invalid optional fields/citations are omitted from metadata and recorded in
`validation_notes`; the rule text itself is retained. Benchmark references do not
reject the cache. Conflicts are retained and included in planning context.
Each stage allows up to three validation attempts with feedback; transport
retries are separate. If review fails or is unavailable, the usable draft is
saved with `review_status:unavailable` and a diagnostic note. A completed review
is recorded as `review_status:completed`. These statuses do not prove semantic
completeness or accuracy; inspect the cache and evaluate it on the dataset.
Normal startup uses the same mode on a cache miss and reuses the completed cache
for subsequent questions. No existing improvement7 cache is copied or imported.

Set `--knowledge-mode` consistently during preparation and execution. Its default
is `DOMAIN_COMPILATION_MODE` from the environment or `.env`, otherwise `simple`.
CLI settings win. Changing modes creates a different cache identity. This mode
requires all inputs and the complete response to fit the model's limits; repeated
invalid JSON or unusable rules still fail. The `.coverage.json` report explicitly
records `coverage_checked:false` and review status in simple mode; it does not
claim deterministic completeness.
Progress logging, complete-JSON parsing, the 32,768 output-token default and the
300-second per-request timeout are retained from improvement8.

To test an existing saved cache without generating new rules, add
`--knowledge-cache .\.runtime\knowledge\<identity>.json` to preparation and run
commands. This validates the saved hash and its compatibility with the supplied
documents/schema, records an input/model binding beside the selected file, and
reuses that exact rule pack. Subsequent document/schema/model changes invalidate
the binding and require fresh preparation. The first explicit selection records
the current test inputs; it is not proof of the cache's original provenance or
semantic correctness. A selected cache remains usable across creation-prompt
changes because its saved rules are not regenerated.

`--knowledge-mode improvement7` retains the older strict whole-document prompt,
exact citation and section coverage checks when explicitly requested.

For the resumable chunked mode, use the following command and also add
`--knowledge-mode chunked` to subsequent pipeline commands:

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --prepare-knowledge --knowledge-mode chunked
```

Chunked preparation determines boundaries, compiles and checkpoints each chunk,
merges rules, and reviews cross-document consistency automatically.

During extraction Python divides source sections into selectable fragments
(sentences, list items and table cells), preserving the exact source text and
keeping full documents available as context. The model returns fragment IDs in
rules and an explicit reason for every other selectable fragment it omits. It
does not copy quotations or write coverage mappings. Python copies the selected
text, derives citations, and computes full or partial source-section coverage.
Benchmark identifiers and table separators are unselectable and their exclusions
are recorded automatically. Every other fragment needs a model decision; useful
rules beside benchmark commentary must still be retained. Full citation/coverage
checks run on the resulting pack; no fuzzy matching or quote rewriting is used.

Wait for successful completion and `[CACHE] Knowledge compiled` (or `hit` if a
valid cache already exists). First preparation may take several minutes or longer.
If it exits with an error, resolve that error before step 7. Chunked mode reuses
completed compatible chunks when the same preparation command is repeated.

During preparation, `[KNOWLEDGE]` messages show the compilation stage, attempt (1/3 to 3/3),
elapsed waiting time every 20 seconds, response finish reason, token usage,
validation failures and the saved cache path. A waiting message proves the local
process is alive; it cannot prove that the remote model is generating tokens.
SDK retries may be included in that waiting time. Live diagnostic events are also
written to the printed `.runtime/logs/knowledge_*.jsonl` file. Rejected answer
content is saved separately as `knowledge_*_attempt_*.rejected.json` with the exact
error and finish reason. These local diagnostics can contain source excerpts;
request prompts and client credentials are not included. If JSON validation
fails repeatedly, inspect the printed diagnostic file rather than repeatedly
rerunning without knowing the error. Complete reasoning/fence wrappers are
handled, but broken JSON is not silently repaired. Validated rules are saved in the
checkpoints. Code edits only take effect on a new process.

In chunked mode, current inputs produce 22 extraction chunks. Each requires one successful model
call, with up to three validation attempts. A compact consistency review follows;
larger rule sets use multiple bounded reviews covering every pair of rule groups.
SDK transport retries are separate. A small input that fits in one chunk needs
only the original one-call compilation/validation flow. No fixed duration or
accuracy improvement is guaranteed.

Successful checkpoints are in `.runtime/knowledge/parts/<identity>/`:
`chunk_0001.json`, etc., and `review_0001.json`, etc. They are integrity-checked on
resume and cannot be used as the final cache until all stages pass. Input/schema,
model, compiler or chunk-setting changes create a new identity. Unresolved
conflicts block the final cache. Explicit addendum supersession decisions are
stored in the review checkpoints and the final coverage exclusions. Other rules
retain their exact citations; deterministic checks do not prove semantic accuracy.

Chunk sizing targets 6,000 source characters. Paragraphs, tables and YAML files
are kept intact, so a unit can exceed that target. Oversized indivisible units
fail explicitly instead of silently cutting a formula or YAML definition. If
needed, set `DOMAIN_CHUNK_CHARS` and `DOMAIN_REVIEW_CHARS` in `.env` (defaults:
6000 and 100000). Larger values increase per-call size. `DOMAIN_MAX_OUTPUT_TOKENS`
and `DOMAIN_TIMEOUT_SECONDS` remain configurable (32768 and 300 by default).

The cache and coverage report are saved under `.runtime/knowledge/`, outside the
code package. All terminals reuse this cache. Changes to source documents, YAML,
the model or compiler invalidate it automatically. A database data-only change
does not require recompiling unchanged rules.

## 7. Run the eight CSVs in eight separate terminals

Open eight PowerShell terminals. In each terminal, first run the `Set-Location`
command from step 2. Then run only its corresponding command below.
`--limit 0` means all questions. Keep each terminal open until it finishes.

Terminal 1 — ARC:

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --questions .\dataset\ARC.csv --output .\pipelien_output_sql\at_risk_critical\raw_pipeline_v9.csv --limit 0
```

Terminal 2 — BSQ:

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --questions .\dataset\BSQ.csv --output .\pipelien_output_sql\batch_status\raw_pipeline_v9.csv --limit 0
```

Terminal 3 — EC:

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --questions .\dataset\EC.csv --output .\pipelien_output_sql\enrichment_context\raw_pipeline_v9.csv --limit 0
```

Terminal 4 — MC:

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --questions .\dataset\MC.csv --output .\pipelien_output_sql\multi_step_comparative\raw_pipeline_v9.csv --limit 0
```

Terminal 5 — RC:

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --questions .\dataset\RC.csv --output .\pipelien_output_sql\reference_compliance\raw_pipeline_v9.csv --limit 0
```

Terminal 6 — SQA:

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --questions .\dataset\SQA.csv --output .\pipelien_output_sql\scoring_quantitative\raw_pipeline_v9.csv --limit 0
```

Terminal 7 — TT:

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --questions .\dataset\TT.csv --output .\pipelien_output_sql\temporal_transaction\raw_pipeline_v9.csv --limit 0
```

Terminal 8 — WM:

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --questions .\dataset\WM.csv --output .\pipelien_output_sql\benchmark\raw_pipeline_v9.csv --limit 0
```

For just one dataset, run only the corresponding command. Each process handles
one question at a time. The usual defaults enable query understanding and contract
checks and specialist consultation. Decompose, Query_Spec and Final_Spec may
request Domain or Query Understanding advice when needed, with no consultation
request-count cap. Repeated requests can continue until a normal plan is returned,
an error stops the run, or you interrupt it. Validation, planning-repair and SDK
retry limits remain separate and unchanged. Domain consultation sends the supplied documents again and can
increase latency and token use. Use `--agent-consultation off` for an ablation.
The eight-terminal launcher explicitly enables consultation. The in-place retry
tool preserves the saved report's consultation setting for comparability.
Already running processes retain their previous setting. After this code/config
change, use a fresh output location if existing reports fail run-identity checks.

## 8. Find results and resume

Each category folder under `pipelien_output_sql/` receives:

- `raw_pipeline_v9.csv` — answers, ground truth, status and timing.
- `raw_pipeline_v9_debug.csv` — debugging information.
- `raw_pipeline_v9.jsonl` and `raw_pipeline_v9_debug.jsonl` — JSONL results.
- `raw_pipeline_v9.csv.manifest.json` — run identity for safe resume.

Detailed logs and timing files are under `.runtime/logs/`.
Accuracy grading is a separate step; successful execution is not an accuracy score.

New runs also save measurements needed for later evaluation:

- Result CSV/debug CSV and JSONL rows include `Timing Run ID`, `Target Model`,
  `Generation Input Tokens`, `Generation Output Tokens`, `Cached Input Tokens`,
  `Generation Latency Seconds`, `Model Calls`, `Failed Model Calls`, and
  `Calls Missing Token Usage`. Generation here means ALL model calls for that
  question attempt, including interpretation, consultation and repair. It excludes
  startup cache compilation. Missing usage stays blank/null, never silently zero.
- Each category's `_telemetry/` folder holds one `<run-id>.events.jsonl` per process.
  Request starts and completed calls are appended immediately; interrupted runs
  retain earlier measurements. A started call with no finish has unknown usage.
  `<run-id>.timing.json` is also saved at normal or handled exit, alongside the
  existing `.runtime/logs/` timing file. These are alternate representations of
  the SAME calls; do not sum events and summaries together.
- Standalone `--prepare-knowledge` measurements are stored separately in
  `pipelien_output_sql/_preparation/_telemetry/`. Keep failed preparation attempts
  if you want total experiment expenditure rather than just successful-run cost.

On resume, report rows contain the retained/latest attempt's measurements. Keep
all telemetry files to account for prior failed/replaced attempts as well. A
request duration includes SDK retries/backoff, but tokens consumed by hidden SDK
retries may not be returned by the provider. These records support cost estimates;
they do not replace provider billing. No prompts, answers or credentials are
included in telemetry. Grading and calculation of accuracy/F1/priced cost remain
separate future steps. Existing runs cannot gain missing measurements retroactively.

To resume an interrupted category, stop its old process and repeat the same command
with unchanged inputs and code. Completed compatible rows are skipped. If inputs
or code changed, use a new output folder rather than overwriting previous results.

## Using different input filenames or locations

Defaults resolve from the parent of `run_pipeline_v2_sql`, regardless of its name.
For replacement inputs, pass all relevant options consistently during preparation
and execution. Run from the parent folder, adjusting the external paths below:

```powershell
.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --db .\new_data.db --yaml-dir .\new_metadata --domain-intro .\new_domain.prompt --business-rules .\new_rules.md --prepare-knowledge

.\.venv\Scripts\python.exe -u -B .\run_pipeline_v2_sql\run.py --env-file .\.env --db .\new_data.db --yaml-dir .\new_metadata --domain-intro .\new_domain.prompt --business-rules .\new_rules.md --questions .\dataset\questions.csv --output .\pipelien_output_sql\new_run\raw_pipeline_v9.csv --limit 0
```

These knowledge/database inputs must stay outside `run_pipeline_v2_sql`.
The four input-path settings in `.env` are ignored; use the CLI options above.
