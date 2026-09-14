# Rerun audit, 2026-09-12

Snapshot taken at 09:16:34 UTC. The CSV files grew during inspection, so these counts describe the saved rows at that time, not a completed benchmark.

| File | Saved rows | Pipeline successes |
|---|---:|---:|
| `v3_rerun_v1_success.csv` | 43 | 5 |
| `v3_rerun_v1_non_success.csv` | 38 | 1 |
| Combined, unique question IDs | 81 | 6 |

Combined statuses: 25 Processing_Spec errors, 29 Final_Spec errors, 19 Query_Spec errors, one decomposition error, one pre-scan error, six successes. All 60 rows that reached Scan reported scan success. Pipeline success is not a correctness grade.

At the start of inspection, every current v3 source-file SHA-256 matched the rerun manifest. The manifest identifies `aop-improvement3-compiled-contracts-v6` with model `openai.gpt-oss-120b-1:0`. These failures came from the intended modified source version.

## What the saved evidence proves

1. **A correct lookup is rejected by unnecessary downstream planning.** For `WM-1T-001`, Scan returned one row, `investorId=INV-001`, `investorName=Arjun Iyer`. All three Processing_Spec attempts then ended with `Malformed spec: 'operator'`. `WM-1T-002` similarly retrieved the requested risk tolerance and time horizon before failing. Twenty saved rows have this exact final validation error. This is an interface/runtime defect; it does not indicate failure to retrieve the answer.

2. **Operator JSON and runtime naming disagree.** `WM-1T-004` used `step_id`, `input_dataset`, and `output_dataset`; the compiler ignored those aliases and rejected a requested output that the plan had explicitly named. In `WM-3T-011`, the model used `operation: Integrate`, `left`, `right`, and `on`. The runtime expected `operator`, `inputs`, and explicit key fields. Several simple filter plans provided `Filter_Aggregate` and `filters` but omitted `operation: filter`, producing an empty-operation error. These are recoverable syntax differences when intent is unambiguous.

3. **The raw retrieval critic confuses one branch with the whole plan.** Examples include `WM-2T-001`, `WM-2T-020`, and `WM-4T-006`. The critic demands other classes' retrieval specs inside the active branch; the deterministic contract then rejects more than one retrieval spec. This creates a repair loop. In `WM-1T-019`, the critic even asked to remove global ranking requirements because retrieval must be raw, although those requirements belong to later execution.

4. **Optional fields are treated as missing selected fields.** The Query_Spec prompt example places a nullable field only in `optional_fields`, while validation requires it to also appear in `fields`. `WM-1T-018` and `WM-2T-012` fail on this discrepancy. Fields mentioned explicitly in optional selection and entity keys should be included in the scan selection after schema validation.

5. **Generated requirements are enforced as infallible.** `WM-1T-013` asks for transaction count and total amount by type. Its requirements incorrectly list raw `amount` in the final projection. A final output containing the group, `transaction_count`, and `total_amount` is rejected for not outputting raw `amount`. `WM-3T-011` requests cash-flow totals after an average-progress condition; validation incorrectly demands that the filtering-only `avg_progress` metric remain in the final projection. The current grain check also applies the final grouping rule to intermediate aggregates, although those may legitimately use a different grain.

6. **Some plans still contain real meaning errors.** `WM-3T-011` has raw `progressPct < 40` and `date = '2025'`, although the question needs an average-progress threshold and the full calendar year. `WM-2T-014` attempts `type = Deposit AND type = Withdrawal`. Fixing rejection bugs does not make these plans correct. Original-question validation must retain responsibility for actual predicate/aggregation errors.

## Smallest useful direction

- Preserve scans as branch outputs by default; plan transformations once at the final stage.
- Normalize unambiguous syntax aliases in one place, and preserve structured errors instead of crashing on missing keys.
- Keep the retrieval critic local to its assigned branch.
- Treat generated answer requirements as fallible planning context. Validate actual operations and compare the final answer against the original question; do not reject solely because two model-generated aliases differ.
- Verify against these real saved spec shapes and a few live small queries before repeating the full benchmark.

This audit does not establish a recovered success rate or correctness score. It identifies the rejection mechanisms present in the saved run.
