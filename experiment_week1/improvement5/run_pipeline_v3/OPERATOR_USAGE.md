# V3 Operator Guide

Raw rows are retrieved first. One final relational plan performs the calculations.
The model chooses the plan; deterministic Python operators execute it.

| Stage | Responsibility | Model call |
|---|---|---|
| Retrieve | Select schema classes | Yes |
| Decompose | Select sources, conditions, connections and metric contracts | Yes |
| Query_Spec | Choose raw fields and optional properties for one source | Yes |
| Generate | Render raw SPARQL | Only when deterministic rendering cannot handle the schema |
| Pre_Scan_Validate | Check SPARQL and its retrieval contract | No |
| Scan | Read raw rows from Fuseki | No |
| Refine | Repair failed retrieval | Only on repair |
| Processing_Spec | Pass through raw rows and schema | No |
| Final_Spec | Plan joins, formulas, grouping, ranking and projection | Yes |
| Compile and Execute | Check fields, NULL filters, identity types and metric lineage; execute operations | No |
| Validate | Execution checks and final semantic review | Yes by default in v3 |
| Explain | Return structured rows | No by default |

Calculation operators include Filter_Aggregate, Integrate, Math_Compute, Order_By,
Date_Extract, Bucket, Distinct, Copy and set operations. Copy selects declared
columns without deduplication or filtering. Cardinality checks remain enabled.
Query_Spec_Validate remains inactive in the normal flow; its manual-use prompt was
synchronized with the business pack.

## Repair Routes

- Contradictory branch requirements: Decompose retries before scanning.
- Invalid metric source/field/group-owner contracts: Decompose repairs before
  final planning. A derived band's owner is the source of its input field.
- Missing raw fields or invalid predicates: Query_Spec retries; exhausted contract
  failures may trigger the existing bounded Decompose retry.
- Invalid final fields, NULL filters, identity joins or metric lineage: Final_Spec
  retries with concrete errors. Missing retrieval or explicit contract conflicts
  route upstream immediately. Persistent metric-lineage errors route upstream
  after four final attempts. The outer decomposition loop remains bounded to three
  attempts and receives its prior decomposition along with failure evidence.
- Review finds a calculation error: one Final_Spec repair by default, using the
  same retrieved rows. Retain a replacement only after execution and review pass.
- Review finds missing sources: preserve the result with a rejected review and its
  upstream repair reason. Semantic review does not automatically restart retrieval.

## Configuration

- `FINAL_SEMANTIC_REVIEW=1`: default; `0` disables final model review.
- `FINAL_SEMANTIC_REPAIR_ATTEMPTS=1`: default; `0` disables review-driven repair.
  The executor clamps this budget to 0-1. Compilation/execution retries are separate.
- `TEST_QUERY_LIMIT=0`: all rows by default, not the first 100.
- `BUSINESS_RULE_PACK_FILE`: optional custom JSON pack; the resolved content is
  hashed in the manifest. Category launchers select v3's local pack.

`PIPELINE_SUCCESS` means execution completed, not ground-truth correctness.
Check the answer-review columns and run the separate grader for accuracy.
