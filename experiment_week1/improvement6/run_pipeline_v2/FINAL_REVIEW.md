# V4 end-to-end review

This pass checked the current source-selection/decomposition handoff, retrieval
contracts, connection-key preservation, raw SPARQL checks, Scan output schemas,
processing context, compiled calculations, final review evidence, and report/grader
paths. It is not proof that every future model-generated answer is correct.

## Additional defects fixed

| Finding | Change | Evidence |
|---|---|---|
| Invalid/empty decomposition could become a fallback source branch | Keep an explicit contract error; reject missing/unknown source classes against the available schema | Invalid JSON, empty branches, unknown class, malformed connection-list regression tests |
| Date fields lost their physical RDF datatype | Preserve all observed RDF datatype URIs per property; simplify metadata query BIND so datatype values are returned | RDF fixture plus actual local Fuseki metadata check: CashFlow.date is xsd:date; numeric decimal/double types retained |
| Selecting several measures could require all measures to exist | Schema-known property projections are optional in raw typed-source specifications; explicit filters still decide eligibility | Query_Spec regression verifies independently optional measures |
| A date filter could declare its value as a string | Normalize date/datetime filter value_type from unambiguous physical schema datatype, preserving literal boundaries | Date-boundary normalization regression |
| Syntax-valid raw SPARQL could aggregate, truncate, sort or deduplicate records | Parser checks reject aggregate expressions and row modifiers, including nested SELECT modifiers | COUNT, DISTINCT, LIMIT, OFFSET and nested-limit regressions |
| Empty Scan result could disguise an omitted selected field | Check returned column headers against the retrieval contract even with zero rows | Empty/missing-header-column executor regression |
| Retrieve choices and repaired SPARQL were not faithfully carried into diagnostics | Initialize retrieved classes from pre-DAG context; save actual Scan SPARQL and per-branch row counts; preserve that query in review evidence | End-to-end stubbed executor test deliberately returns different generated/executed queries |
| Optional final review only saw intended retrieval and result samples | Pass actual executed SPARQL per branch and execution step row counts | Context-handoff test; no added review call or default-setting change |
| Existence filtering could collapse left duplicates; NOT EXISTS could lose unmatched null keys | Honor distinct:false on intersection/difference and retain unmatched null-key rows when nulls_equal:false | Independent SQLite EXISTS/NOT EXISTS comparison with duplicates and nulls |

Set operations still default to distinct results and null equality. The final-plan
prompt now documents `distinct:false, nulls_equal:false` for SQL-style row existence
filters. This makes the intended semantics explicit without introducing another
operator. For unknown or mixed key domains the existing connection helper does not
guess compatibility.

## Verification

- **148 offline tests pass**, including independent SQL checks for grouping, joins,
  multilevel comparative calculations, null handling, formulas, ordering, and existence.
- Production V4 main module imports after all changes.
- Actual local Fuseki metadata load returns 27 classes and preserves date/decimal/
  double datatype information. This was read-only; no external model call was made.
- Historical compatibility replay still has **105 sample executions passing, 21
  compile errors, and 10 compiled plans without complete samples**, among 136 retained
  plans. It reports no regression among the 83 baseline plans previously executable.
  These are historical V3 declarations on at most five saved rows per branch, not
  a fresh V4 accuracy score. The V3 baseline comes from previously saved results on
  identical source report hashes because its source directory is unavailable.
- Original datasets and saved run/grade CSVs were not rewritten. No question IDs,
  expected answers or reference SQL were added to inference.

## Important remaining limits

1. **Missing source/path discovery is not implemented.** The connection helper
   validates and preserves declared keys; decomposition may still omit a necessary
   source or choose the wrong relationship. Final steps receive those declarations
   but do not yet have complete entity-type lineage enforcement.
2. **Generate remains an LLM call.** Optional fields and typed filter values are
   present in the contract, but parser checks do not establish complete equivalence
   between every SPARQL filter/graph pattern and the original question. A valid query
   could still omit a condition or bind an optional field incorrectly. A deterministic
   supported-contract retrieval builder remains a larger planned change.
3. **Ambiguous comparative definitions remain ambiguous.** Band boundaries, whether
   comparison means sum or average, population participation, and definitions such
   as concentration need business semantics. Shorter prompts cannot establish hidden
   benchmark conventions.
4. **Execution success is still separate from correctness.** Semantic review remains
   off by default and advisory when enabled. The separate grader reads final structured
   answers, not raw scans. Counts of completed runs must not substitute for MATCH counts.
5. **No fresh GPT-OSS evaluation was run.** Local tests establish specific fixes and
   execution behavior, not a promise of 350 correct answers or zero remaining defects.

The next useful measurement is a fresh mixed run followed by grading of actual final
answers. Include previously correct cases as well as missing groups, dates, profile
connections and comparative questions; use new filenames and record the source manifest.
