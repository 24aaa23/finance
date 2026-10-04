# Audit of generic no-rules v2, 2026-10-03

The latest completed run is `outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v2_20261003`. Both raw and graded reports contain 1,000 unique, identical sample IDs. Every row uses pipeline version `generic-contract-grounding-v2-20261003`. The graded report's question, reference, pipeline answer, node traces and version match the raw report exactly. The grader uses `strict_v1`, `grader_2` and `gpt-5.6-terra` throughout. There are no changed question/reference strings in the paired comparison with v1.

This audit changes analysis artifacts only. It does not change the pipeline, grader, benchmark outputs or source databases. SQL replays use read-only SQLite connections; RDF checks use read-only Fuseki SELECT queries. Reference answers are used only for offline diagnosis, never for runtime definitions or prompts.

## Outcome

| Metric | Previous generic v1 | Latest generic v2 |
|---|---:|---:|
| MATCH | 579 (57.9%) | 721 (72.1%) |
| PARTIAL | 45 | 57 |
| MISMATCH | 365 | 215 |
| Raw execution success | 698 | 825 |
| Query_Spec contract failures | 295 | 167 |
| Binding failures | 2 | 4 |

Other v2 grades: 2 SCAN_ERROR, 2 PRE_SCAN_ERROR, 1 OTHER and 2 GRADER_API_ERROR. Percentages use all 1,000 benchmark rows. MATCH + PARTIAL is 77.8%, but PARTIAL is not counted as a correct answer.

The gain over v1 is **142 matches, or 14.2 percentage points**. Relative to the older 63.7% run, the gain is 84 matches, or 8.4 percentage points; that older run used embedded domain rules and is not a controlled ablation of generic behavior.

Paired v1 comparison: 467 old matches remain matches; 254 old non-matches become matches; 112 old matches become non-matches. Net gain: 254 - 112 = 142. Of the 112 lost matches, 70 now fail the Query_Spec contract, 2 fail binding, 37 execute but receive a non-MATCH grade, and 3 fail scan/pre-scan. Among 231 previously unsuccessful raw executions that now succeed, 208 become MATCH, 15 PARTIAL and 8 MISMATCH. Conversely, 101 formerly successful executions become DAG errors. The improvement is substantial but does not preserve every previously correct answer. Model variability and multiple simultaneous changes prevent attributing the net gain to one fix.

## Raw execution versus answer correctness

Of the 215 MISMATCH grades, **171 are failed DAG executions** and **44 are successful executions with incorrect answers**. Thus 79.5% of mismatches are blocked plans/bindings. The remaining unsuccessful raw runs comprise 2 scan and 2 pre-scan errors. Of 825 successful executions, 721 match, 57 partially match, 44 mismatch, 1 is unassessable and 2 have grader API errors. Execution success alone is not answer correctness.

## Remaining contract failures

The following incidences overlap and must not be summed:

| Failure pattern | Rows |
|---|---:|
| Physical aggregate marked final_group, then rejected for lacking a formula | 48 |
| Formula operands treated as derived aliases and rejected | 43 |
| Unknown logical source/base names | 48 |
| Explicit unresolved requirements | 29 |
| Problems with metric population-filter representation | 12 |
| Empty output schema, including nested population validation | 10 |
| Unknown physical fields/formula operands | 9 |
| Missing measure field/formula | 4 |
| Unknown final projection alias | 3 |
| Unparseable plan | 3 |
| Literal/quoted-requirement conflict | 3 |

**83 distinct rows have one or both formula-stage/operand failures.** This is the main new interface issue, not proof that all 83 plans are semantically correct. Some plans have additional genuine defects.

`formula_stage="final_group"` currently makes both the validator and SQL compiler treat a measure as a derived-alias expression. But the model also uses that marker on physical COUNT/SUM/AVG measures, or on row formulas with physical column operands. For example, ARC125-3T-017 describes a physical holding count with eligibility filters and no formula; the marker causes rejection for “derived measure needs an expression.” ARC125-4T-001 uses a CASE expression over `current_value` and `cost`, but the same marker makes those columns be checked as aggregate aliases. The interface needs separate operand kind and evaluation grain, with structural repair when unambiguous and explicit rejection when genuinely inconsistent.

Unknown labels such as `investor`, `base` and `event` still occur. The declared-primary-key fallback cannot resolve this database: a read-only inspection confirms that none of its eight tables declares a primary key. Do not invent keys or choose a physical base table by a financial-name mapping. Supply independently validated source identities/relationships, or require the model to choose a real source from the schema.

Aggregate predicates are also being placed in `population_filters`. SQA125-2T-006 places `avg_sharpe_ratio_across_goals > 1` inside the metric's input filters. The nested validator has no aggregate alias context and rejects it. That condition belongs after the per-investor aggregate. Another three failures use a final alias such as `investmentGoalTypeLabel` without declaring a projection binding; the appropriate repair is an explicit field-to-alias mapping, not blanket permission for invented outputs.

Provenance warnings are no longer the principal execution barrier. Among 536 successful executions with warnings, 491 are MATCH, 24 MISMATCH, 20 PARTIAL and 1 GRADER_API_ERROR. Warning presence alone does not identify a wrong answer.

## Executed-answer problems confirmed from traces and replays

### Attribute ownership and category fields

EC125-2T-029 groups by the holding table's segment, although the reference uses the investor profile's segment. EC125-2T-043 similarly uses holding category instead of profile category. Read-only queries using the profile dimension reproduce the references exactly for all 65 and 78 groups respectively. The generated queries are executable and schema-valid; schema-name validation cannot distinguish these meanings.

WM125-3T-017 still filters `PortfolioHolding.investmentName = Gold`, producing no data, rather than selecting the category field. SQL-only category profiling does not provide the same evidence to the RDF path. TT125-063 places “Internal Transfer channel” in the `type` field. Source/value grounding needs to cover both backends and retain the owner of every attribute, rather than selecting a convenient repeated name.

WM125-2T-023 filters both profile goal and individual goal records to Emergency Fund. The question requires investors selected by their stated goal, then averaging their goal progress. Removing the extra goal-record restriction changes the average from 19.2019 to 41.0143, agreeing with the 41.01 reference. This is an eligibility-scope error.

### Input filters versus aggregate filters

SQA125-2T-014 asks for investors whose average annual goal return exceeds 35. The generated query filters individual goal rows with `WHERE avg_annual_return_pct > 35`, then averages only those retained rows. This changes both the population and the average. A replay that averages all goal records first and applies HAVING returns the 11 reference investors. Similar extra-entity errors occur in SQA125-3T-009 and SQA125-3T-028. The contract should distinguish row eligibility, per-entity aggregate eligibility and final-group eligibility explicitly.

### Stored versus computed metrics, signs and grain

SQA125-1T-016 uses `AVG(returns_pct)` with the recorded cost/current-value filter. The reference uses the computed holding return. For Gold, the stored-field average is 103.01075, while `100*(current_value-cost)/cost` averages 109.11162, agreeing with the 109.112 reference. Many EC/MC partials share this distinction. A generic pipeline cannot infer that two source metrics with similar names are interchangeable. Metric definitions must come from explicit question semantics or an independently authored source catalog, not benchmark-derived hardcoding.

TT125-007 and TT125-071 invent inflow/outflow category sign logic over amounts that are already signed. For TT125-071, the generated CASE expression returns 1,205,465,660, while summing stored amounts returns 803,318,818, exactly the reference. TT125-068 has the opposite ambiguity: summing stored negative Withdrawal amounts yields the negative of the requested positive withdrawal total. Signed net totals and transaction magnitudes need distinct definitions; neither blanket ABS nor blanket sign reversal is valid.

MC125-004 computes an AVG of each investor's sector investments when the requested metric is average *total* investment. Replacing the inner AVG with SUM produces the reference investment values while leaving the correct allocation averages unchanged. This illustrates why each metric needs its own row/entity/final-group grain, even when several metrics share a source table.

### Null groups and null membership

MC125-043 and MC125-096 aggregate metrics by a nullable dimension, then join those aggregates using `dimension = dimension`. SQL NULL does not equal NULL, so the final null group remains present but its metrics become null. A null-safe join restores those metric bindings. MC125-043 still has other grain differences after that repair; it is not a complete fix by itself.

RC125-072 adds `profile.segment IS NULL OR profile.segment NOT IN (...)`, turning an empty reference result into a large result set. Removing the added null branch returns no rows. RC125-007 and RC125-074 have related null-membership problems. Twelve RC partials report correct named values/counts plus an extra null category. Distinguish “outside a set” from “missing or outside a set,” and distinguish ordinary nullable group preservation from a non-null reference-value coverage report. Do not globally drop null groups to raise scores.

### RDF date checks are not receiving the required evidence

TT125-072 and TT125-084 compare `xsd:date` literals to untyped string dates and return zero. Read-only Fuseki replays that type the constants return 300,702,150 and 200,498,710 respectively, exactly the references.

The metadata query currently evaluates DATATYPE inside an OPTIONAL block with only a FILTER/BIND and no pattern binding its input there. A focused live SELECT using that structure returns an unbound datatype (`{}`). A direct `DATATYPE(?o)` SELECT over the date predicate returns `xsd:date`. Therefore the new deterministic check lacks observed datatype evidence and cannot reject these comparisons. Fix metadata extraction and test the complete metadata-to-validator path, not just the validator with manually constructed metadata.

### Ranking, syntax and error handling

Some MC partials retrieve most/all correct investors but use an incorrect score or ordering (MC125-055/056/057/085/110/112/115). Review component eligibility, min-max normalization population, numeric division and tie breaks together. MC125-056's generated arithmetic omits an explicit real-valued cast within the component divisions; that is a type-sensitive concern, not a proven cause without a type-specific replay.

The two SQL scan errors were independently reproduced: MC125-060 has an extra closing parenthesis; TT125-119 uses HAVING in a non-aggregate outer query without GROUP BY. These are execution defects that passed pre-scan validation. The SQL executor returns immediately on scan error rather than repairing it, unlike the KG scan repair loop. Parse/prepare checks before execution and a bounded SQL scan-repair path would address this class without domain rules.

## Where performance is weakest

Each family has 125 questions:

| Family | v1 MATCH | v2 MATCH | v2 accuracy |
|---|---:|---:|---:|
| General wealth management | 73 | 111 | 88.8% |
| At-risk/critical | 63 | 107 | 85.6% |
| Batch/status | 87 | 108 | 86.4% |
| Enrichment/context | 65 | 83 | 66.4% |
| Multi-step/comparative | 37 | 39 | 31.2% |
| Reference/compliance | 92 | 94 | 75.2% |
| Scoring/quantitative | 81 | 92 | 73.6% |
| Temporal/transaction | 81 | 87 | 69.6% |

MC has 39 MATCH, 29 PARTIAL, 55 MISMATCH, 1 SCAN_ERROR and 1 PRE_SCAN_ERROR. It accounts for 29 of all 57 partials. The large overall gain comes mainly from general, critical and batch questions; multi-metric comparative semantics remain weak.

Pure SQL: 612/854 MATCH (71.7%). Pure KG: 109/138 (79.0%). Mixed backend: 0/8 MATCH. These are different question populations, not a controlled backend comparison. There are 991 single-node executions and only 9 with multiple nodes; all nine multi-node executions receive MISMATCH. Eight are mixed-backend. Four fail bindings; five fail contracts before completion. This run does not establish a decomposition benefit. It specifically exposes a need to test declared subquery output contracts and cross-backend identity bindings.

## Grader exceptions and runtime

RC125-113 and SQA125-2T-030 are grader request timeouts, not demonstrated pipeline errors. Their saved answers are consistent with the reference count and group averages respectively; retry the unchanged grader to establish final labels. RC125-064 is OTHER because the final-answer JSON sent for grading is explicitly truncated. Do not treat it as evidence that query semantics were wrong.

Average per-question runtime decreased from 36.05 to 33.15 seconds. Median is 22.70 seconds, p95 52.63 seconds and p99 630.89 seconds. Twelve questions exceed 300 seconds and contribute 7,710.62 seconds, or 23.3% of cumulative per-question time. Based on the first row's start and report completion time, wall time is approximately 145 minutes versus 156 minutes for v1. Operator-level timing is not available, so the tail cannot be assigned conclusively to one model call or retry stage.

## Recommended next work, in order

1. Separate physical/derived operands from computation stage; represent row filters and aggregate predicates independently. This targets the largest remaining contract cluster and prevents threshold-before-average errors. Keep genuinely unknown fields and unresolved semantics blocking.
2. Repair RDF datatype extraction and verify end-to-end behavior against synthetic typed RDF data. Extend source-value evidence to KG, and preserve dimension ownership in both backends.
3. Make every metric's definition, grain, unit, sign convention, eligibility and missing-value policy explicit. Use source-owned metadata where the database cannot establish semantics; never transplant reference-answer formulas into prompts.
4. Compile or validate independent aggregate joins with null-safe keys, and preserve SQL null predicate semantics. Apply special non-null coverage policies only when justified by the question/source definition.
5. Validate SQL syntax against the actual read-only schema before scanning; add bounded repair for SQL scan errors. Strengthen projection and binding contracts for multi-node DAGs.
6. Regrade the two API exceptions with the unchanged grader. Keep truncation separate from semantic failures. Evaluate targeted fixes on a fresh version/folder and use a held-out domain plus decomposition ablation before making paper-level transfer or decomposition claims.

Artifacts: [summary.json](summary.json), [row_diagnostics.csv](row_diagnostics.csv), [read_only_replays.json](read_only_replays.json), and [analyze.py](analyze.py). Recompute the saved-output statistics with `/usr/bin/python3 script_diff_llm2/analysis/generic_no_rules_v2_20261003/analyze.py` from the repository root. Replay evidence records the queries and their observed results separately; it is offline diagnosis and must not be imported by the runtime pipeline.
