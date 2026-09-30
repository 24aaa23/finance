# MC_diverse grader change and pipeline plan

## Implemented in the grader

Updated `../grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py`.

The new policy applies only to MC_diverse. A candidate must contain exactly the required named groups, plus extra rows with a genuine JSON-null group label. Unknown/ambiguous label mappings stay under strict grading. Strings such as `"NULL"` and `"Unknown"` are not treated as JSON null.

The grader sends the complete, unchanged answer and its strict verdict for a second review. It allows MATCH only when the reviewer explicitly confirms all five checks: unnamed groups are not required, named groups are complete, named metrics are correct, ordering is correct, and populations/denominators are unaffected. Merely finding a null row never changes a grade.

The review cannot excuse a wrong formula, null metric, missing named group, wrong ordering, or an extra unnamed winner replacing a required top result. Top/bottom/winner questions and overall/global-average questions are conservatively excluded from this adjustment. Answers too large for complete prompt inspection are excluded too. Numeric checks for the adjustment use reference rounding precision, with exact counts, instead of the existing strict prompt's universal 1.5 tolerance.

MC and TT receive no null-group exception. Their required missing-label groups must still be checked.

## Saved evidence

- `New Status`: resulting grade, compatible with existing summaries.
- `Original Grade`, `Original Grade Reason`, `Original Grade Evidence`: strict baseline.
- `Grading Policy`: versioned policy; MC_diverse uses `mc_diverse_extra_null_groups_v1`.
- `Null Policy Status`: `adjusted`, `retained`, `not_applicable`, or `review_error`.
- `Null Policy Reason`, `Null Policy Evidence`: review explanation, checks, and candidate row indices.
- `Grading Input Key`: fingerprint used for resume, including question, reference, answer, baseline metadata, and model.

When the input is an existing graded file from the same model, the grader reuses its strict baseline. A raw input needs ordinary grading first. Changed inputs, model, or policy are not silently skipped on resume. Failed null reviews retain the strict grade and retry on the next run. Input and output must be different files.

Tests use mocked model responses and temporary files. They verify policy routing, candidate guards, preservation, required review checks, full-answer prompts, error handling, and resume behavior. No live model regrading was performed while implementing this change, so no improved accuracy percentage is claimed.

## CMD command

This reviews the existing MC_diverse grades and saves a separate report. It makes paid grader API calls for eligible rows; it does not rerun the pipeline. Run from CMD:

```cmd
cd /d "C:\Users\AMAN KUMAR SINGH\Desktop\financial\experiment_week1\improvement5"
set RAW_REPORT_FILE=pipeline_output_v2\graded\MC_diverse_v2_graded.csv
set GRADED_REPORT_FILE=pipeline_output_v2\graded\MC_diverse_v2_null_policy_graded.csv
python grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py
```

Use the same command to resume. Original graded and raw files stay unchanged. Compare strict and adjusted grades under their respective policy names; an adjusted grade is an evaluation-policy change, not a repaired pipeline answer. For v1/v2 comparisons, apply the same grading policy to both versions.

## Pipeline changes still needed

These are recommendations, not changes already made to pipeline execution.

| Priority | Change | Why | Main locations |
| --- | --- | --- | --- |
| 1 | Preserve OR/IN semantics for compared groups; reject impossible same-field equalities and repair Decompose | MC-229/230 currently require two different categories simultaneously | `llm_operators/decompose.py`, `llm_operators/query_spec.py`, contract checks |
| 1 | Reject accidental comparisons to literal NULL; require `is_null` / `is_not_null` | TT-026 loses every row; MC-022 has the same kind of invalid presence test | `spec_runtime.py`, final-plan repair |
| 1 | Encode metric source, operands, investor grain, inner aggregation, outer aggregation, and population as structured requirements | Fix pooled averages, SUM-versus-AVG mistakes, wrong metric sources, and average-of-ratios errors | `business_rule_pack.json`, `decompose.py`, `final_spec.py`, contract checks |
| 2 | Declare null-label inclusion separately from missing-metric handling; validate label joins and aggregate-group merges | Some questions require unnamed groups; INNER label joins drop them and ordinary NULL-key joins split them | planning requirements, `final_spec.py`, join validation |
| 2 | Complete relevant domain definitions and source mappings | MC-002 invents goal-match bands absent from the compact pack | `business_rule_pack.json`, rule-coverage tests |
| 2 | Validate join identity types and actual cardinality | TT-055 joins unrelated identifiers; TT-051/064 violate uniqueness declarations | connection validation and final-plan contracts |
| 3 | Add optional semantic-plan repair with a bounded retry count and preserved evidence | `FINAL_SEMANTIC_REVIEW=1` currently records a verdict but does not repair the plan | `validate.py`, `executor.py` |
| 3 | Hash the resolved rule pack in the run manifest | Prevent results made under different rule packs from being mixed on resume | `run_identity.py`, `main.py` |

Before using match rate to judge these fixes, resolve benchmark conflicts such as TT-043's weighting/population disagreement with R5/R6. Make vague MC questions explicit about metric owner and averaging. Preserve prior references; version any corrected ground truth. Do not insert reference answers or question-specific expected values into pipeline prompts.

First verify a focused set with independently checked expected values: MC-002, MC-005, MC-010, MC-022, MC-201, MC-229, MC-244, MC-268, TT-002, TT-026, TT-043, and TT-055. Then rerun all datasets into new result files. Set `TEST_QUERY_LIMIT=0` for all 105 MC questions; use a new report because changing the query window changes run identity.
