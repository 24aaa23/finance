# Completed saved-run audit

The completed V3 simplified run contains 192 input questions: 91 pipeline successes,
91 Final_Spec errors, 4 decomposition errors, 4 pre-scan errors, and 2 Query_Spec
errors. Both V3 reports are complete. All 45 source hashes recorded in their run
manifests match the current V3 source; the diagnosis is not inferred from filenames.

The saved typed-repair V4 reports contain 179 questions and 81 pipeline successes.
The report named `v4_typed_repair_non_success_137.csv` contains 124 rows, so 13 of
its input rows are absent. Its manifest records a different implementation in five
source files. These historical V4 results do not measure the new V4 changes.

Of 43 successful V3 executions in the separately graded prior-success subset,
the grader reports 26 MATCH, 8 PARTIAL, and 9 MISMATCH. Execution success therefore
does not establish answer correctness. The other 48 successful V3 executions were
not graded by the supplied `graded_v3_simplified_v7_success_55_terra.csv`.

## Main V3 failure families

Counts overlap when a failed row reports more than one defect:

| Reported family | Failed rows |
| --- | ---: |
| No explicit final plan parsed | 38 |
| Selected input field missing | 29 |
| Duplicate column after repeated joins | 23 |
| Text forced into numeric arithmetic | 9 |
| Unsupported aggregate JSON shape | 8 |
| Missing explicit join key mapping | 4 |
| Retrieval branch dependency rejected | 4 |

Saved no-plan failures retain only `contract_errors`; their raw model responses are
not saved. The reports cannot distinguish an empty response, truncated JSON, a JSON
wrapper, or another response structure for these 38 rows. Future failures need the
raw response and finish reason to establish the cause.

## Concrete evidence and simple remedies

* WM-1T-012 already joins holdings to InvestmentType, counts rows by label, and then
  uses `column('rdfs_label')` to copy that label into `investment_type`. Arithmetic
  evaluation rejects the text label. Copying a column should preserve its type.
  WM-1T-014 and multiple comparative questions show the same defect.
* Saved typed-repair WM-2T-008 correctly filters `sector = 'Technology'` and
  `allocationPct > 30`. The validator compares these local names against
  `SectorAllocation.sector` and `SectorAllocation.allocationPct`, then falsely
  reports both predicates missing on three identical retries. Normalize a field
  qualifier only when it names the active class and an existing schema field.
* An explicit non-null/date filter can legitimately remove a null value from an
  OPTIONAL field. The pre-scan model critic rejects that pattern in MC-018 and
  WM-1T-020. BSQ-2T-004 is rejected for not retrieving another branch's classes.
  Replace this extra critic with parser-based SELECT/projection checks; Scan checks
  actual database execution. This removes a fallible gate rather than adding one.
* Unqualified final `rdfs_label` notes were treated as a raw requirement of every
  class with that property. They are final answer notes, not an instruction to
  require unrelated labels on every fact source. Keep active-source predicates and
  explicit relationship keys, and let the final plan choose its output labels.
* Chained joins repeatedly produce `subject_iri_right`, which collides on the next
  join. Several plans also assume a foreign-key field exists on both inputs when
  the right input instead uses its subject identity. The runtime and prompt must
  share one predictable naming/mapping rule.

## Remaining correctness issues shown by grading

The supplied grades still show missing null category groups, missing requested
names or sector columns, wrong/empty joins, and incomplete or overbroad predicates.
WM-1T-011 and WM-2T-005 omit the unspecified risk-tolerance group; WM-2T-002,
WM-2T-003, WM-2T-017, WM-2T-020, WM-4T-001, and BSQ-3T-009 return empty results despite
nonempty expected answers. TT-047, TT-058, and BSQ-4T-005 have wrong membership;
MC-017 computes the wrong measures. Relabeling these rows as success cannot repair
their answers. The user's independent grader remains the correctness measurement.

`audit_completed.py` produces `saved_run_audit.json` from existing local CSVs and
manifests. It does not contact a model, endpoint, or grader and does not read
benchmark answers into pipeline prompts.
