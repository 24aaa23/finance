# Offline replay of captured rerun plans

Snapshot: 2026-09-12T09:20:49.777829+00:00. Replayed: 2026-09-12T09:31:42.965690+00:00.

The fixed snapshot contains 86 completed log rows. 36 rows retained a declarative final plan and its input schemas.

| Check on those retained plans | Accepted |
| --- | ---: |
| Recorded final contract (compiler plus old builder gates) | 6 |
| Current offline compiler | 34 |

Previously accepted plans that now fail compilation: 0.

This is contract acceptance and execution on recorded samples only. Samples contain at most five rows per branch, so joins may be empty and aggregate values are incomplete. This does not recheck retrieval or final semantic validation, grade answers, or predict the number of successful queries in a full rerun. Earlier-stage failures have no final plan to replay.

Replay dispositions: `{"compile_error": 2, "compile_pass": 34, "no_recorded_declarations": 1, "no_recorded_final_spec": 49}`.

Recorded-sample execution: `{"not_recompiled": 50, "runtime_pass": 34, "skipped_compile_error": 2}`.

## Remaining compiler failures

- `wealth_management_70_question_benchmark:WM-3T-015`: Step input dataset does not exist: Investor; __spec_step_2 right join key: field does not exist on the selected input: investorId; projection: field does not exist on the selected input: investorName
- `wealth_management_70_question_benchmark:WM-3T-001`: Step input dataset does not exist: Investor; __spec_step_2 right join key: field does not exist on the selected input: investorId; projection: field does not exist on the selected input: investorName

## Remaining sample execution failures

None among the sampled plans that compiled.

To repeat the same snapshot:

```powershell
python experiment_week1/improvement3/diagnosis_20260912/replay_rerun_specs.py
```

Use `--refresh-snapshot` only to deliberately capture newer source CSV rows. The JSON report records source hashes, compiler hashes, schemas, and per-plan outcomes.
