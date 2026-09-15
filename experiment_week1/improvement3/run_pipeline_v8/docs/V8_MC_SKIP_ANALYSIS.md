# V8 MC skips: completed-run diagnosis

This review analyzes the three saved V8 raw/debug/graded reports in
`../../pipelien_output`. All three manifests match the current V8 production
sources. Only review documents and the offline audit script were added during
this review; inference behavior and historical grades were not changed.

## Result: the hard contract made V8 too brittle

| Part 2: same 68 MC questions | V5 | V6 | V8 |
|---|---:|---:|---:|
| MATCH | 5 | 2 | 3 |
| PARTIAL | 26 | 31 | 17 |
| MISMATCH | 13 | 31 | 10 |
| Skipped execution failures | 24 | 4 | 38 |

V8's three matches are MC-020, MC-028 and MC-105. The previously lost V5 matches
MC-043, MC-044 and MC-068 are now skipped. MC-105 remains an empty-answer match,
which is not proof of correct rule semantics.

Across all 76 MC questions in the three cohorts: 5 MATCH, 17 PARTIAL, 16 MISMATCH,
38 skipped. The extra eight MC questions outside part 2 contribute two matches
and six mismatches, with no skips.

The 38 skips are **37 FinalSpec failures plus one decomposition failure**. These
are upstream inference failures, not grader refusals or grading API failures.
For the 37 FinalSpec failures:

* 34 have only `comparative_contract:` errors.
* Three have executable-plan defects: MC-051, MC-061 and MC-093.

Offline recompilation of the exact saved plans with only the comparative contract
removed passes the ordinary compiler for all 34 contract-only cases. This is a
compilation diagnostic, not execution on the graph and not 34 recovered matches.
Several of these plans plainly disagree with the reference calculation.

## The major failure families

Counts below overlap; a question can have several errors.

| Reported problem | Skipped questions | Interpretation |
|---|---:|---|
| Required population is not established before metric aggregation | 22 | Often a real separate-population/left-join planning error; the contract can also overstate eligibility by listing every retrieved label source |
| `outer_aggregate: none` is rejected | 11 | The model and contract interface disagree on the meaning of one-level versus two-level metrics; allowing none blindly would also admit wrong calculations |
| Source-column provenance mismatch | 6 | Includes row-count notation problems, plus cases needing semantic review |
| Contract uses class names instead of runtime dataset IDs | 3 | MC-026, MC-038, MC-048; the executable plan normalizes aliases but the contract does not |
| Missing contract after repairs | 1 | MC-054 |
| Ordinary executable-plan errors | 3 | MC-051: missing inputs/fields and empty aggregations; MC-061: compiler-generated name collisions and missing fields; MC-093: nonexistent suffixed label fields |
| Decomposition uses invalid schema class spellings | 1 | MC-098: `Cash Flow`, `Rebalancing Action`, `Scenario Rebalancing`, `Portfolio Health` instead of catalogue names |

The full per-question list and final errors are in
[v8_mc_skip_review.csv](v8_mc_skip_review.csv).

## Specific design problems demonstrated by the run

### 1. Missing metadata triggers a complete plan rewrite

The first visible repair errors mention a missing comparative contract for **39
of the 76 MC questions**, including **24 of the 38 skipped questions**. These
counts use the first saved repair record, not a claim about all attempts.

FinalSpec inserts the comparative-contract instructions and then says:

`Use this single format: {"final_steps": [], "projection": [...]}`

Its long worked example also omits the comparative contract. This gives the model
inconsistent output examples. The observed omissions are consistent with that
prompt defect, although a prompt ablation would be needed to isolate its effect.

The current repair then requests the complete corrected plan. It does not preserve
valid calculation steps when only metadata is missing. MC-043 illustrates why
this matters:

* First saved attempt: AVG goal progress per investor; health summaries per
  investor; join profile/metrics; outer AVG by segment. Its only visible rejection
  was the missing contract. That structure agrees with the reference pattern,
  although no full-data execution of this attempt was performed in this review.
* Last saved attempt: AVG raw goals by segment; separate health aggregation;
  inner join the segment summaries. Its contract says `outer_aggregate: none`.
  The plan is now semantically worse and still rejected.

MC-044 and MC-068 also first fail for missing metadata, but their first plans
already contain semantic errors. They must not be treated as recoverable merely
by adding a contract.

### 2. The contract aliases are not normalized like plan inputs

MC-026's steps use actual IDs such as `q_cash_processed` and `q_scen_processed`.
Its contract instead uses `CashFlow` and `ScenarioRebalancing`. The validator
reports nonexistent source tables, even though those sources have already been
retrieved and the steps use them.

Resolve a class/branch alias only when exactly one available dataset owns it,
using the same mapping for plan inputs, contract dimensions, metric sources and
required populations. Never guess when two branches read the same class. Fixing
these names alone does not validate MC-026's SUM-versus-AVG choices or population.

### 3. Row count is incorrectly treated as a value-column dependency

MC-042 executes `count_rows(*)` per investor, then sums those counts. Its contract
lists `subject_iri` as the source column, which describes the counted records.
The checker represents the operation with a `*` dependency and rejects the mismatch.

In an offline copy of that saved plan, changing only the count metric's contract
`source_columns` to `["*"]` removes the final compiler error. No executable step
changes. This isolates an interface/validation limitation, not a mathematical fix.
MC-042's other SUM-based business definitions still need comparison with reference SQL.

The durable fix is explicit row-count lineage tied to a source relation/grain.
Keep COUNT(*), COUNT(nullable_column), and COUNT(DISTINCT column) distinct.

### 4. Population errors are not all false alarms

MC-068 aggregates goals, allocations and health independently by time horizon,
then joins the group summaries. Its contract requests investors participating in
all three sources. The actual metric populations need not be the same. It also
uses raw goal shortfalls rather than per-investor goal averages. Removing the
contract does not fix either issue.

MC-058 declares required goals, allocations and health but left-joins all three
onto investors. It also averages allocation percentages where the relevant
reference uses per-investor MAX. Relaxing the population check would hide a real
problem and would not repair concentration.

The representation should distinguish required fact participation, preserved
base entities and optional display dictionaries. Changing every join to inner
would lose null groups; changing every join to left would change eligibility.

### 5. Repeated retries lack focused feedback and complete saved evidence

FinalSpec has up to four attempts per invocation, each regenerating the entire
plan. Error strings do not always tell the model which required source is missing
from the specific metric path, or distinguish metadata repair from calculation repair.

**57 of 76 MC repair-log cells are truncated.** The final specs and first visible
records permit the findings above, but complete attempt-by-attempt reconstruction
is not possible from these cells. Save full repair records as JSON artifacts and
put paths/hashes in the CSV rather than embedding repeated large specs in a capped cell.

## Recommended repair order

1. **Fix the response and repair interface first.** Supply one authoritative
   response shape that includes the contract, including the worked example.
   Specify allowed outer aggregates explicitly. Require the contract on the first
   response, but when it is missing, request metadata for the existing plan while
   preserving the plan. If the existing calculation is wrong, repair that separately.
   Do not construct a contract from the plan and treat it as independent evidence
   that the question has been answered correctly.
2. **Fix deterministic normalization and validator limitations.** Resolve only
   unambiguous source aliases, represent row counts properly, and report missing
   population members with the responsible metric and step. Keep invalid fields,
   wrong operators and proven grain mismatches as hard failures. Retain unresolved
   interpretation issues as separately reported review status; any diagnostic
   execution of such a plan must not be labeled verified success.
3. **Repair calculation semantics before rerunning all questions.** For the
   reference-backed grouped comparisons, explicitly resolve metric definitions,
   per-source entity keys, required participants and profile attribute ownership.
   Then construct the per-entity summaries and joins from that resolved description.
   MC-043 needs its original two-level shape preserved; MC-044 needs the holding's
   investor connector retrieved and profile segment used; MC-068 needs per-investor
   goal AVG, allocation MAX, a shared required population and preserved null groups.
   Do not insert question IDs, expected values or reference SQL into inference.
4. **Fix the four non-contract blockers separately.** Repair MC-051's unavailable
   inputs/columns; stop emitting reserved `__spec_step_*` names for MC-061;
   track actual suffixes for MC-093; normalize uniquely matching catalogue spellings
   or constrain class selection for MC-098.
5. **Run a focused diagnostic cohort, then all 68.** Start with MC-026, MC-042,
   MC-043, MC-044, MC-051, MC-058, MC-061, MC-068, MC-093 and MC-098. Include synthetic
   unequal-record and missing-participant fixtures, and compare saved first/last
   attempts. Measure execution completion and answer grade separately. After the
   focused run, rerun the fixed 68 and the other 124 regression questions.

Increasing retries or removing every comparative check is not the recommended
fix. The former repeats an unstable process; the latter is likely to exchange
skips for PARTIAL/MISMATCH. The earlier 186 passing offline tests established
behavior on supplied fixture contracts; they did not establish reliable model
contract emission or cover these saved-run interface failures.

## Reproduction and limits

```powershell
python experiment_week1/improvement3/run_pipeline_v8/docs/audit_v8_skips.py
```

This regenerates [v8_skip_evidence.json](v8_skip_evidence.json) and the per-question
CSV. It imports the actual compiler using the offline test loader, reads saved
reports, checks source manifests, extracts available first-attempt evidence and
performs compilation-only counterfactuals. It makes no API or Fuseki calls, does
not execute against complete source rows, does not regrade, and does not change
production code. No recovered MATCH count is claimed.
