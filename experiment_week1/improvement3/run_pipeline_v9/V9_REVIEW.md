# V9 review and changes

All changes and new reports are inside this directory. The runner uses the
existing RDF/SPARQL retrieval and Python operators. It does not generate or
execute SQL, read reference queries during inference, or look up answers by ID.
The copied V8 comparative-contract framework was not added.

## What the completed V7 results show

The first inspection happened while inference/grading files were still growing.
The final audit below uses all 192 completed rows. Question text agrees with the
reference workbook for every row; all three inference manifests agree with V7's
recorded source hashes.

| Cohort | Rows | MATCH | PARTIAL | MISMATCH | OTHER | Execution failure |
|---|---:|---:|---:|---:|---:|---:|
| Prior success | 55 | 26 | 14 | 7 | 4 | 4 |
| Non-success part 1 | 69 | 27 | 22 | 19 | 1 | 0 |
| Non-success part 2 | 68 | 9 | 28 | 31 | 0 | 0 |
| Total | 192 | 62 | 64 | 57 | 5 | 4 |

The comparative family has **11 MATCH, 30 PARTIAL and 35 MISMATCH out of 76**.
Execution success is therefore a poor substitute for answer correctness.

The complete per-question grades, explanations, source queries and saved plans
are in [docs/v7_audit/questions.csv](docs/v7_audit/questions.csv) and
[docs/v7_audit/evidence.json](docs/v7_audit/evidence.json).
[The snapshot](docs/v7_audit/snapshot.json) records file hashes and row counts.
These are offline review artifacts, not inference inputs.

## Root causes and the corresponding changes

| Observed issue | Evidence | V9 treatment |
|---|---|---|
| Schema meanings were discarded | The source schema documents allocation change and describes the before/after fields, but the loader gave planners empty descriptions | Load existing source and field descriptions, allowed values, synonyms and derived-metric descriptions; associate them with their owning source |
| Decomposition drops formula operands | MC-024 retrieved scenario strings; MC-025 omitted action-gap operands | Preserve declared `required_fields` alongside branch identity and retain schema-valid operands through QuerySpec |
| A valid query changes retrieval meaning | WM-1T-005 adds reverse cash-flow edges to a type lookup, returning 7,437 rows; BSQ-1T-008 similarly expands the scenario lookup | Render supported single-source QuerySpecs directly; do not add undeclared sources |
| Filters are optional or syntactically malformed | WM-3T-005 puts its allocation filter inside OPTIONAL; four failures include invalid numeric datatype syntax | Render typed literals and filters outside OPTIONAL; validate the rendered structure before scanning |
| Wrong metric/grain | MC-046 uses mean allocation for concentration; MC-068/083 sum shortfalls; many comparisons report group totals | Carry calculation notes and actual field metadata into FinalSpec; distinguish inner and outer aggregates explicitly |
| Different populations are compared | MC-054 uses left joins for every fact; MC-024's V9 diagnostic also exposes this | Explain required fact participation separately from nullable labels; record assumptions and actual join counts. This remains a model interpretation risk |
| Nullable labels are dropped or split | MC-043/044 lose null labels; MC-042/047/049 split null summaries | Prefer the owner's direct display attribute; explain label attachment before grouping and explicit null-safe joins between comparable group summaries |
| Label ownership becomes ambiguous | MC-076 groups on an investor label; MC-086 groups cash metrics on cash-flow type | Supply source descriptions and column ownership; retain explicit join keys and recommend aliases before joins |
| Conditional totals lose entities or reverse signs | MC-007/086/100 | Add a small interpreted `where` expression with comparisons, boolean logic and explicit null tests; preserve groups with no qualifying conditional rows |
| Null checks silently erase calculated values | First V9 live diagnostic used `value != null` inside formulas, producing all-null changes | Reject null comparisons during expression validation; use `is_null`/`is_not_null` or direct null-propagating arithmetic |
| Buckets lack an ELSE case | Missing/null inputs cannot receive a declared fallback; string `false` was treated as true | Add `default`, validate boundaries/boolean flags and preserve first-match semantics, including null labels |
| Debug samples hide multiplicity | Only three sampled rows and compact logs were available | Compute full-scan column statistics; log join key multiplicity, matches, unmatched rows, input/output sizes and per-step null counts |
| Copied launcher runs the wrong package | Root `run.py` imported V7 | Import V9, use V9 report/version defaults and provide a timestamped subset launcher |

No additional model stage was introduced. Processing remains a pass-through;
FinalSpec remains the one calculation planner. Existing join/cardinality checks
and bounded repairs are reused. Declared fields and assumptions are not an oracle
for question meaning: an incorrect declaration can still produce an incorrect plan.

For schemas without enough RDF binding metadata, the existing model Generate
fallback remains. Its structural checks are weaker than the canonical rendering
path; V9 does not claim exhaustive semantic validation of arbitrary SPARQL.

## Validation actually performed

**184 offline tests pass**, including the inherited suite and 17 new regressions.
Tests cover complete-data key statistics, retained operands, source-owned
descriptions, conditional/null semantics, bucket defaults, unsafe expression
rejection, and real RDF query execution. Existing independent operator tests
also cover unequal observations, two-stage aggregation and required participants.
The old Generate test now checks the rendered connector query instead of requiring
an unnecessary model call.

Two live four-question diagnostic runs were performed. The first exposed the
discarded schema descriptions and invalid null comparisons; those were corrected
before the final run. A separate sandbox attempt failed with connection errors
and is preserved as `outputs/smoke_v9.csv`; it is not accuracy evidence.

The final run uses the configured GPT-OSS model and Fuseki database and completed
all four questions successfully. The run took about 165 seconds including setup.
Its [manifest](outputs/smoke_v9_final.csv.manifest.json) identifies the source and
local input files; it does not prove the live Fuseki graph is identical to the
local instance file.

Local answer verification uses reviewed column aliases, exact group coverage and
an absolute tolerance of 0.00500001 against two-decimal reference numbers:

| Question | V7 grade | Final V9 local check |
|---|---|---|
| MC-024 | MISMATCH | All groups and 4/12 requested numbers match. Scenario change is corrected; goal means still use a broader population |
| MC-025 | MISMATCH | All groups and 8/12 numbers match. Both differences are corrected; amount still averages action amounts rather than investor totals |
| MC-038 | MATCH | All groups and 18/18 requested numbers match. Two extra output metrics are still present |
| MC-068 | PARTIAL | All groups and 16/16 requested numbers match, including the previously wrong shortfall |

See [docs/smoke_comparison.json](docs/smoke_comparison.json) for every compared
value, alias and absolute error, and [the final debug report](outputs/smoke_v9_final_debug.csv)
for executed queries, assumptions, branch profiles and operator evidence.
These are **local diagnostic results**, not new external-grader MATCH labels or
an estimate of full-cohort accuracy. MC-025 also returns an extra investor count.

Automatic approval review blocked external grading because it would send the
questions, reference answers and pipeline outputs to an external endpoint without
explicit authorization. No external grade is claimed for V9.

## Remaining limitations

- The model can still select the wrong population, statistic or output fields.
  V9 reports these choices rather than silently rewriting them to match answers.
- Some benchmark wording omits required metrics or exact definitions: for example
  MC-009 also expects sector investment, and MC-011 expects a maximum-change metric.
  A general pipeline cannot recover every unstated requirement reliably.
- Source schema descriptions improve grounding but do not define every desired
  aggregation. The MC-025 amount definition remains one such mismatch.
- MATCH does not prove correct semantics. V7 MC-105 returns an empty answer while
  using maximum scenario change; empty results conceal that distinction.
- The five V7 OTHER grades include incomplete references. This change preserves
  the existing external grading criteria and does not restore truncated references.
- The four-question diagnostic is deliberately small. A full 192-row matched run
  is still needed to measure accuracy and regressions.

## Run V9

From the workspace root:

```powershell
& experiment_week1/improvement3/run_pipeline_v9/run_v9.ps1 -DryRun
& experiment_week1/improvement3/run_pipeline_v9/run_v9.ps1
```

The default subset is the 68 comparative-heavy part-2 questions. Reports are
timestamped under `run_pipeline_v9/outputs`. The launcher restores environment
settings when it exits. For the other cohorts:

```powershell
& experiment_week1/improvement3/run_pipeline_v9/run_v9.ps1 -Subset non_success_part1_69 -Limit 69
& experiment_week1/improvement3/run_pipeline_v9/run_v9.ps1 -Subset success_55 -Limit 55
```

Run offline verification with:

```powershell
python -m unittest discover -s experiment_week1/improvement3/run_pipeline_v9/tests
```

The nested `run_pipeline_v7` folder is a supplied copy and is not imported by the
V9 launcher. It was left untouched. Other copied review documents describe older
versions; this file describes the final V9 changes.
