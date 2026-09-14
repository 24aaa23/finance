# V8 comparative analysis and implementation

## Verified results

The saved results support the reported tradeoff. MATCH is the independent grader's
answer grade, not pipeline execution success.

| Fixed input subset | Rows | V5 MATCH | V6 MATCH | V5 execution failures | V6 execution failures |
|---|---:|---:|---:|---:|---:|
| Prior success | 55 | 27 | 33 | 4 | 0 |
| Non-success part 1 | 69 | 23 | 27 | 3 | 1 |
| Non-success part 2 | 68 | 5 | 2 | 24 | 4 |
| Total | 192 | 55 | 62 | 31 | 5 |

All 68 part-2 questions belong to the MC source family. The full 192-row cohort
contains 76 MC questions: 7 MATCH in V5 versus 4 in V6. Part 1 contains only five
MC questions and retains two MC matches in both versions. Its overall improvement
therefore does not establish improved multi-step comparative accuracy.

The audit verifies identical IDs, question text and ground-truth text against the
442-row workbook. All six completed report manifests match their current V5/V6
Python sources. An older V5 success manifest without a corresponding completed
report also exists; it is excluded. Comparing that abandoned manifest would wrongly
suggest source drift for the completed success run.

Source evidence is in [docs/v5_v6_transitions.csv](docs/v5_v6_transitions.csv) and
[docs/v5_v6_evidence.json](docs/v5_v6_evidence.json). The latter retains each saved
plan, contract, grade, answer and reference SQL. Regenerate with:

```powershell
python experiment_week1/improvement3/run_pipeline_v8/docs/audit_v5_v6.py
```

## Why the three matches were lost

V5's five part-2 matches were MC-028, MC-043, MC-044, MC-068 and MC-105. V6 retained
MC-028 and MC-105 and gained no new MATCH in that subset.

| Question | V5 plan | V6 divergence | Saved V6 grade |
|---|---|---|---|
| MC-043 | AVG progress per investor; join health/profile; AVG those values by profile segment | AVG raw goals by segment; separate health population; inner label join drops the null segment | PARTIAL |
| MC-044 | SUM(currentValue-cost) per investor; compare by Investor.segment | AVG individual holding gains by holding.hasSegment; omits Investor; inner Segment lookup drops null group | MISMATCH |
| MC-068 | AVG shortfall and MAX allocation per investor; join health/profile; outer AVG by time horizon | AVG raw shortfalls and raw allocationPct by time horizon; separately merged group populations; null group disappears | PARTIAL |

MC-043's numeric drift fits the grader's tolerance in this run, but unequal numbers
of goals per investor make raw AVG and AVG(per-investor AVG) different estimands.
MC-044 changes both the metric and the grouping attribute. MC-068 changes weighting,
the concentration operator, and population construction.

MC-105 is an empty-result MATCH in both versions. Its V6 plan filters individual
scenario changes above 20 rather than averaging scenario change per investor and
then filtering. It also returns cash amount without the reference net-flow SUM.
An empty MATCH therefore does not certify the intended calculation. It needs a
nonempty synthetic witness when its rule-based planning is addressed.

## Why V6 helped part 1 but hurt part 2

V6 changed several components together: deterministic rendering of supported raw
QuerySpecs, simpler Decompose/FinalSpec prompts, and removal of the V5 semantic
contract normalizer and runtime checks. These runs are not an ablation, so they
cannot isolate the numerical effect of a single change.

Part 1 has eight gained matches and four lost matches. Five gains restore missing
null groups (WM-1T-012, WM-3T-008, WM-3T-009, BSQ-2T-004, TT-042); WM-1T-020 restores
monthly cash-flow results; TT-053 and TT-061 correct overbroad investor membership.
The four losses are WM-4T-003, WM-4T-008, BSQ-2T-003 and BSQ-3T-006.

Part 2 drops from 16 FinalSpec failures in V5 to one in V6, but MISMATCH rises from
13 to 31. V5 often enforced a speculative global source key and display-field name:
MC-008 required investorId on the wrong branch; MC-012/018/029/032/037 and others
failed because the plan grouped by rdfs_label while the contract named a semantic
display alias. Removing these checks made more plans executable, while also
removing guidance/checks for the useful per-investor calculations.

V5's checker also tracked a global 'summarized' flag per branch. A summary on one
path could incorrectly certify a different raw path. It did not reliably prove
the inner operation or metric-specific lineage. Reinstating that checker verbatim
would reproduce avoidable failures without proving answer semantics.

## What the ground-truth SQL establishes

The authoritative workbook is
`../../improvement2/dataset/verification_results_v2_sql_correct_442.xlsx`, sheet
`SQL_Correct_442`. It includes `sql_query`, `sql_verdict`, `sql_reason` and
`ground_truth_answer`. These establish the reference calculation; no question
generation script was located in the targeted source search, so this review does
not claim to reconstruct the original authoring process.

The observed multi-step SQL patterns are:

| Metric family | Inner calculation | Later calculation/population |
|---|---|---|
| Holdings | SUM(current_value), SUM(current_value-cost); AVG(returns_pct) where requested | Join by investor, then requested profile-level aggregate |
| Goals | AVG(progress_pct), AVG(shortfall), other requested goal measures by investor | AVG of investor summaries for the relevant grouped comparisons |
| Allocation concentration | MAX(allocation_pct) by investor | AVG of investor maxima for the relevant grouped comparisons |
| Health | Risk/liquidity/diversification at investor level; reference SQL reasons describe health as 1:1 | Join required investors before outer comparison |
| Cash/scenario | Per-investor CTEs; formulas and filter scopes vary with metric | Follow the specific definition, not a universal sign or concentration formula |

The important sequence for MC-043/044/068 is **source calculation → investor
summary → required participant joins → profile grouping → outer calculation**.
Missing profile labels remain a null group. Missing metric values are ignored by
their own aggregate, rather than dropping the entire investor from every metric.
An inner join between required fact summaries is different from an inner join to
an optional label dictionary.

Two-table dimension/fact comparisons may use raw observation averages. A blanket
'always aggregate by investor' rule is wrong for them. The SQL also contains
definitions absent from vague question wording: 'compare' alone does not specify
SUM versus AVG, weighting, participation, or every band boundary. Those definitions
need explicit dataset documentation or question clarification for a fully
unambiguous benchmark. V8 records assumptions; it does not read SQL or expected
answers during inference.

## Changes implemented only inside V8

The supplied V8 directory was not byte-identical to V5 when inspected: it already
had connector/schema repair changes, revised prompts, and a V7 launcher. Those
existing changes were preserved. V5/V6, datasets, saved outputs and the V4 review
directory were not edited.

1. **Preserve comparison intent through decomposition.** Non-executable
   `comparison_notes` retain metric ownership, weighting, population and filter
   scope. Profile attributes are distinguished from similarly named fact fields;
   the question's SQL table count is not a hard limit on RDF connector classes.
2. **Resolve the executable contract at FinalSpec.** A compact `comparative_contract`
   uses actual retrieved IDs/columns, a separate grain per metric, requested inner
   and outer operations, source operands, dimension provenance and required
   population. Ambiguous choices remain visible in `assumptions`.
3. **Validate the actual metric path.** The compiler tracks column-specific
   aggregate/expression provenance through aliases and join suffixes. It rejects
   a wrong inner/outer operation, wrong source/dimension, omitted projection,
   a sibling summary substituted for the actual metric path, aggregation after
   joining another metric source, and outer averaging before required participation.
   A left join alone cannot establish participation in a required source.
4. **Keep scope narrow.** Contract emission is mandatory for the existing
   'Across … compare … three/four/five related tables' template: 56 of the 76 MC
   questions. Ordinary questions and two-table comparisons retain the existing
   calculation path. A supplied contract is still validated for other wording.
   Rule-based/ranked multi-step questions outside that template are not claimed
   to be solved by this iteration.
5. **Repair without deleting requirements.** The caller makes the contract
   mandatory on every applicable retry. Missing-source requests still route to
   retrieval. Existing bounded repair feedback includes failed plans and schemas.
6. **Make V8 runnable as V8.** `run.py` imports `run_pipeline_v8.main`; version,
   manifest tag and default output names identify V8. Default input is part 2.
   The subset launcher creates timestamped reports under V8/outputs and restores
   process environment settings afterward. The copied grader accepts explicit
   `--raw-report` and `--graded-report` paths with V8 defaults; its grading criteria
   are unchanged.

The runtime is domain-independent: no MC IDs, ground-truth SQL, answer values,
per-question lookup table or hidden workbook access is introduced into inference.

## Validation and practical limits

Verified: **186 offline tests pass** (167 inherited and 19 new). All three subset
launchers pass their path-validation dry runs. Authentication-error messages in
the test output are mocked grader fixtures, not live authentication attempts.

Run the offline suite:

```powershell
python -m unittest discover -s experiment_week1/improvement3/run_pipeline_v8/tests
```

The new tests compare actual operator execution with independent SQLite on unequal
fact counts, null groups and missing participants. They also exercise wrong inner
and outer operations, MAX versus AVG, source/dimension ownership, omitted metrics,
separate populations, aliases, sibling-summary bypass, cardinality against actual
rows, malformed contracts, idempotent recompilation and missing-source repair.

This is structural validation of the planner's declared interpretation, not an
oracle for the question's meaning. A consistently wrong model declaration can
still pass. Operand provenance does not prove arbitrary algebraic equivalence;
nullable retrieval/label joins and filter fidelity are not exhaustively checked by
this new module. A required contract adds a possible repair/failure point; a fresh
run must measure whether it improves accuracy without recreating V5's failure rate.

No new model, Fuseki, or grading run was performed during implementation. Saved
debug files contain samples rather than all raw rows. The work therefore does not
claim new V8 MATCH counts or numerical replay of the entire source database.

## Run and evaluate

From the workspace root, first check the resolved paths without model calls:

```powershell
& experiment_week1/improvement3/run_pipeline_v8/scripts/run_v8.ps1 -DryRun
```

Then run part 2 (default), followed by the regression cohorts:

```powershell
& experiment_week1/improvement3/run_pipeline_v8/scripts/run_v8.ps1
& experiment_week1/improvement3/run_pipeline_v8/scripts/run_v8.ps1 -Subset non_success_part1_69
& experiment_week1/improvement3/run_pipeline_v8/scripts/run_v8.ps1 -Subset success_55
```

`-Limit 5` provides a small smoke run; it is not a substitute for the complete
cohort. Use the printed timestamped report path for grading:

```powershell
python experiment_week1/improvement3/run_pipeline_v8/grade_final_answers.py --raw-report "<printed V8 report path>" --graded-report "<V8 outputs destination.csv>" --dry-run
```

Remove `--dry-run` to grade. Keep model settings, graph snapshot and grader criteria
fixed. Report all 192 transitions, the 76-question MC family, the 56-question
contract subset, execution failures and assumptions separately. Inspect the three
lost matches and MC-105's semantics even if their grader labels improve. Do not
claim V6's part-1 gains have been retained until the matched run demonstrates it.
