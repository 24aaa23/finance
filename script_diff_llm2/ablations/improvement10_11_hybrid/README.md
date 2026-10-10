# Improvement 10/11 hybrid ablation

This is a separate, derived GPT-OSS 120B experiment. It combines Improvement 10's
SQL retrieval operators with Improvement 11's KG retrieval operators, preserving
Improvement 10's Processing Spec and Python Final Spec calculation workflow.
Neither original source snapshot is edited. No grader is launched.

## Architecture

The startup loader combines the physical SQL table metadata and RDF class metadata
into one catalog. A source name must be unique across both backends. The shared
knowledge-preparation agent reads Improvement 10's domain introduction, business
addendum and YAML documents, plus Improvement 11's RDF ontology. Its compiled
pack is installed in both operator families and reused by every worker.

Query understanding, consultation and retrieval select relevant sources. Decomposition
produces one raw retrieval branch per physical source, declaring SQL or KG. The
source's catalog metadata determines dispatch; a conflicting declaration is rejected.
Each branch follows the original fixed operator sequence:

```text
Query understanding + consultation → Retrieve → Decompose
  ├─ SQL source: Query Spec → SQL Generate → Pre-scan Validate → SQLite Scan → Processing Spec
  └─ KG source:  Query Spec → SPARQL Generate → Pre-scan Validate → Fuseki Scan → Processing Spec
                        ↓
             Python Final Spec → Validate → Explain
```

Query Spec, generation, pre-scan validation and repair use the selected baseline's
native operators. Final Spec receives the retrieved rows and performs joins,
aggregations, calculations and ordering using the original Improvement 10 runtime.
The decomposition's dependency annotations describe logical composition; they do
not implement upstream ID injection into downstream scans.

This follows the main hybrid pipeline's schema-grounded backend-selection principles,
but deliberately retains the baseline's raw-retrieval/Python-composition execution.
It does **not** copy the main pipeline's execution of complete computations inside
each SQL/SPARQL node. Backend choices and branch counts depend on the question;
the operator sequence within each branch remains fixed.

The KG is derived from SQL. The planner is instructed to avoid duplicate retrieval
of the same information and choose the smallest useful source set. Cross-backend
joins require documented, compatible identifiers. RDF resource IRIs are not treated
as SQL literal keys, and labels or URI suffixes are not guessed as identity mappings.

## Inputs

Paths below are relative to `script_diff_llm2`:

| Input | Location |
|---|---|
| SQLite database | `ablations/improvement10_models/source/improvement10/wealth_management_diverse.db` |
| SQL metadata and documentation | `ablations/improvement10_models/source/improvement10/table_medatada/` |
| Domain introduction | `ablations/improvement10_models/source/improvement10/domain_intro_latest.prompt` |
| Business rules | `ablations/improvement10_models/source/improvement10/business_rules_addendum.md` |
| 1000-question workbook | `ablations/improvement10_models/source/improvement10/datatset/wealth_management_1000_test_set_questions.xlsx` |
| Evaluation reference overrides | `ablations/improvement10_models/source/improvement10/datatset/216_questions_full_results.json` |
| KG ontology | `ablations/improvement11_gpt_oss_120b/source/improvemnt11kgfixed/kg_output_fixed/wealth_management_diverse_schema.ttl` |
| KG instances | `ablations/improvement11_gpt_oss_120b/source/improvemnt11kgfixed/kg_output_fixed/wealth_management_diverse_kg.ttl` |
| KG query endpoint | `http://127.0.0.1:3041/improvemnt11kgfixed/query` |

The launcher explicitly sets these paths. It uses credentials from the environment
or the project's existing local `.env` loader. All model stages use
`openai.gpt-oss-120b-1:0`. It inherits `BEDROCK_BASE_URL` when configured, otherwise
uses the Bedrock OpenAI-compatible runtime endpoint in `us-east-1`.

The workbook and reference overrides populate benchmark/evaluation records, rather
than the domain-preparation documents. This experiment intentionally preserves the
baseline's supplied business documents; their existing benchmark-related examples
and correction notes are **not** removed. Therefore it inherits the context-provenance
concerns documented in `docs/improvement10_context_leakage_audit.md`; this is not a
claim of a leakage-free business-context condition.

## Run

Run the offline input check first. It makes no model calls and does not need Fuseki:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash ablations/improvement10_11_hybrid/run_raw.sh --check
```

If the Improvement 11 Fuseki server is not already running, start it in a separate
terminal and leave it running:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash ablations/improvement11_gpt_oss_120b/start_fuseki.sh
```

Start the raw experiment:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash ablations/improvement10_11_hybrid/run_raw.sh \
  --run-tag run_01 --workers 4 --max-active-workers 1
```

Four fixed shards contain 250 questions each. Each worker processes one question
at a time, with the query's original operator workflow sequential within that
worker. `--max-active-workers 1` schedules those shards one at a time; this is the
conservative starting setting following the observed Bedrock throttling. To run
two or four shards simultaneously, use `--max-active-workers 2` or `4` respectively.
The launcher defaults to two active workers when the option is omitted. Capacity
is shared with other experiments using the same model/account.

Repeat the same command to resume. Native baseline resume keeps completed rows
and retries its eligible crash, transient/quota, scan and pre-scan failures. Other
semantic failure statuses retain the baseline's original resume policy. Completed
saved rows are not re-executed just because a worker process is restarted.
Changing the active-worker limit does not change shard assignment, so the same
run tag can resume with a different active-worker limit after stopping its launcher.
Keep `--workers 4` unchanged for that run.

The first invocation compiles and reviews a new, isolated hybrid knowledge cache.
Later invocations reuse the cache. Startup stops if preparation fails, the source
snapshots change, or the recorded inputs/code change. Use a new run tag for changed
code or data. Preparation-only invocation is also available:

```bash
bash ablations/improvement10_11_hybrid/run_raw.sh \
  --run-tag run_01 --workers 4 --max-active-workers 1 --prepare-only
```

## Outputs and verification

Combined raw CSV:

```text
ablations/improvement10_11_hybrid/runs/gpt_oss_120b/run_01/raw_pipeline.csv
```

Each `worker_01` through `worker_04` folder contains its question shard, raw CSV,
native diagnostic artifacts and `pipeline.log`. Terminal progress reports the number
of saved rows; 1000 saved rows means every question has a result/status, not that
every answer is correct. Individual logs include `[HYBRID]` routing messages.
Knowledge and RDF metadata caches live under the run's `runtime` folder.

`derivation_manifest.json` records original package-file hashes.
`run_manifest.json` records derived implementation, data/document hashes, model,
endpoint and shard count. Original snapshots are checked before and after running.
The source KG package remains unchanged; adapters and hybrid-specific changes live
only in this ablation's derived SQL package and launcher.

Offline checks cover schema-based routing and rejection of ambiguous/mismatched
sources, backend-specific scans and query generation, RDF metadata preservation,
and a real SQLite/local-RDF fixture joined through the original Final Spec runtime.
They do not validate model-produced plans or establish benchmark accuracy. Run them with:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/python3 -B -m pytest -q \
  ablations/improvement10_11_hybrid/tests/test_hybrid_backend.py
```

### Azure GPT-OSS fresh experiment

Credentials load from `../azure_gpt_oss_120b/azure.env`. The external launcher
connects Azure through the derived pipeline's existing OpenAI-compatible client;
original snapshots and the derived query workflow are unchanged.

```bash
/usr/bin/python3 -u -B ablations/improvement10_11_hybrid/run_raw.py \
  --provider azure --run-tag azure_fresh_01 \
  --workers 4 --max-active-workers 4
```

A new tag executes all 1000 questions without importing previous results. Repeat
this command to resume using the derived pipeline's existing resume policy.
Outputs are `runs/azure_gpt_oss_120b/azure_fresh_01/raw_pipeline.csv` relative to
this ablation folder. Context is enabled and compiled/reused within this run;
no grader starts. The dedicated Improvement11 Fuseki graph on port 3041 is
required. The main pipeline's new decomposition retry loop is not part of this
baseline-derived workflow.
