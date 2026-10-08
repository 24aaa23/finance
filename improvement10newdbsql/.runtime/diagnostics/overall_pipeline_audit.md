**Overall GPT-OSS SQL pipeline audit ? saved snapshot, 9 October 2026**

Read-only code, raw report, grader report, and trace review. Selected causes verified with read-only database queries. No model calls or pipeline/result edits. Grader assessments are not independently verified causes unless supported by the trace explanation.

**Results**

| Outcome | Rows |
|---|---:|
| MATCH | 429 |
| QUERY_SPEC_ERROR | 11 |
| MISMATCH | 199 |
| FINAL_SPEC_ERROR | 23 |
| PARTIAL | 46 |
| DECOMPOSITION_ERROR | 5 |
| CRASH | 2 |
| SCAN_ERROR | 6 |

721 graded rows of 757 questions; 36 have no saved execution result. Strict MATCH/saved = 59.5%; MATCH/semantically judged rows = 63.65%. Results mix old and new implementations; this is not a completed evaluation of v3.

**Actual flow**

YAML/domain/rules ? cached knowledge; each question ? Query Understanding ? Retrieve ? Decompose ? fixed per-branch QuerySpec ? Generate SQL ? Pre-scan validation ? read-only Scan ? ProcessingSpec (row-preserving) ? FinalSpec local joins/calculations ? structural/execution Validate ? Explain ? separate GPT-5-mini grader.

The operator order is fixed, but table selection, branches, filters, joins, metric operands, grouping, dates and output projection remain model decisions. SQL selects raw rows; the final calculation runs in the local operator engine. Domain/query-understanding specialists are available on demand, not mandatory for each question.

**Error diagnosis**

| Error | Total | Updated v3 | Reason |
|---|---:|---:|---|
| QUERY_SPEC_ERROR | 11 | 11 | Grouped OR contract differs from generated IN/flattened conditions. QuerySpec prompt lacks a grouped filter example and NULL-IN guidance. None None in feedback is a group-formatting issue, not evidence of absent data. |
| FINAL_SPEC_ERROR | 23 | 3 | Unsupported old expressions; missing datasets/columns/joins; aggregation/grain mismatch. Current v3 examples: T2_001 count contract, T2_078 missing window_start, T3_021 invalid Set_Difference inputs/keys. |
| DECOMPOSITION_ERROR | 5 | 3 | Unknown source columns or malformed logical operator=any/value shape instead of an any group. |
| SCAN_ERROR | 6 | 0 | Date operands are quoted SQL/functions/placeholders rather than actual dates. All currently saved Scan errors come from v2. |
| CRASH | 2 | 2 | Saved traces show Bedrock HTTP429 rate-limit errors at QuerySpec/QueryUnderstanding. |

**Why successful execution still yields MISMATCH/PARTIAL**

Validation checks structure, available columns, declared contracts and execution. It explicitly disables model semantic review, so a wrong interpretation or empty/wrong result can pass as PIPELINE_SUCCESS. Self-healing retries detected failures, not answers later marked MISMATCH by the separate grader. A flawed interpretation can remain internally consistent and pass all execution checks.

Mismatch causes include wrong entity keys, nullable scopes, exact abbreviated-name filters, wrong dates/snapshots, unit/threshold scale, selected population, aggregation grain and join multiplicity. Partial causes include correct subsets with missing entities/metrics, correct entities with wrong values, fragmented per-position rows, extra qualifying rows and identifier mismatches. Some cases reflect ambiguous question meaning or grader judgment; they require review rather than changing the reference answer.

**Verified representative cases**

| ID | Trace/database explanation |
|---|---|
| T1_017 | Final filter occupation != NULL evaluates UNKNOWN and drops all 30 scanned clients; presence needs IS NOT NULL. |
| T1_019 | Builds extra agency-specific measures then INNER joins them all. brick_rating has zero non-null rows, so its grouped result is empty and eliminates the other agencies. |
| T1_037 | Counts distinct ISIN (68) rather than product_id (84); confirmed both counts on the supplied database. |
| T1_134 | Exact amc_name='HDFC' matches zero rows; stored AMC name is HDFC AMC. |
| T1_160 | SUM includes all 180 AUM snapshot rows: 13,455,063,632.72. Latest snapshot sum is 2,348,178,644.45; no snapshot selection in saved final plan. |
| T2_003 | Filter uses equity_net >=0.65 on a 0..99.2 percentage scale. Database count at 0.65 is 27; at 65 it is 23. |
| T2_054 | Rating filter contains 'AA' admits AA as well as AA+ and AAA, rather than enforcing an ordered rating threshold. |
| T2_056 | Final plan projects per-position bond rows without grouping and summing quantity/current_value per requested bond; produces fragmented rows. |
| T2_067 | Projection uses numeric dim_mf_fund_complete.fund_id; expected product identifiers require the documented product mapping. |
| T2_017 | Family scan adds is_active IS NOT NULL AND is_deleted IS NULL, returns zero clients; later aggregation cannot recover excluded family members. |
| T2_039 | Exact client_name='Ram' returns zero rows; raw status filters also incorrectly require NULL flags. This loses records before portfolio calculation. |
| T2_040 | Scan requires dim_product_unified_cat.sector IS NOT NULL for mutual funds; that branch returns zero rows before joining fund categories. |
| T2_048 | Exact fund_name equality uses the abbreviated requested name and returns zero rows; no documented alias/name resolution in the saved plan. |
| T3_001 | Client master scan requires is_active IS NOT NULL AND is_deleted IS NULL and returns zero rows, removing all SBU valuation results. |
| T3_088 | Copies client_name into alias name, then copies that alias into servicing_banker; the banker output uses the client label rather than the joined employee label. |
| T5_019 | LOB dimension is not unique by lob_id (2 or 3 rows each). Revenue join multiplies 561 input rows into 1,594 joined rows before SUM; trace has no cardinality validation. |
| T5_037 | Selects 2025 calendar transactions although reference includes 2026; joins account mappings on client_id, repeating trades across client accounts. |
| T6_041 | Retrieves clients and AUM but explicitly computes xirr=NULL; does not retrieve or compute the required metric. |
| T6_042 | Required XIRR values are absent in saved answer; grader flags otherwise correct top client selection as incomplete. |
| T6_075 | Selects and projects benchmark_return_1y only; benchmark_return_3y is absent from the saved retrieval/projection. |

**Knowledge and healing limitations**

All 21 supplied table YAMLs and both supplied domain/rules documents were given to the GPT-OSS knowledge builder; it cached 68 rules. The simple mode performs an LLM completeness review but does not enforce section-by-section coverage. This does not prove missing knowledge caused any specific failure.

Decompose has three attempts and FinalSpec has four. Missing retrieval can request upstream repair. The saved problematic plans often repeat the same invalid representation or assume unsupported operations. Specialist availability does not ensure a consultation is requested.

4 of 292 problematic saved rows record specialist consultations. Trace indicators are nonexclusive and do not by themselves prove a cause:

- Final filter compares to NULL instead of a presence operator: 1 rows
- Final answer is empty: 123 rows
- At least one executed retrieval branch returned zero rows: 131 rows
- NULL appears in SQL IN; it does not include NULL-valued records: 17 rows
- Definite contradictory AND on nullable status flag: 70 rows

**Priority fixes to consider (not applied by this audit)**

1. Align QuerySpec/Decompose prompts and canonical logical representations; give precise grouped-tree feedback and reject NULL-IN misuse where the required scope includes NULL.
2. Preserve documented units, identity mappings, name aliases and snapshot definitions in Query Understanding and carry those contracts into final validation.
3. Check join cardinality and output grain, including dimension keys that are not unique; do not deduplicate raw facts indiscriminately.
4. Route missing raw inputs upstream and repair invalid plan syntax/functions with explicit supported examples.
5. Handle API429 as a transient retry with bounded backoff; question-worker count alone is not a request-rate limit.
6. Retry selected failures and regrade changed answers while preserving old results and mixed-run provenance. Use documented general rules, not per-question answer patches.

Every current error/MISMATCH/PARTIAL row has its grader assessment, failure reason, SQL and final-plan evidence in overall_pipeline_failure_reasons.csv.
