# Pipeline output and successful-execution grades

Evaluation label: **Post-fix evaluation on an inspected test set (v4)**.

Main reports:
- `raw_pipeline.csv`: all saved answers and execution failures, copied from `outputs/full_run`.
- `graded_gpt_5_mini.csv`: existing current grades only for rows whose raw execution status is `PIPELINE_SUCCESS`. This includes MATCH, MISMATCH and PARTIAL answers. Execution failures are retained in the raw report, not this graded report.

The original `outputs/full_run` reports are preserved. Snapshot counts and source hashes are in `snapshot.json`. The existing run manifest, question input and lossless result JSONL are copied for restart provenance. Original debug traces are copied to `original_diagnostics/`; the runner will create fresh debug reports alongside the main reports during the retry.

From Windows CMD, retry the raw execution errors and current MISMATCH/PARTIAL rows with four pipeline workers:

```cmd
cd /d "C:\Users\AMAN KUMAR SINGH\Desktop\financial\improvement10newdbsql"
python run_pipeline.py --workers 4 --model gpt-oss --output-dir "outputs\pipeline_output" --retry-errors-in-place --retry-graded "outputs\pipeline_output\graded_gpt_5_mini.csv"
```

This writes replacements to this folder's raw CSV and preserves MATCH rows. Existing reports are backed up before retry. It does not run questions with no saved result. Grader labels select IDs only; reference answers are not passed to the generation agents.

After the pipeline command finishes, grade successful executions into the same graded CSV with four grader workers:

```cmd
python grader.py --workers 4 --model gpt-5-mini --only-pipeline-success --retry-nonmatch --input "outputs\pipeline_output\raw_pipeline.csv" --output "outputs\pipeline_output\graded_gpt_5_mini.csv"
```

New or changed successful answers are graded normally. Unchanged MATCH grades are reused. MISMATCH/PARTIAL and grader failures are regraded. Rows still failing execution are omitted from the graded file and remain visible in the raw file. The previous graded CSV is backed up before replacement.

Neither command was started when preparing this folder. The pipeline uses AWS Bedrock GPT-OSS 120B; the separate grader uses GPT-5-mini with the local OpenAI configuration. Generation, financial rules and grading criteria are unchanged. Only the optional success-only selection was added to the grader.
