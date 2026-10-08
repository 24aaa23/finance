# Mechanical fixes after inspecting the test set

Evaluation label: **Post-fix evaluation on an inspected test set (v4)**.

These changes were made after reviewing saved test-set execution traces. This rerun is not a new, untouched held-out evaluation.

Scope:
- Preserve the planner's explicit AND/OR condition tree during normalization and SQL serialization. Give precise feedback when QuerySpec changes that tree.
- Reject comparisons to JSON NULL and request explicit `is_null` / `is_not_null` presence operators.
- Reject quoted SQL, unresolved date placeholders and invalid typed or schema-declared date literals before scanning. Do not invent date boundaries.
- Validate referenced fields, datasets and output columns before execution. Give the source's actual available fields in repair feedback.
- Retain bounded SDK retries (`max_retries=5`, with SDK backoff). Classify exhausted HTTP 429 and other transient failures for a later retry. Do not add unbounded retries.

Metric selection, financial thresholds, name matching, snapshot defaults and grouping choices have not been changed to fit reference answers. Fixed operator order and agent flow are retained.

Run the selected retry from Windows CMD:

```cmd
cd /d "C:\Users\AMAN KUMAR SINGH\Desktop\financial\improvement10newdbsql"
python run_pipeline.py --workers 4 --model gpt-oss --retry-errors-in-place --retry-graded "outputs\full_run\graded_gpt_5_mini.csv"
```

The retry selects saved execution failures and current MISMATCH/PARTIAL grades. MATCH rows remain unchanged. Grades referring to an older answer are skipped. It does not select unsaved questions unless `--include-pending` is added.

Before replacing selected rows in `outputs/full_run/raw_pipeline.csv`, the runner backs up the existing reports and manifests in `outputs/full_run/backup_before_retry_<timestamp>/`. The manifest records mixed results, selected/completed IDs and run identities. Retain these backups when reporting the post-fix results.

Verification on 9 October 2026: all eight mechanical regression tests passed again using Python 3.10. No live model requests or pipeline run were started by this verification. Validation improvements do not guarantee a correct regenerated interpretation or eliminate every execution failure.
