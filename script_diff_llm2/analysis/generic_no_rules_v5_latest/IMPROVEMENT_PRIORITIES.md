# Small improvements after the final 81.1% v5 run

The final report records 811 MATCH, 61 PARTIAL, 126 MISMATCH and two PRE_SCAN_ERROR. Raw execution succeeds on 912 questions. The 189 non-matches comprise 85 contract failures, one context exception, two pre-scan failures, 40 executed mismatches and 61 executed partials. Grader API errors have already been retried successfully.

This is an implementation review and recommendation, not a new revision or measured accuracy increase. No runtime, grader or saved-report changes are made here. The complete paired audit and read-only probes are in REPORT.md and its companion JSON files.

## First small patch candidates

| Candidate | Evidence | Smallest generic change | Required validation |
|---|---|---|---|
| RDF display fields must not restrict eligibility | SQA125-1T-008 loses 13 goals because rdfs:label is mandatory. TT125-020 loses 15 transactions because unrequested metadata/relationships are mandatory. Minimal read-only queries recover both complete reference results. | Make QuerySpec/generation distinguish eligibility predicates from unrequested display fields. Omit unrequested fields or make them OPTIONAL while preserving declared row identity and multiplicity. Align pre-scan validation with this rule. | Synthetic typed entities with missing display properties: all eligible IDs remain; an explicitly required eligibility property still filters. Test multi-valued optional properties against requested output grain. |
| Field-to-field comparison syntax is poorly advertised | The QuerySpec JSON template lists value_type string/number/date/list, omitting the supported field type. Four unresolved cases say comparisons are impossible; other plans produce nested operand objects. | Add value_type field and a source-neutral example. Normalize a nested comparison reference only when its explicit source matches the owning predicate source and its field exists; otherwise keep it blocked. | Synthetic same-source field comparisons compile and execute; cross-source, unknown fields and ambiguous references remain rejected. Cover both shared and measure-local predicates. |
| NULL validator inconsistency | RC125-002 alternates between rejecting NOT IN for excluding NULL and rejecting OR IS NULL for widening the population. Plain NOT IN returns the exact empty reference result. | Require generation and validation to honor the QuerySpec predicate and any explicit missing-value requirement. Do not invent IS NULL merely because NULL values exist. Keep group-key NULL preservation distinct from membership predicates. | Synthetic non-null allowed/disallowed values and NULLs; plain NOT IN and explicitly requested missingness must produce different, correct populations. Do not blanket-accept all queries containing NOT IN. |
| Requirement ledger invents tasks | RC125-044/047 add zero-count category rows to questions asking which values are actually in use. Four cohort cases demand an additional definition for a descriptive band despite an explicit numerical criterion. | Clarify that the ledger records requested clauses only. Do not invent complete-enumeration output requirements. An adjective accompanying a stated threshold does not automatically add a second predicate. | Fake model responses plus contract checks using unrelated synthetic vocabulary; genuine extra undefined eligibility clauses still remain unresolved. |

These changes can be expressed without a financial category list, threshold table, metric formula or benchmark-ID mapping. The two RDF examples are strong counterfactual evidence; they do not guarantee gains on a regenerated full run.

## Additional cleanup defect found in code review

In specification.py, legacy predicates explicitly referencing their owning alias are moved from population_filters into aggregate_filters. The movement currently supplies stage entity whenever per_entity_operation is present, even if final_operation is also present. Both stages may be possible. This contradicts the safer v5 normalization rule that missing stage is inferred only for one aggregation level.

The correction is small: preserve explicit stage; infer a missing stage only when exactly one supported level exists; leave a two-level ambiguity for contract repair. Rewrite ledger paths as before and preserve scope. Do not silently change all such predicates to entity or final_group. This is a structural correctness improvement, not a guaranteed accuracy improvement: stricter handling could block plans whose repair fails. Existing migration tests need separate one-stage and ambiguous two-stage fixtures rather than assuming entity is always correct.

## Larger work to keep separate

- Source ownership mistakes are important but cannot all be corrected by a local name-based rule. Same-named columns on profile/fact tables may have different meanings; require the plan to justify owner selection from the question/schema/source descriptions.
- Average row values, average entity totals and final group aggregates require explicit per-measure grain. A universal SUM-to-AVG or AVG-to-SUM rewrite would be wrong.
- Units, stored versus computed financial metrics and sign conventions need explicit question or independently source-authored definitions. Do not translate the audit's diagnostic formulas into production defaults.
- Composite population min/max statistics need an explicit supported representation; adding missing aliases by guessing names would hide semantic errors.
- Large bound intermediate datasets need payload budgets or compact references. SQA125-1T-010 exceeds model context after a first node emits 4,600 rows. This is a more involved interface change than a prompt correction.
- Malformed generation needs complete structured-response recovery and finish-reason/token diagnostics; never accept a JSON fragment as a complete computation plan.

## Cases that should not drive pipeline rewrites

ARC125-1T-013's full saved answer has exactly all 4,013 reference goal IDs, despite a PARTIAL reason alleging extras. Grader truncation is the likely cause; excluding a prefix or reducing the answer population would damage correct behavior. The grader remains unchanged.

MC125-095 sorts genuinely different full-precision scores correctly, while the reference treats rounded scores as ties. Do not impose a two-decimal ranking rule merely to fit the reference. Ranking precision should be independently specified.

## Validation before promotion

Preserve the 81.1% v5 report as the baseline. Test each patch on synthetic data and the saved failure shapes, then run a fresh paired benchmark in a new output folder/version using the unchanged grader. Report both recovered and lost matches. No numerical improvement beyond 81.1% has been established by this review, and test-informed development still requires an untouched evaluation set for a generalization claim.
