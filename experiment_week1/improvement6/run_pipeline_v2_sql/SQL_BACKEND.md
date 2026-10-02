# SQLite backend for the existing v2 pipeline

Default database:

```text
experiment_week1/improvement6/wealth_management_diverse.db
```

This package uses the eight actual SQLite tables and their columns. It also
reads the small schema TTL used by KG for matching business documentation.
It does not load the instance graph or alias map, and does not contact Fuseki.
SQLite is opened read-only; generated statements cannot modify the database.

## Business metadata shared with KG

`sql_metadata.py` attaches the same schema annotations used by KG: table
descriptions, column descriptions, synonyms, documented allowed values, and
derived-metric descriptions. `SCHEMA_FILE` selects the documentation file;
the default is `kg_output_fixed/wealth_management_diverse_schema.ttl` under
`improvement6`, matching the KG default. YAML files are not read separately.

Only existing SQLite tables and columns are annotated. Context classes in the
TTL do not become SQL tables, derived metrics do not become stored columns,
and SQL types, names, nullability, and declared keys remain authoritative.
Allowed values are documentation, not a verified exhaustive list of observed
database values. No additional sampling or category restrictions are added.

Decompose and Query_Spec receive enriched relevant schemas; Final_Spec receives
the source descriptions, documented metrics, and metadata for available fields.
Retrieve retains the same lightweight table/column index as KG. All eight
current SQL tables and all 70 columns match documentation. Missing/invalid
schema files fail startup; unmatched tables produce a coverage warning.

The schema file is included in the run manifest. For a fresh comparison after
this change, rerun every question into a new root such as
`--output-root pipelien_output_sql_metadata_v1`. Reusing an old report fails the
source/data identity check. Error-only retries cannot measure the full effect
of this prompt-context change. Stop old terminals before starting the new run;
already running processes may still hold the old metadata in memory.

This aligns the business-documentation source, not all SQL and RDF semantics
or model outputs. The graph representation and physical SQL schema still differ.

The pipeline flow remains:

```text
Retrieve -> Decompose -> fixed DAG
  each branch: Query_Spec -> Generate -> Pre_Scan_Validate -> Scan -> Processing_Spec
  combined: Final_Spec -> existing Python calculation operators -> Validate -> Explain
```

Only the data-source boundary and its prompt terminology changed. Generate
renders the raw retrieval contract as SQL. Pre_Scan_Validate checks that SQL
against the same contract and compiles it with SQLite. Scan returns native
SQL values and NULLs without dropping duplicate rows. Joins, aggregations,
formulas, grouping and ordering still run in the existing Python operators.

The DAG builder, planner, calculation execution, specification compiler and
contract rules, relational operators, profiles, business-rule pack, reporting,
Processing_Spec, Validate, Explain and grader files remain unchanged from v2.
No model, credential file, decomposition policy, retry count or business rule
was changed. The original `run_pipeline_v2` package was not edited.

Existing internal names such as `sparql`, `failed_sparql`, `class` and the
`Debug SPARQL` report column are retained for compatibility; their query text
is SQL and their source names are SQLite tables in this package. Unused legacy
RDF graph-execution helpers remain unused; the schema annotation helper is
shared in behavior with KG for business documentation only.

## Run

From `improvement6`, in CMD or PowerShell:

```text
python run_pipeline_v2_sql/scripts/run_question_types_v2.py --type "Benchmark"
```

Use the same command with another of the eight existing type names in a
separate terminal. Omit `--type` to process all types sequentially. The existing
`--limit`, `--offset`, `--env-file`, `--prepare-only`, and `--output-root` options
are retained.

SQL results default to `pipelien_output_sql/<type>/`, avoiding the existing
KG reports and their source manifests. Filenames and report schemas remain the
same. The SQL manifest fingerprints the database and business-metadata schema.

`SQLITE_DB_PATH` can override the database and `SQL_SCAN_TIMEOUT_SECONDS`
defaults to 60 seconds. The existing local `.env` loading behavior is unchanged.
No Fuseki startup command is required.

## Retry only QUERY_SPEC_ERROR questions after the SQL compatibility fix

Let the original terminals finish or stop them before starting retries. The
launcher checks report locks and refuses to read a report still being written.
From `improvement6`, run all eight types sequentially:

```text
python run_pipeline_v2_sql/scripts/run_question_types_v2.py --retry-query-spec-errors
```

For eight terminals, use the same flag with one different `--type` in each:

```text
python run_pipeline_v2_sql/scripts/run_question_types_v2.py --type "Benchmark" --retry-query-spec-errors
```

The launcher reads each original `pipelien_output_sql/<type>/raw_pipeline_v9.csv`
and selects only rows whose saved status is `QUERY_SPEC_ERROR`. It does not
reload the workbook, include successful/other-error rows, or run questions the
original report has not attempted. Types with no Query_Spec failures are skipped.
Do not pass `--limit` or `--offset` in this mode.

Results and debug CSV/JSONL files go to
`pipelien_output_sql/<type>/query_spec_retry/`. The original reports and grades
are untouched. This separate report has the corrected code's own source/data
manifest; the existing protection against mixing code versions remains enabled.
The retry input records preserve the source report path, hash and run identity.

The failed-question selection is frozen on first use. Repeating the command
resumes that selection: missing results and remaining `QUERY_SPEC_ERROR` rows
are attempted; successful results and other completed error statuses are kept.
Old retry failures are replaced one at a time without dropping unattempted rows.
Use `--prepare-only` with the retry flag to prepare the selection without model
calls. Complete the original run before preparing it so all its failures are
included. Retry results require separate grading; prior grades do not update.

The compatibility fix normalizes explicit NULL checks and unambiguous ISO-date
BETWEEN bounds across Decompose, Query_Spec comparison and SQL rendering. It
does not change metric formulas, relax source-table checks, or reinterpret
ordinary equality comparisons to the literal string `NULL`.

## Verification

All 233 tests pass with `python -m unittest discover -s run_pipeline_v2_sql/tests -v` from `improvement6`.
Metadata tests check all physical tables/columns against the shared documentation,
preserve the SQL schema, reject missing/invalid documentation, and inspect actual
Decompose, Query_Spec, and Final_Spec prompts in the offline integration run.
This includes NULL/date compatibility, literal and table-check preservation,
error-only cohort selection, a main-runner retry/resume check, and downstream
predicate-stage protection with no live API calls.
SQL-specific tests cover schema discovery, read-only enforcement, timeouts,
literal escaping, filter semantics, NULLs, duplicate preservation and contract
validation. The complete main pipeline was tested against the real database
using scripted model responses, including two raw branches followed by Python
join/group/sum; the result matched a direct SQLite query. That test prohibited
KG parsing and network calls and verified the database checksum was unchanged.
The copied retrieval tests were adapted to SQL fixtures; calculation assertions
remain in place. No live model benchmark was launched as part of this conversion.

## SQL compatibility review (October 1)

Only `run_pipeline_v2_sql` retains changes from this review. Every Python source
file in the SPARQL package matches its saved `run_v5_memory_safe` source manifest.
The DAG/planner, calculation execution, specification compiler, relational and
numeric operators, business rules, Processing_Spec, Validate and Explain remain
identical between packages. Model and retry-count configuration also matches.

Additional SQL checks address observed saved traces:

- ISO date pairs separated by `AND` or `|` normalize to two endpoints. Arbitrary
  strings, invalid dates and changed endpoints are not accepted as equivalent.
- Unsupported raw operators such as `LIKE` are rejected at Decompose so its
  existing repair loop can express the requested condition in supported syntax.
  No automatic LIKE-to-contains or guessed-date-range rewrite is performed.
- Query_Spec rejects applying an explicitly downstream predicate to raw records,
  unless that same condition is separately required at Scan for the same branch.
  For example, testing whether net cash flow is negative must not discard positive
  transactions before summing. The failed contract is returned for repair; its
  filter is not silently removed. This guard does not prove full plan correctness.
- The PowerShell question-type wrapper now forwards `-RetryQuerySpecErrors`.

Wrong-source checks remain strict. These compatibility and validation changes
can alter generated plans and outcomes, despite unchanged overall architecture.
Use a new full SQL run and separate grading to measure accuracy. Offline test
success does not establish that all live model plans or answers will be correct.
