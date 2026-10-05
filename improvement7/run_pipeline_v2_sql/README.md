# Improvement7 SQL AOP

This is an isolated copy of the improvement6 SQL runtime. Original files, supplied
documents, database, and existing results are not modified. Historical outputs,
old audits, grader programs, credentials, and the bundled fixed business-rule JSON
are not copied. Runtime dependencies and relevant regression tests are retained.

## Minimum inputs

The three knowledge input types are table YAML files, a business-rules document,
and a domain-introduction document. They are not sufficient by themselves: a run
also needs an existing SQLite database, a question CSV/JSONL, Python dependencies,
and credentials/access for the configured model. Schema and DDL are read from the
database. This runner supports SQLite, not arbitrary database engines.

There are only two new LLM stages: Domain compiles knowledge once per cache identity;
Query Understanding interprets each question before the existing AOP flow. They are
bounded model calls with validation, not independent autonomous tool-using agents.
Understanding is optional for ablation. No additional agent is needed for cleanup.

## Optional specialist consultation

Add `--agent-consultation on` to `run.py` or `scripts/run_question_types_v2.py`
to let Decompose, Query_Spec and Final_Spec request the existing specialists when
their supplied context is insufficient, including during self-healing retries.
This is off by default and does not add another agent or change SQL execution.

- Domain consultation re-examines the supplied domain intro, business rules and
  YAML against the question and physical schema. It returns validated source excerpts.
- Query Understanding can reconsider the original interpretation using documented
  schema, the canonical rule pack and any domain advice. A changed interpretation
  restarts Retrieve and Decompose; it never silently changes an executing branch.
- There are at most five specialist requests per question, shared across operators
  and retries. Query Understanding retains its existing three validation attempts
  per request. Consultation does not increase the three decomposition attempts.
- Requests use fixed agent/topic enums. Row samples, SQL, raw runtime errors,
  ground-truth fields and environment configuration are not forwarded. Your supplied
  knowledge documents are authorized context; their existing benchmark commentary
  remains subject to the knowledge-boundary limitations below.
- Advice and revisions appear under `agent_consultations` in the debug repair log.
  Invalid/unavailable advice is not used; existing context and repair loops remain.
  Transport/quota failures retain normal error handling. Repeated requests beyond
  the budget become explicit plan errors, not unlimited recursive calls.

This is operator-requested assistance, not an automatic extra model call on every
error. SQL Refine keeps repairing syntax/DB errors from the retrieval contract;
deterministic arithmetic/join operators do not need domain-agent calls.
Consultation is separate from the coverage and contract checks below. Its
accuracy/cost impact still needs live evaluation.

## Cleanup

Removed unused `config.py`, `dag.py`, `schema_loader.py`, `schema_annotations.py`,
`llm_operators/link.py`, `llm_operators/query_spec_validate.py`,
`non_llm_operators/check_schema.py`, and `non_llm_operators/fuseki.py`.
Removed dead RDF scan/utility code, legacy external alias-map discovery and the
RDF dependency. Retrieve's table index moved to `sql_metadata.py` without changing
its contents. Existing SQL operator names are retained for compatibility.
The obsolete Fuseki-parser test was removed with its implementation; SQL tests,
batch/retry scripts, the comparison script and run documentation remain useful.
All supplied YAMLs are retained because the Domain stage reads them, including
context-only files that do not represent physical tables.

## What changed

- Domain knowledge comes from `../domain_intro_latest.prompt`,
  `../business_rules_addendum.md`, and `../table_medatada/*.yaml` (or `.yml`).
- A startup Domain agent compiles cited, extractive rules. Exact excerpts preserve
  source formulas; unknown schema references, uncited text, benchmark question IDs,
  unresolved conflicts, and incomplete source-section coverage are rejected. Three attempts
  are allowed before startup fails. There is no fallback to the old rule pack.
- Physical schema/DDL comes from SQLite. YAML supplies descriptions, synonyms,
  documented enum values and derived-metric descriptions. YAML does not create
  physical columns, constraints, or keys. Legacy TTL is not loaded by the runner.
- Optional Query Understanding runs once per question before Retrieve. It records
  field owners, metrics, units, grouping, conditions, population and output aliases.
  Original questions are preserved. Valid interpretations return on the first call;
  invalid responses receive at most three calls with validation feedback. After
  exhaustion, the original question continues through the base AOP pipeline without
  an invalid interpretation contract. Attempts and reasons are recorded in the
  debug report's `Debug Understanding Attempts` column. Transport/quota errors
  still use the existing service-error handling.
- Existing Decompose, Query_Spec and Final_Spec consume the interpretation. Missing
  interpreted operands enter the existing decomposition repair loop. Projection,
  output aggregate grouping, ranking and observable outer aggregation checks enter the
  existing final-plan repair loop. These checks do not prove arbitrary formula or
  natural-language equivalence.
  Grouping is checked against compiled output lineage for all supported aggregate
  declaration formats. Ranking preserves requested key priority/direction/null placement
  while allowing extra trailing tie-breaks; it uses the executor's sort-term parser.
- The four existing business-context injection points remain. Financial examples
  and embedded sign assumptions were generalized; supplied documents now own them.

The fixed AOP DAG, SQL rendering/validation, read-only query safeguards, relational
execution, NULL/duplicate semantics, models, and retry budgets are preserved.
Samples/statistics still reach the existing final planner; optional result review
and explanation retain their existing behavior. This is NOT schema-only mode.

## Knowledge boundary

The Domain agent sees supplied documents and physical schema, not database rows,
question datasets, ground truth or environment configuration. Query Understanding
sees the question, documented schema and compiled rules, not result rows or grading.
Ground truth remains a report/evaluation field and is never passed to those agents.
Run manifests store logical input names and hashes instead of absolute input paths.
Local runtime/debug logs can still contain paths, SQL, samples and results.

The supplied addendum contains empirical observations and benchmark commentary.
The compiler is instructed to omit those from runtime rules. Exact-quote and ID
checks are deterministic, but semantic completeness and removal of every empirical
claim are not guaranteed by an LLM. Review the compiled cache before a benchmark.
No accuracy improvement is claimed without live paired evaluation.

## Coverage review

The startup compiler must account for each source section (paragraph, heading/comment,
or table row). Every included section must be fully covered by exact citations to
existing rules; citing one formula does not cover the rest of its paragraph. Blank
lines and Markdown separator lines do not need coverage. All 17 current documents
produce 505 review sections. This inventory is generic, not a list of financial rules.

For non-rule text, superseded rules or benchmark commentary, the compiler must record
an explicit exclusion reason. Mixed sections can be excluded while their reusable
rules are still extracted. Exclusions and their reasons are saved in
`<identity>.coverage.json` for inspection, but do not block a run or require approval.
The pipeline proceeds unattended when structural, citation and coverage checks pass.
Missing coverage entries, partial citations and exclusions without reasons still fail.
An LLM can nevertheless exclude a useful rule incorrectly; the report makes omissions
visible, not semantically verified. No human review is enforced.

`--prepare-knowledge` optionally creates the cache and coverage report without running
questions. Normal runs also compile automatically on a cache miss. There is no
approval command; old approval files are unused. Topic-only domain consultations
validate citations but do not claim to cover or replace the whole startup rule pack.

Cache files live in `../.runtime/knowledge/`. Changes to documents, physical schema,
model or compiler code invalidate the cache. Each run records the knowledge identity,
compiled-pack hash and feature switches; incompatible reports cannot be resumed.
Raw documents are preserved. No credentials are copied. Explicit CLI settings win
over the optional credential file; otherwise only `improvement7/.env` is considered.

## Run from the workspace root

Install dependencies with `python -m pip install -r improvement7/run_pipeline_v2_sql/requirements.txt`
if they are not already installed.

Offline input check (no API calls):

```powershell
python -B improvement7/run_pipeline_v2_sql/run.py --db improvement7/wealth_management_diverse.db --check-inputs
```

Compile/review knowledge before running questions (makes model calls on cache miss):

```powershell
python -B improvement7/run_pipeline_v2_sql/run.py --db improvement7/wealth_management_diverse.db --env-file improvement7/.env --prepare-knowledge
```

Small original-question run, using an existing JSONL manifest:

```powershell
python -B improvement7/run_pipeline_v2_sql/run.py --db experiment_week1/improvement6/wealth_management_diverse.db --env-file experiment_week1/improvement6/.env --questions experiment_week1/improvement6/pipelien_output_sql/benchmark/input_questions.jsonl --output improvement7/outputs/normal/run.csv --limit 5
```

Use `experiment_week1/improvement6/pipleien_outoput_paraphrased/benchmark/input_questions.jsonl`
for its paraphrased counterpart, and a distinct `--output` filename.
For another database, supply `--db` and set `DOMAIN_INTRO_FILE`,
`BUSINESS_RULES_FILE`, `TABLE_METADATA_DIR` to its approved documents.

Input CSV/JSONL may use `Sample Row ID`, `Question`, `Ground Truth`, or
`global_question_id`, `question`, `ground_truth_answer`. Expected answers may be blank.
They are only used for reporting. The existing eight-sheet workbook batch adapter is
available as `scripts/run_question_types_v2.py`; pass `--db`, `--dataset`,
`--env-file` and `--output-root`. `--full-answers` is optional for report-only overrides.

## Timing and latency

To retry only saved execution failures in an existing per-type CSV:

```powershell
python -B improvement7/run_pipeline_v2_sql/scripts/retry_failed_in_place.py --type benchmark
```

Use the other type folder names in separate terminals. `--dry-run` shows selection
without API calls or writes; `--status` shows counts across all eight types.
Successful rows (including answers graded mismatch/partial) and unattempted
questions are not rerun. Each completed retry replaces its row by Sample Row ID
in the existing raw CSV, debug CSV, and JSONL sidecars. The report lock prevents
overlapping writers. Stop or finish the old run for that type first.

Before retrying, originals are copied into `backup_before_retry_<timestamp>`.
Changed code is allowed; the input-question and database hashes must match the
original manifest. The manifest records the mixed-run history, backup, selected
IDs and completed IDs. Ordinary full-run resume cannot reuse this mixed report.
Rerunning the same retry command attempts only errors still remaining. Graded
CSVs are unchanged until the separate grader runs again; its existing resume
logic reuses grades only for unchanged inputs/results.

Question processing has no fixed sleep by default. Set `--query-delay 2` on either
launcher (or `QUERY_DELAY_SECONDS=2` in the selected environment file) to restore
the previous pause if your endpoint needs it. SDK retries/backoff remain enabled.
The full rule pack is preserved; its compact JSON text is serialized once at startup.
No question-result cache, rule pruning, or extra question concurrency is introduced.
Planning prompts place the unchanged business-rule pack before question-specific
content. Query Understanding puts documented schema and rules first, and Retrieve
puts the table index first. This preserves all context while making a long identical
prefix available across questions; provider-side cache hits remain best effort and
must be checked in the recorded token usage, not assumed from prompt ordering.

Progress distinguishes question processing, the question cycle including memory
waits/report writes, and elapsed time since CLI startup. The final `[TIME]` line
includes imports, startup memory waits, schema reads, knowledge-cache validation
or compilation, inference/retries, execution, and final result/log writes.
Interpreter bootstrap and the final timing-summary write are outside the saved
measurement. A separately invoked `--prepare-knowledge` has its own timed run;
it is not added again to a later warm-cache run.

`[TIMING]` points to a per-run JSON file in `.runtime/logs/`, also written on
handled failure/interruption. It records startup time, cache hit/miss, per-question
processing/cycle times, operator times, and model-request durations/token usage.
SDK retries and backoff are included in request duration. Stage times may nest,
so do not sum them as independent wall-clock components. `cached_prompt_tokens`
is null when the endpoint does not report it, not evidence of a cache miss.
Local knowledge caching does not imply provider-side prompt caching.

Current-run timing excludes historical question durations on resume; report-wide
totals are labeled separately. The workbook launcher additionally prints its total
duration including manifest preparation and all child processes.

Code changes require a new `--output` or `--output-root` to preserve run identity.
An already-running process retains its loaded code and original timing behavior.

## Ablation and verification

- External knowledge only: `--query-understanding off --contract-checks off`.
- Understanding without deterministic contract checks: `--query-understanding on --contract-checks off`.
- Full improvement7: both switches on (default).
- Improvement6 remains the unchanged baseline, not an improvement7 switch.

Use separate reports for each configuration. Grade with the existing external
grader, then compare normal/paraphrased MATCH rates, paired correctness, regressions,
execution failures, cost and latency. Never send grader feedback back into inference.

`scripts/compare_results.py --normal <graded-file-or-root> --paraphrased <graded-file-or-root>`
reports matched-ID accuracy, both-correct counts, grade transitions and regression IDs.
Its output describes saved grader verdicts, not independent proof of correctness.

```powershell
python -B -m unittest discover -s improvement7/run_pipeline_v2_sql/tests -v
```

Tests cover the original SQL/runtime behavior, knowledge cache and citation checks,
schema ownership, interpretation validation, and an end-to-end original/paraphrase
pair through the real runner/SQLite executor with mocked model replies. Live model
compilation and answer accuracy require the separate runs above.
