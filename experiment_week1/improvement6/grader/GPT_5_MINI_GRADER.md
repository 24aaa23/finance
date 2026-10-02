# GPT-5 mini grader

Run from this directory in CMD:

```cmd
set "LLM_GRADER_MODEL="
python grade_openai_gpt_5_mini.py
```

This grades all eight question types sequentially using `gpt-5-mini` and
`OPENAI_API_KEY`, discovered through the same local `.env` search as TERA.
The endpoint is fixed to `https://api.openai.com/v1`; Bedrock credentials and
`OPENAI_BASE_URL` are not used.

Inputs: `pipelien_output_sql_gpt_oss_grader/<type>/raw_pipeline_v9.csv`.
Outputs: `pipelien_output_sql_gpt_5_mini/<type>/graded_openai_gpt-5-mini.csv`,
with a separate OpenAI API usage log in each type folder.

The original TERA grading prompt, tolerance, truncation, parsing, CSV grading,
and resume logic are preserved. Model API defaults are retained.
Add `--type benchmark` to select one type, or `--dry-run` to validate all inputs
without API calls or output writes. Completed rows resume on subsequent runs;
use fresh outputs if the source reports change. Setup does not start grading.

Model documentation: https://developers.openai.com/api/docs/models/gpt-5-mini
