# Comparative-only check — 13 September 2026

The current operators can execute the tested multi-step calculations correctly.
This does **not** establish that GPT-OSS chooses correct retrievals and plans for
all comparative questions. The saved run demonstrates substantial planning errors.

## Evidence from the saved run

The three `v4_simple*_debug.csv` files contain 76 comparative questions, matching
the comparative subset of the supplied 442-question workbook. The source name
contains `105_questions`; this checked subset contains 76, not 105.

| Saved outcome | Cases |
| --- | ---: |
| Graded MATCH | 1 |
| Graded PARTIAL | 5 |
| Graded MISMATCH | 33 |
| Execution failed; grading skipped | 37 |

These are historical results, before the latest source changes. They are not a
new score for the edited pipeline.

Recompiling and executing the retained V4 comparative plans with today's code:

| Local replay outcome | Cases |
| --- | ---: |
| Executed on saved branch samples | 39 |
| No saved calculation plan to replay | 35 |
| Compilation error | 2 |

Of the 39 sample executions, 22 return no rows. Independently sampled branches
can lack overlapping entities, so this is neither proof of a broken join nor
evidence of a correct answer. Replay does not retrieve full data or regenerate plans.

The two compilation errors remain legitimate failures: MC-011 uses SQL
`cast(... as float)` inside the arithmetic expression language; MC-047 has a
malformed steps value and unavailable projected fields. The documented arithmetic
form already supports subtraction of numeric columns without SQL casts.

## What is verified in the current engine

`tests/test_comparative_steps.py` now has seven passing tests: six compare output
against independently executed SQLite queries, and one checks the final planner's
branch and connection context. They cover:

- Summarize each fact table, join summaries, then group across entities, with
  unequal fact counts that expose multiplication of rows and wrong weighting.
- Keep both entity and category keys in a two-key summary.
- Calculate a score after joining summaries, then sort and limit.
- Calculate paired differences before averaging, including independently missing inputs.
- Preserve MAX versus AVG in separate summaries before a group comparison.
- Preserve entities with only negative, positive, zero, or missing cash amounts
  when computing separate signed totals. Existing arithmetic can express this;
  arbitrary SQL CASE syntax is not supported.
- Pass branch responsibilities and declared connections to the final planner.

The entire local suite passes: **151 tests**. No external model was called.

## Why all comparative answers are still not guaranteed

1. **Selecting the correct source.** In the historical plans, 53 of 65 questions
   whose reference SQL uses Investor profile have no Investor branch. This is a
   structural warning, not a proof that every such join is necessary. MC-006 is
   a concrete error: grouping by a holding's category is different from grouping
   by the investor profile's category. More arithmetic operators cannot fix it.
2. **Connecting the same entity.** MC-035's saved plan joins Category subject IRIs
   to Investor IRIs. It compiles but cannot make the intended population. Current
   connection checks retain and type-check declared retrieval keys; they do not
   discover every missing bridge or prove every newly generated final join.
3. **Choosing the intended reduction and population.** MC-068's reference uses
   per-investor MAX allocation and inner joins; the saved plan uses AVG allocation
   and left joins. Both versions are executable, but answer different questions.
4. **Recovering from missing data.** A missing source still requires upstream
   replanning. The current repair flow restarts decomposition; it does not repair
   only the affected branch.
5. **Unstated definitions.** Some reference SQL specifies bands, score formulas,
   or eligibility joins not fully stated in the question. General inference
   cannot guarantee those hidden choices without their business definitions.

The required sequence is: identify the population and grouping source; retrieve
facts and compatible identity keys; calculate each fact summary at its intended
level; join summaries with the intended inclusion rules; calculate the final
comparison; sort/limit and project. The existing operators support the tested
sequence. Source selection and plan meaning still require a fresh model run and
answer comparison to measure correctness.

No new runtime operator, benchmark-specific rule, or prompt expansion was added
for this check. Three regression tests and a reproducible local replay were added.

Replay: `../diagnosis_20260913/check_comparative_plans.py`

Machine-readable results and source hashes:
`../diagnosis_20260913/comparative_plan_replay.json`
