# Improvement8 v3 SQL AOP

Run this copy using its quoted folder name: `run_pipeline_v3_sql _`.
The entry points load this folder as `run_pipeline_v3_sql`; they do not import v2.
The Retrieve, Decompose, Query_Spec, Generate, Scan, Final_Spec and local execution
flow is retained. The existing Domain Knowledge specialist handles terminology
and business rules when an operator requests help. No additional agent is added.

## Prompt inputs

- Retrieve uses the physical table/column index.
- Decompose and Query_Spec use relevant YAML definitions and required connectors.
- Final_Spec uses the question, declared branch columns, retrieval contracts,
  complete relevant YAML metadata (including YAML examples) and specialist advice.
  Live Scan samples, result row counts and observed column statistics are excluded.
- Supplied YAML, domain and business-rule files are loaded unchanged. No fields,
  examples, sample values, counts or reference notes in those files are masked.
- Query Understanding has no hardcoded investor aggregation default.
- Semantic answer review is disabled, including legacy opt-ins. Validation checks
  execution structure locally. Explain always serializes results locally as JSON.
- Ground truth loaded from question records stays in reports and the separate grader.

The default rules input is the original `improvement8/business_rules_addendum.md`.
`--business-rules` and `--domain-intro` can select replacement documents. Content
validation checks structure and citations, without rejecting supplied source content.
All knowledge modes receive complete source content; knowledge extraction can still
summarize relevant policies, but no source field is redacted at ingestion.

Knowledge is still compiled/cached at startup using the existing process.
On-demand domain consultation remains enabled by default, without a count cap.
A document/schema change gives a fresh knowledge cache identity. V3 uses
`.runtime/knowledge_v3` by default and its own source/data run identity.

## Recovery after the saved v3 planning failures

Decompose now retains schema-backed source owners and raw operands explicitly
required by Query Understanding. It does not invent predicates or connections.
Query_Spec sees only its assigned table definition; an attempted source switch
still fails validation. Derived grouping aliases are supported without requesting
them as raw columns. Distinct label lists no longer fail an unrelated aggregate
grain check. Field-to-field conditions belong in local calculation, not raw
literal filters. Final_Spec's prompt makes existing datasets, formula steps and
declared join uniqueness explicit. Runtime validation remains enabled.

Running Python processes keep the version already loaded. Finish or stop the old
v3 jobs before retrying. Existing failure rows are historical results until retried.
From CMD in `improvement8`, inspect counts and retry saved failures with backups:

```cmd
python -B "run_pipeline_v3_sql _\scripts\retry_failed_in_place.py" --status
for %T in (benchmark at_risk_critical batch_status enrichment_context multi_step_comparative reference_compliance scoring_quantitative temporal_transaction) do python -u -B "run_pipeline_v3_sql _\scripts\retry_failed_in_place.py" --type %T
python -B "run_pipeline_v3_sql _\scripts\retry_failed_in_place.py" --status
```

The loop runs one category at a time. For eight terminals, use the same command
with `--type` followed by a different category name in each terminal. Success rows
are retained; each category's original reports are backed up before replacement.
These retries make model calls. Offline tests do not guarantee success or answer
accuracy for every future model response.

## Offline validation (CMD, from the workspace root)

```cmd
python -B "improvement8\run_pipeline_v3_sql _\run.py" --check-inputs
python -B -m unittest discover -s "improvement8\run_pipeline_v3_sql _\tests" -p "test_*.py"
```

## Run one category (CMD, from the workspace root)

```cmd
python -u -B "improvement8\run_pipeline_v3_sql _\run.py" --env-file "improvement8\.env" --questions "improvement8\dataset\ARC.csv" --output "improvement8\pipelien_output_sql_v3\at_risk_critical\raw_pipeline_v9.csv" --limit 0
```

Use the corresponding CSV and a separate output folder for each category.
An actual run makes model calls. The offline checks make none.
Do not reuse a v2 report filename for v3: the run identity deliberately differs.
Default outputs and copied batch launchers use v3 locations. The existing
`improvement8/start_dataset_terminals.ps1` continues to launch v2.

## Changing databases

Supply `--db`, `--yaml-dir`, `--domain-intro` and `--business-rules` together as
needed. Definitions and policies come from those inputs rather than hardcoded
formulas. YAML/DDL metadata declares available structure; no rows are read for
planning metadata. Only local Scan/execution reads database contents.
