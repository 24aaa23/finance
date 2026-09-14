# V6 plan and evaluation contract

## Goal

Improve generalization by making each stage do one job and by removing a second
model interpretation from raw retrieval. V6 must be measured against V4 on the
same questions, input order, schema, Fuseki data, and model settings.

## Changes in this version

1. Keep Decompose responsible for source branches and declared connections.
2. Keep Query_Spec responsible for one validated raw-source contract.
3. Compile a complete single-source contract into raw SPARQL in Python. Use the
   LLM only when RDF metadata is incomplete or a filter is unsupported.
4. Keep Final_Spec responsible for ordered joins, aggregation, formulas, and
   ranking. Do not add question IDs, expected answers, or benchmark-specific
   rules.
5. Preserve bounded repair attempts and record every contract, executed query,
   error, and self-heal attempt in the report.

## What this does not guarantee

V6 is expected to be more stable for retrieval syntax, optional fields, typed
dates/numbers, and retry behavior. It is not guaranteed to be more accurate:
source selection, relationship meaning, and ambiguous business definitions are
still model decisions. A fresh matched run and semantic grading are required.

## Acceptance checks

- Offline tests pass.
- `run.py` imports and executes the V6 package, not V4.
- Deterministic generation makes zero model calls for a complete contract.
- Incomplete metadata uses the documented fallback.
- Compare V4 and V6 using the same 442 workbook and fresh report filenames.
- Report separately: pipeline success, self-heal count, execution failures,
  MATCH, PARTIAL, and MISMATCH. Never treat execution success as correctness.

## Run

```powershell
$env:INPUT_SAMPLE_FILE = 'C:\Users\AMAN KUMAR SINGH\Desktop\financial\experiment_week1\improvement3\dataset\verification_results_v2_sql_correct_442.xlsx'
$env:TEST_QUERY_LIMIT = '442'
$env:TEST_QUERY_OFFSET = '0'
$env:REPORT_FILE = 'C:\Users\AMAN KUMAR SINGH\Desktop\financial\experiment_week1\improvement3\pipelien_output\raw_pipeline_v6.csv'
python experiment_week1/improvement3/run_pipeline_v6/run.py
```

For a smoke test, set `TEST_QUERY_LIMIT=20` and use a separate report name.
Do not overwrite the existing V4 CSVs.
