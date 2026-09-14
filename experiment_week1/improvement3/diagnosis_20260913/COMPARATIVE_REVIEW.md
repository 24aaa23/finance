# Multi-step comparative questions: formation, merging, and step order

Reviewed 13 September 2026. The supplied 442-question workbook contains 76 questions
from the collection named `wealth_management_multi_step_comparative_105_questions`.
The collection name does not mean all 105 remain in this filtered workbook. The
original authoring/generation script was not located in the workspace; the structure
below is inferred from the supplied question/SQL pairs, not claimed generator history.

## How the reference queries are constructed

The 76 retained pairs have 4 one-table, 14 two-table, 32 three-table, 15 four-table,
and 11 five-table cases. Seventy-one use WITH subqueries (CTEs: named intermediate
tables). Sixty-five reference the investor-profile table. All contain GROUP BY
somewhere, including ranking queries that group intermediate facts first.

The recurring pattern combines a grouping dimension, a set of per-entity measures,
and a final comparison or score. Repeated CTE bodies suggest reusable SQL components,
but that does not prove how the original questions were generated.

| Family | Reference sequence | What must survive decomposition |
|---|---|---|
| Within one fact source, e.g. MC-001 | Raw records -> independent averages by attribute | Nullable values, grouping attribute, raw identity |
| Across a profile dimension, e.g. MC-006 | Sum facts per investor -> profile join -> average those totals by profile category | Investor link AND the source owning profile category |
| Across a fact category, e.g. MC-014 | Sum by investor AND cash-flow type -> join investor-level rebalance totals -> average by type | Both summary grouping keys, not investor alone |
| Compare changes, e.g. MC-016 | Difference within each action -> average by investor AND logic -> join scenario averages -> average by logic | Paired row-level inputs, investor key, logic key |
| Several profile measures, e.g. MC-051 | Independent goal/holding summaries -> join profile and health -> averages by profile group | Common investor identity, separate source populations |
| Rank a score, e.g. MC-104 | Component summaries -> required joins -> formula per investor -> sort -> limit | Component definitions, common investor identity, ranking after calculation |

Examples of reusable component meanings observed in the reference SQL:

- Holding value/gain: sum current value and sum(current value - cost) per investor.
- Goal progress/shortfall: average each measure per investor, with separate non-null denominators.
- Cash net: sum signed amount; inflow: sum positive amounts; outflow: positive magnitude of negative amounts. CASE branches can contribute zero, which is not the same as dropping the investor.
- Allocation concentration: maximum allocation percentage per investor, then a group average when requested.
- Rebalancing gap: average(target allocation - current allocation), computed from paired values within each record.
- Scenario change: average(new allocation - current allocation), likewise computed per record before averaging.

These describe the reference, not universal definitions to hardcode into inference.
Some prompts omit the component definition, the final averaging level, or band
boundaries. MC-086/MC-100 also join health as an eligibility source despite selecting
no health metric. Such a join can affect population if a profile lacks a matching
health record; a correct answer needs the intended participation rule, not merely
the displayed measures. CTEs often define extra unused metrics; the pipeline need
not compute those extras if they have no effect on the final SQL result.

## Are the saved decompositions and merges correct?

Often they are not. Of 65 retained comparative SQL queries using profiles, 53 saved
decompositions lack an actual Investor source. Sources frequently substitute Category,
Segment, TimeHorizon, or RiskTolerance dimensions for the investor-to-dimension
relationship. This is a structural warning, not proof all 53 answers must fail:
some profile joins could be redundant on particular data or expressed another way.
Three failed decompositions have no source class at all. See `comparative_structure.json`
for every retained question, reference SQL, saved source list, and execution status.

Concrete trace findings:

- MC-006 chooses holding category rather than profile category and sums directly
  by that category rather than averaging per-investor totals.
- MC-035 selects Category plus goal/health facts, then joins category subject IRIs
  to investor references. Existing fields and compatible primitive representations
  do not make them the same entity.
- MC-014 needs investor-plus-type grouping; its result instead reports totals and
  counts and drops the null type group.
- MC-065 returns investor/scenario rows instead of a comparison by time horizon.
- MC-068 follows several aggregation levels but uses average allocation rather
  than per-investor maximum allocation for concentration.

The previous full-data diagnostic reproduced MC-006 and MC-035 reference answers
from current RDF records using reference SQL in an isolated SQLite database. That
establishes feasibility for those cases; the saved model-generated plans are wrong.

## Small production corrections made in this review

1. Executor now carries each branch's question into its final table profile.
2. Final_Spec receives the existing declared predicates and joins explicitly, with
   branch IDs alongside actual dataset IDs. Previously its prompt exposed only raw
   retrieval specifications and separately inferred direct schema join options.
3. The final prompt explains the calculation order and retaining entity-plus-category
   keys when needed. It preserves the original question as authoritative and asks
   for missing sources instead of joining unrelated identities.
4. Decompose gets a short instruction to include the source connecting an entity
   to its grouping attribute, rather than selecting only a list of attribute labels.

No question ID, expected value, reference SQL, domain metric lookup, automatic
Investor injection, or new model stage was added to inference. The shared connection
helper from the preceding change preserves declared keys but still does not discover
missing paths or enforce every final join's semantic meaning.

## Execution checks

Added independent SQL comparisons with unrelated synthetic names and deliberately
unequal fact counts, missing values, a null category, and an entity missing a required
related source:

- Summaries -> two joins -> group averages: no fact multiplication, correct null
  groups, separate non-null average denominators, correct inner-join population.
- Summaries -> joins -> score -> top two: filtering/participation precedes ranking.
- Entity-plus-category summaries -> join -> category comparison: both intermediate
  keys survive, including a null category.
- A prompt handoff test checks that branch responsibility and declared connections
  actually reach Final_Spec.

All 138 offline tests pass. This confirms the existing compiler/runtime can follow
these sequences with a valid plan. It does not prove GPT-OSS chooses that plan after
the prompt changes; no fresh model or grading run was performed here. Missing source
discovery, exact typed retrieval, and semantic validation of final merge lineage remain
the main implementation gaps described in V4_CORRECTNESS_PLAN.md.
