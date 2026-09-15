# V8 repair changes

The saved run's 38 skipped MC questions showed that the response format and retry
behavior needed repair. This update stays inside V8 and keeps the same operators,
model calls and four-attempt FinalSpec limit. It does not add a new planning stage.

## What changed

* **One consistent comparative response.** The response format and full worked
  example both include `comparative_contract`. The separate comparative guidance
  is shorter. It explains inner versus outer aggregation directly: one grouping
  uses `inner_aggregate: none` and the actual grouping operation as the outer
  aggregate. It no longer leaves the allowed outer operations implicit.
* **Missing metadata preserves calculations.** If the only error is a missing
  contract, the next existing retry asks only for that object. Python preserves
  the previous steps, projection and other plan declarations even if the model
  returns rewritten steps. A disagreement between the added contract and the
  existing calculation becomes a normal plan-repair error on the following attempt.
  No contract is invented from the plan and treated as independent proof of meaning.
* **Names are normalized consistently.** Unique class/branch aliases resolve to
  actual datasets inside both plans and contracts. Ambiguous aliases remain errors.
  Decompose also resolves unique catalogue spellings that differ only in spacing,
  punctuation or case; question text and filter literal values remain unchanged.
* **Row counts describe a source relation.** COUNT(*) metadata may name a record
  identity without failing solely because the checker uses `*`. The checker still
  distinguishes row count, non-null value count and distinct count, and still
  verifies the source, grouping and aggregate operations.
* **Feedback names the actual problem.** Population errors identify missing sources
  and guaranteed participants. The prompt distinguishes required facts from optional
  label dictionaries. An unsupported outer operation gets a clear one-level example.
  Generated `__spec_step_*` declarations are renamed with their references to avoid
  collisions with compiler-owned IDs. Other invalid inputs/fields still fail.
* **Saved retries remain inspectable.** The repair-log CSV field is no longer capped
  at 12,000 characters, matching the existing full final-plan logging. This keeps all
  saved repair records/steps; individual raw-response excerpts retain their existing
  size limit. Debug CSVs can consequently be larger.

No question-specific branches, benchmark answers, reference SQL, or metric lookup
tables were added to inference. The example uses synthetic customers/payments/reviews.
There is no automatic switch to inner joins, no automatic weakening of required
populations, and no disabling of comparative checks.

## Validation

Verified: **202 offline tests pass** (186 existing tests and 16 new repair tests).
The subset launcher's path-validation dry run passes. V5 and V6 source files still
match their saved run manifests. The production repair changes are limited to
`comparative_contract.py`, `llm_operators/final_spec.py`,
`llm_operators/decompose.py`, and the repair-log serialization in `main.py`.
No live model, graph, or grading calls were made for this repair validation.

The new regression tests cover missing metadata, attempts to overwrite preserved
steps, invalid metadata, a genuine calculation error progressing to full repair,
ambiguous aliases, nullable counts, reserved IDs, catalogue spellings, and the
complete worked example. A test through the real executor confirms that all three
source scans are reused and the missing metadata is repaired in the next FinalSpec
call. Independent SQL comparison tests continue to cover weighting and populations.

```powershell
python -m unittest discover -s experiment_week1/improvement3/run_pipeline_v8/tests
python experiment_week1/improvement3/run_pipeline_v8/docs/replay_v8_repairs.py
```

Recompiling the 37 saved FinalSpec failures with the revised code clears MC-038
and MC-042 without changing their calculation operations. MC-026/048 now progress
past alias errors to their actual remaining population/grouping errors. MC-061's
name collisions clear, exposing a remaining dimension-provenance error. The other
saved plans still require model repair or corrected interpretation.

These are offline compilation results, not new answers or recovered MATCH grades.
The primary expected benefit of the new prompt and metadata-only retry requires a
fresh GPT-OSS run. Existing saved grades have not been changed. The old skip audit
remains a historical account; its source manifests will now differ from the repaired
production code, as expected.

## Next run

Use the existing launcher, which creates a fresh timestamped report under V8:

```powershell
& experiment_week1/improvement3/run_pipeline_v8/scripts/run_v8.ps1 -DryRun
& experiment_week1/improvement3/run_pipeline_v8/scripts/run_v8.ps1
```

It defaults to the fixed 68-question part-2 cohort. Compare skips and grades against
the saved baseline of 38 skipped / 3 MATCH. Do not assume the changes fix hidden or
ambiguous metric definitions, source-selection errors, or every remaining plan.
