# Improvement5 V3 Changes

Date: 2026-09-27. Baseline: the existing copied v2 pipeline. V2 and its results are preserved.

## Failure Grading Update (2026-09-28)

At the user's request, `grade_final_answers.py` now counts pipeline execution
failures as `MISMATCH` instead of `SKIPPED_EXECUTION_FAILURE`. These questions
remain in end-to-end accuracy totals. Their original execution status and error
text are preserved, and the reason explicitly states that no successful answer
was produced and no model comparison was performed. The grading path is
`execution_failure_as_mismatch`.

The general NULL policy and model grading of successful answers are unchanged.
Failed rows are classified before resume lookup. Rerunning the same grader
command replaces old skipped labels and reuses unchanged successful grades under
the same model and policy. A failed question that later executes successfully
receives a fresh model grade. Grader API errors/pending grades retain their
separate statuses and retry behavior.

This update does not repair an answer or change raw pipeline reports. Existing
saved graded reports change only when the grader is rerun. Tests cover preserved
errors, conversion of legacy skips, reuse of successful grades and grading after
execution recovery. `README.md` documents this reporting policy.

Verification: all 20 grader tests passed, including two new resume/recovery
regressions and expanded failure coverage. Python compilation passed. No live
grading calls were made and existing graded CSVs were not rewritten.

## Execution Failure Fixes (2026-09-28)

The completed MC run recorded 55 execution failures out of 105 questions. The
v3 grader originally skipped those failed rows. Changing the grade label would
not repair their missing answers, so these changes address pipeline planning
and execution. That pipeline fix left the grader and saved CSVs unchanged; the
later failure-grading update above changes the grader's reporting policy.

### What Was Fixed

- **Invalid `None` source check:** component-based metrics already declare each
  real source and its inner aggregation. The checker now uses those components
  without also demanding an aggregation on `None.investorId`. Component operands,
  source identity, entity grain and the requested outer aggregation remain checked.
  The outer aggregate cannot also satisfy a required inner aggregation.
- **Invalid metric contracts:** unknown sources/fields, missing component sources,
  source-less raw operands, invalid aggregation names and group owners without a
  retrieved source return to Decompose for repair. Legacy output-only metadata
  remains supported. Standard mean/average aliases use the same AVG check.
- **Wrong grouping owner:** prompts distinguish the source of a group attribute
  or derived band from the entity owning the records. Explicit contract conflicts
  go back to Decompose. Persistent semantic errors also return there after the
  existing four Final_Spec attempts. The outer decomposition budget remains three
  attempts, and its repair prompt now includes the previous decomposition.
- **Branch source drift:** Query_Spec sees the active source's schema and an output
  example containing its actual assigned source and branch ID. Full schema checks
  still validate connections. Required branch fields and source changes remain
  checked; the code does not silently substitute another source.
- **Metric cases incorrectly used as scan filters:** disjoint conjunctive IN
  conditions now trigger repair. Prompts place separate metric cases/bands in
  final calculations or separate branches, preserving the common population.
  No AND is silently rewritten as OR.
- **Executable plan formats:** explicit filters tolerate an empty `aggregations`
  list; same-key multi-input joins normalize to the existing sequential join;
  `Copy` projects declared columns while preserving rows, duplicates, NULLs and
  lineage. Unknown columns, conflicting keys, different-key multi-input joins,
  invalid aggregates and cardinality violations remain errors.

These are general schema/contract fixes. No question IDs, category rules, expected
answers or hardcoded result values were added to pipeline logic.

### Files And Verification

Production changes are in `semantic_contracts.py`, `llm_operators/decompose.py`,
`llm_operators/query_spec.py`, `llm_operators/final_spec.py`, `main.py`, `executor.py`,
`spec_contracts.py`, `spec_runtime.py` and `execution.py`.
Regressions are in `tests/test_v3_failure_repairs.py` and
`tests/test_repair_feedback.py`; `OPERATOR_USAGE.md` reflects the new repair routes.

Read-only replay of saved MC-033, MC-051 and MC-078 declarations confirms their
specific compiler errors are resolved. MC-010's saved plan passes the source/grain
checks using column-only metadata reconstructed from its saved retrievals. This
limited replay does not verify live RDF identity metadata or final answer accuracy.
Independent synthetic-data tests cover calculated values and continued rejection
of incorrect plans.

Verification passed: all 229 offline tests, including 19 new regressions; Python
compilation of all nine changed production modules; and the MC ten-question CLI
dry run. The full suite also checks all nine category launchers without API calls.

### Running Again

Old error rows do not change automatically. Run the corrected pipeline to create
new timestamped reports, then grade those new reports. From `improvement5`, a small
first run is:

```cmd
python run_pipeline_v3\run.py MC --limit 10
```

Omit `--limit 10` for the full category. Results go to `pipeline_output_v3`.
The source fingerprint changes with these fixes, so old runs cannot be silently
resumed as if produced by the corrected code.

No paid model calls or full dataset rerun were performed for this fix. Connection
errors still depend on the external service/network; the existing SDK retry budget
is retained. No new match percentage or guarantee of zero execution failures is
claimed before a fresh run and grading.

## What Changed In Easy Language

| Problem seen in v2 | V3 change |
|---|---|
| A branch requested Short-term AND Medium-term on the same value | Detect contradictory equalities and request a repair. Comparisons use IN or separate branches; genuine AND is not silently changed to OR. |
| `month != null` removed all rows without an execution error | Reject the filter before execution and request `is_not_null` / `is_null`. Runtime SQL-like NULL behavior is unchanged. |
| Averages were pooled across rows instead of calculated per investor first | Carry source, operand, inner/outer aggregation and entity-grain contracts through planning; check final column lineage against them. |
| The final plan joined unrelated action and decision identities | Track schema identity targets through grouping, copies and join suffixes; reject proven target-type mismatches. |
| Missing labels were confused with missing scores | Declare label keep/exclude policy and check exclusions before ranking. Preserve legitimate NULL groups by default. |
| Bands and composite definitions were missing from the pack | Add the three goal-match bands, R8.0 terms and R8.2 population/normalization rules. |
| Execution success was the only check enabled | Enable final semantic review and one bounded calculation repair. Keep a replacement only if execution and review pass. |
| Changing rule JSON could reuse stale results | Include the actual business-rule pack in the run identity, including custom packs. |
| Copied v3 launcher still imported v2 | Import v3, use a v3 label and separate `pipeline_output_v3` paths. |
| Default limit was 100 | Default to all rows; add simple category commands and optional `--limit`, `--offset`, `--workers`, `--dry-run`. |

## Files Changed

- `semantic_contracts.py`: contradiction, column-origin, aggregate-lineage,
  identity-target and declared NULL-label checks.
- `llm_operators/decompose.py`: structured metric requirements; retain operands
  and entity keys in branches; reject impossible conjunctions.
- `llm_operators/query_spec.py`: preserve the full shared contract; check raw filters.
- `llm_operators/final_spec.py`: use the full contract and validate final lineage;
  improve instructions for source/grain, ratios, bands and optional label joins.
- `spec_runtime.py`: reject invalid NULL comparisons and contradictory filters.
- `llm_operators/validate.py`, `executor.py`: default review, explicit repair hints,
  bounded final-plan repair, original/candidate evidence in repair logs.
- `llm_operators/query_spec_validate.py`: synchronize the inactive/manual critic
  with the rule pack; do not add another critic to every branch.
- `business_rule_pack.json`: bands, component definitions, normalization and NULL
  group-label policy. Original business-rule/domain source documents are unchanged.
- `main.py`, `common.py`, `run.py`, `run_identity.py`: v3 paths/import/version,
  all-row default, short category CLI and pack/configuration provenance.
- `scripts/*_v3.ps1`: renamed runners, v3 output/pack selection, enabled review,
  no-write dry run, and quoted Fuseki background arguments containing spaces.
  The legacy subset launcher `run_v9.ps1` also targets v3 outputs/version now.
- Tests: new offline regressions and updated review-repair expectations.

## Follow-Up Consistency Fixes

- `COUNT(*)` now retains input-source provenance, so a valid per-investor row
  count followed by a cohort average is not incorrectly rejected as missing its source.
- Label presence established by an explicit raw retrieval filter is recognized.
  An OR condition is not incorrectly treated as a guarantee of a non-null label.
- Left and right joins preserve the non-null guarantees on their preserved side,
  while allowing missing values on the optional side. This avoids unnecessary repairs
  of a valid label filter applied before the join.
- Malformed metric operands, component lists, entity keys and NULL-label policies
  generate explicit contract errors. Final_Spec routes malformed requirements back
  to Decompose before making another planning model call.

## Important Boundaries

1. Metric checks verify plans against declared contracts, not hidden ground truth.
   A wrongly understood contract can still need review. Formula direction, ratio
   meaning, optional populations and ambiguous wording are not symbolically proven;
   the model still plans these calculations.
2. NULL groups are not automatically errors. V3's `grade_final_answers.py` applies
   the same question/reference-based NULL instructions to every category. It does
   not drop NULL labels based on category names or question IDs. The shared root
   grader retains its older MC_diverse-only policy; use the v3 grader for v3 results.
3. Compilation errors requiring new sources use the existing upstream repair route.
   A semantic review requiring new sources stays visibly rejected; automatic
   review-driven repair only changes calculations on already retrieved rows.
4. Rejected, unavailable or failed repairs do not replace the original answer.
   Original rows, verdict and candidate evidence are retained. An unconfirmed
   replacement is never reported as accepted.
5. `PIPELINE_SUCCESS` means execution completed. Use review status and the separate
   grader before claiming a match-percentage improvement.
6. R8.2 requires a constant-component guard but does not define an alternate score.
   V3 uses NULL for a zero normalization denominator, producing a NULL index;
   it does not invent zero or average fewer components. This is explicitly an
   implementation assumption, not an additional expert-approved rule.
7. Audited TT references can conflict with R5/R6 weighting/population rules, including
   TT-043 and unresolved weighting in TT-059. Reference answers were not edited or
   used to overfit the implementation.

## General Grader NULL Policy (2026-09-28)

The v3 grader is `run_pipeline_v3/grade_final_answers.py`. Its prompt now uses
one policy, `general_null_semantics_v1`, for all nine categories. No category,
filename, question-ID test, or list of allowed group-column names selects a rule.
The model judges the question, reference answer and final pipeline answer.

The existing v2 graded CSVs show three different cases:

- MC-212: required named groups and values match, with an additional NULL label.
  An extra unnamed group can be harmless only if every requested result, ordering,
  population, total and denominator remains correct. A changed rank position,
  winner or top/bottom result is still an error.
- TT-002/TT-003: the reference includes an unnamed group that the answer omits.
  Missing that group still reduces the grade.
- MC-004: the answer uses NULL for required zero inflow/outflow values.
  A missing metric is not the same as a zero and is still graded accordingly.

The change only adds general NULL instructions to the existing grading prompt.
It does not remove rows, replace values, normalize literal text labels to NULL,
automatically promote a result to MATCH, or add a second model call. Existing
numeric tolerance and other grading criteria remain unchanged. A harmless extra
group is an evidence-based model decision, not a guaranteed score increase.

Each output records `Grading Policy`; resume reuses grades only when input, model
and policy match. Old or unversioned grades are evaluated again. Default report/log
paths now point to `pipeline_output_v3`; specify the timestamped raw input and
graded destination explicitly as shown in README.

The shared root grader, v2 grader/results, v3 pipeline generation and existing
raw outputs were not changed. Use the v3-local grader to get the general policy.
Offline regressions cover identical requests across all nine category/file names,
unmodified input answers, unchanged model verdicts, and policy-aware resume.
These mocked tests verify wiring and preservation, not live model accuracy.
Verification passed: 18 grader tests, Python compilation, and CLI dry runs on
all nine saved v3 result CSVs with destinations under `pipeline_output_v3/graded`.
No paid grading run or new match percentage is part of this change.

## Documentation Cleanup

Only three Markdown files remain in v3: `README.md`, `VERSION_CHANGES.md`, and
the rewritten `OPERATOR_USAGE.md`.

Removed copied historical reports: BUSINESS_RULE_PACK_INTEGRATION, CHANGES_AND_REASONING,
COMPARATIVE_CHECK, FINAL_REVIEW, GRADER_NULL_POLICY_AND_PIPELINE_PLAN, MC_MC_DIVERSE_TT_AUDIT,
V9_REVIEW and docs/completed_run_audit/FINDINGS. The old `prompt.md` was an unused
v4 brainstorming note, not a runtime prompt; it was also removed. Python prompts
and the business JSON remain. All original v2 documents remain available, including
[the audit](../run_pipeline_v2/MC_MC_DIVERSE_TT_AUDIT.md).

Copied non-Markdown audit artifacts and historical outputs were not deleted;
they must not be interpreted as newly generated v3 results.

## Verification

- Offline v3 suite: 207 tests passed, including 23 new regression tests.
- Shared MC_diverse NULL grader suite: all 25 existing tests passed.
- All nine simple commands passed `--dry-run`: correct input, v3 output, all rows.
- PowerShell all-nine runner dry-run passed; all PowerShell scripts parsed successfully.
- Python compilation passed. Failed-repair rollback and accepted-repair execution
  are covered offline, without additional Fuseki scans.
- No paid model calls, live dataset run, live Fuseki startup or regrading was performed.
  No new accuracy or match percentages are claimed.

Start with small MC, MC_diverse and TT samples and grade their new outputs before
running the full comparison. See README for commands.
