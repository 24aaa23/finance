# GPT-OSS context v5, GPT-5 Mini grading audit — 2026-10-05

## Scope and integrity

Analyzed `outputs/openai_gpt_oss_120b/all/test1000/context_v5_01/raw_pipeline.csv` and `graded_pipeline_gpt_5_mini.csv`. The GPT-OSS `with_context` ablation folder is empty; this report concerns the completed legacy context run, not a new ablation. The incomplete TERA report is not used for current accuracy.

Both files contain 1,000 unique, identical sample IDs. Questions, references, answers, scan rows, node traces, and pipeline versions agree between the raw and graded reports. Every row uses `generic-contract-recovery-v5`; the grader is `gpt-5-mini` with `strict_v1`. Input SHA-256 hashes are recorded in `summary.json`. All 210 PARTIAL/MISMATCH rows and five grading errors are captured in `nonmatches.json`; this is a full report inventory, with selective independent semantic checks rather than independent regrading of every answer.

Only analysis artifacts were written. The pipeline, grader, benchmark references, and saved outputs were not changed. SQL checks use a read-only SQLite connection and hand-authored SELECT statements; no model calls were made.

## Recorded results

| Outcome | Rows | Share of 1,000 |
|---|---:|---:|
| MATCH | 785 | 78.5% |
| PARTIAL | 81 | 8.1% |
| MISMATCH | 129 | 12.9% |
| GRADER_API_ERROR | 4 | 0.4% |
| TOKEN_OUTPUT_ERROR | 1 | 0.1% |

The resolved-judgment match rate is 785/995 = 78.89%. MATCH + PARTIAL is 86.6%, which is not full-match accuracy. Five grader errors remain, but quota exhaustion is no longer the dominant problem. Even if all five become MATCH, this unchanged raw run reaches at most 79.0%.

Raw execution succeeded on 903 rows and failed on 97. All 97 failures became MISMATCH. Successful execution produced 785 MATCH, 81 PARTIAL, 32 MISMATCH, and five grader errors. Among successful rows with resolved grading, full-match accuracy is 785/898 = 87.42%.

## Where performance is weakest

Each family has 125 questions.

| Family | Match | Partial | Mismatch | Grader errors | Match rate | Raw failures |
|---|---:|---:|---:|---:|---:|---:|
| General | 116 | 2 | 7 | 0 | 92.8% | 6 |
| At-risk | 106 | 8 | 9 | 2 | 84.8% | 8 |
| Batch/status | 115 | 2 | 8 | 0 | 92.0% | 8 |
| Enrichment | 103 | 6 | 16 | 0 | 82.4% | 2 |
| Comparative | 41 | 34 | 49 | 1 | **32.8%** | **47** |
| Reference/compliance | 94 | 21 | 10 | 0 | 75.2% | 6 |
| Scoring | 107 | 6 | 10 | 2 | 85.6% | 8 |
| Temporal | 103 | 2 | 20 | 0 | 82.4% | 12 |

Comparative questions account for 83/210 semantic nonmatches and 34/81 partials. Of their 49 mismatches, 47 are execution failures. Their central problem is representing and executing complex metrics reliably, rather than final answer wording.

## Main causes and independently checked examples

### 1. QuerySpec contracts prevent execution

94 failures are at `Query_Spec_Contract`, two at `Exception`, and one at `Binding`. Execution failures explain 75.2% of all recorded mismatches.

Contract tag incidence across node traces includes 46 rows with unresolved requirements, 17 with missing derived expressions, 11 with missing output-schema contracts, 10 with unknown/self-referencing alias operands, seven with unknown base entities, five with unknown sources, and five with unparsed specs. Tags overlap and are not a partition of failures. Twenty-eight failed rows have contract text mentioning both cash flow and sign uncertainty.

`MC125-095` rejects missing expressions for normalization stages. `MC125-084` cannot resolve min/max aliases. `MC125-107` reports an integer downstream ID contract against a TEXT physical key. A generic fix should provide typed intermediate measures, explicit formula dependencies and normalization stages, source-derived ID types, and targeted retries with exact contract errors. Genuine ambiguity should remain visible; disabling validation would conceal incorrect computation.

### 2. Wrong aggregation grain and metric meaning

`MC125-007` averages goal rows directly, weighting investors with more goals more heavily. Computing average shortfall per investor first, then averaging investors by risk tolerance, reproduces all reference shortfall values to rounding.

`MC125-003` uses SUM(target allocation − current allocation) per investor for an average-shift request. AVG at the investor stage reproduces all reference shifts to rounding.

`MC125-032` uses stored `returns_pct`. Computing 100 × (current value − cost) / cost on eligible holdings, averaging per investor and then by risk tolerance, reproduces all reference return values to rounding. This confirms the source/formula discrepancy; the intended formula should be grounded in approved database documentation or explicit question wording, not hardcoded from benchmark answers.

`MC125-030` independently aggregates metrics by risk tolerance and joins groups using ordinary equality. NULL groups cannot match NULL through `=`, so that group's metrics become NULL. Its cash-flow mean also averages event rows rather than first averaging per investor. Generic remedies are explicit measure-level grain/population contracts and null-safe group joins.

### 3. Wrong source ownership and population filters

`WM125-2T-026` filters the goal table's goal type instead of the investor profile's stated goal. The pipeline returns 38.3854; filtering the profile and averaging all goals per selected investor returns 41.3418, agreeing with reference 41.34.

`WM125-2T-023` similarly applies an unwanted child-goal filter. The corrected population returns 41.0143 against reference 41.01.

`EC125-3T-010` interprets “have a Growth goal” as a profile attribute. An EXISTS condition on goal records, alongside an EXISTS condition on Mutual Fund holdings, exactly reproduces all four reference risk-group counts.

`EC125-2T-029` groups by holding segment instead of investor segment. Grouping profile segment with holding sector exactly reproduces all 65 reference groups. This question's wording is less explicit about segment ownership, reinforcing the need for approved source definitions rather than assuming a universal owner.

### 4. Signed cash flows are transformed twice

`TT125-055` asks explicitly for SUM of signed amounts. Generated SQL introduces a transaction-type whitelist and reverses other amounts, yielding 401,596,601 instead of 401,051,589. Direct SUM(amount) exactly matches the reference.

`TT125-004` repeats this sign reconstruction. Summing recorded amounts for 2024 and applying HAVING SUM(amount) < 0 reproduces the reference's 212 investor IDs exactly.

The portable rule is to preserve recorded signs when the question or validated source definition says amounts are signed. Do not invent a type-to-sign taxonomy or assume every financial database uses the same convention. Mere presence of positive and negative values is not sufficient proof of every metric's intended meaning.

### 5. Entity joins create duplicate answers

Four independently checked investor-list partials have exactly the reference entity sets, but duplicate output rows:

| Sample | Answer rows | Reference entities | Duplicate IDs |
|---|---:|---:|---:|
| WM125-3T-026 | 15 | 13 | 2 |
| ARC125-4T-002 | 93 | 35 | 58 |
| ARC125-4T-003 | 115 | 45 | 70 |
| ARC125-4T-025 | 4 | 3 | 1 |

For an entity-list question, child-record existence predicates should use EXISTS/semijoins or project distinct requested entities. Do not apply global DISTINCT to questions requesting child records or detailed rows.

### 6. NULLs and allowed-set questions

Reference-family partials often add a NULL bucket to an enumeration comparison: for example, `RC125-032` returns correct allowed categories plus 755 NULL holdings. Similar issues occur in source/type/category checks. Questions comparing an allowed set should distinguish valid members, nonmember values, and missing values. Nullable foreign keys are not automatically invalid references. Do not blanket-remove NULL groups: comparative and enrichment references legitimately include them.

### 7. Some recorded partials reflect limited grader visibility

The existing grader truncates each answer/reference at 60,000 characters. Twenty rows exceed this boundary in at least one payload; their recorded grades are 15 PARTIAL, two MATCH, and three MISMATCH. Length alone does not establish a grading error.

Two full-result checks establish stronger evidence:

| Sample | Required entity set | Answer/reference rows | Missing/extra IDs | Recorded grade |
|---|---|---:|---:|---|
| ARC125-1T-013 | Underfunded goals | 4,013 / 4,013 | 0 / 0 | PARTIAL |
| ARC125-1T-015 | Goals with progress <30% | 2,420 / 2,420 | 0 / 0 | PARTIAL |

Both questions request lists of goals; the complete saved goal-ID sets are exact. The missing/extra-entity interpretation is not supported by these full payloads. Different row order and truncation can prevent the LLM from seeing corresponding records. These checks are separate audit evidence, not changes to recorded grades or a claimed corrected overall accuracy. Reordering runtime answers to imitate unseen reference ordering would not be a portable fix.

## What this run says about context and decomposition

No saved QuerySpec or node trace contains `domain_context_trace`. The input manifest names both documents but has no approval file. The current context loader quarantines evaluation-scoped documents such as `phase0_business_rules.md`; operational policy activation requires approval. Thus this report does not establish that operational business rules were applied. Terminology may still have influenced decomposition, which does not record the same trace. The manifest does not identify an immutable prepared bundle, so exact run-time activation cannot be reconstructed solely from the current cache.

Consequently, label this as a run configured with context inputs, not evidence that business-rule integration improved or worsened accuracy. Future runs should persist prepared-bundle fingerprint, active-entry counts, selected entries per stage, and fallback status.

The traces contain 992 single-subquery DAGs and eight DAGs with multiple nodes. A single subquery may still execute complex SQL; this is not automatically a defect. However, complex comparative computations frequently remain in one QuerySpec. Explicit stages for per-entity metrics, eligible population, normalization, composite construction, and ranking could reduce malformed formula contracts. Preserve each stage's population and grain so additional decomposition does not change semantics.

## Comparison with the earlier 81.1% run

The previous no-rules v5 report records 811 MATCH, 61 PARTIAL, 126 MISMATCH, and two PRE_SCAN_ERROR rows. Current full-match accuracy is 2.6 percentage points lower. Questions/references and IDs align exactly, but the previous grader was `gpt-5.6-terra`, current grader is `gpt-5-mini`, and raw answers were rerun.

Raw success declined from 912 to 903: 72 previously successful rows now fail, while 63 previous failures now execute. Match transitions show 83 former matches lost and 57 new matches gained, net −26. This substantial turnover is consistent with generation/recovery instability and requires controlled repetitions to separate causes.

506 successful current scan payloads are byte-identical to previous payloads. Of these, six former MATCH rows are now PARTIAL, one former PARTIAL is MISMATCH, and two former mismatches improve; two further former MATCH rows have grader errors. These changed judgments on unchanged inputs demonstrate evaluator effects, but do not isolate model choice from grader randomness. The aggregate −2.6 points cannot be attributed solely to business context or solely to Mini.

## Recommended order of work

1. Retry the five grader errors on the existing Mini report. IDs: ARC125-4T-001, ARC125-4T-014, MC125-086, SQA125-3T-006, SQA125-4T-009. This cannot by itself reach 80%.
2. Restore observable context activation and source-grounded metric definitions. Verify selected context, not just configured file paths. Keep evaluation-derived rules quarantined.
3. Improve QuerySpec recovery and typed expression stages without weakening semantic contracts. Comparative execution failures offer the largest opportunity.
4. Enforce measure-level population, ownership, aggregation grain, sign handling, and null-safe grouping. The read-only probes demonstrate concrete recoverable errors.
5. Apply entity-list deduplication and explicit allowed-set/missing-value semantics where the question requires them.
6. Compare with/without context using the same model, grader, database snapshot, configuration, and repeated runs. Keep independent large-result checks beside unchanged recorded grades.

Reaching 80% requires at least 15 additional matches from this report, or ten after an optimistic recovery of all five grading errors. The identified defects offer plausible opportunities, but this audit does not guarantee a score improvement or justify embedding benchmark-specific answers into runtime rules.

## Reproduce the audit

From the repository root:

```bash
/usr/bin/python3 script_diff_llm2/analysis/gpt_oss_context_gpt_5_mini_20261005/analyze.py
/usr/bin/python3 script_diff_llm2/analysis/gpt_oss_context_gpt_5_mini_20261005/sql_checks.py
```

Artifacts: `summary.json`, `row_diagnostics.csv`, `nonmatches.json`, `entity_checks.json`, and `sql_checks.json`.
