# Bedrock graders

These are copies of `grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py`.
The grading prompt, numeric tolerance, truncation, parsing, execution-failure
handling, CSV columns, and resume logic are unchanged. The original is untouched.

| Script | Default model |
| --- | --- |
| `grade_bedrock_deepseek_v3_2.py` | `deepseek.v3.2` |
| `grade_bedrock_qwen3_235b_a22b.py` | `qwen.qwen3-235b-a22b-2507` |
| `grade_bedrock_kimi_k2_5.py` | `moonshotai.kimi-k2.5` |
| `grade_bedrock_mistral_large_3.py` | `mistral.mistral-large-3-675b-instruct` |
| `grade_bedrock_glm_5.py` | `zai.glm-5` |

The client uses `https://bedrock-mantle.<region>.api.aws/v1`. Region comes from
`BEDROCK_REGION`, `AWS_REGION`, or `AWS_DEFAULT_REGION`, defaulting to `us-east-1`.
Keys are read from `AWS_BEARER_TOKEN_BEDROCK`, `AWS_BEDROCK_API_KEY`,
`AWS_Bedrock_API_gpt_oss_120b`, or `BEDROCK_API_KEY`, in that order. OpenAI keys
and OpenAI endpoints are not used. Existing .env discovery is unchanged.

## Inputs and outputs

Every script reads question, ground truth and pipeline answer from
`pipelien_output_sql_gpt_oss_grader/<type>/raw_pipeline_v9.csv` under this directory.
The raw files are never modified. Each model saves matching type subfolders in:

- `pipelien_output_sql_deepseek_v3_2`
- `pipelien_output_sql_qwen3_235b_a22b`
- `pipelien_output_sql_kimi_k2_5`
- `pipelien_output_sql_mistral_large_3`
- `pipelien_output_sql_glm_5`

## Run

From this `grader` directory, run all eight types sequentially for a model:

```powershell
python grade_bedrock_deepseek_v3_2.py
```

Replace the script to choose another judge. Add `--type benchmark` to run one
type, or `--dry-run` to check all paths without API calls or output writes.
All paths resolve relative to the script, regardless of terminal directory.
No grading starts merely by importing a script.

Each destination type folder contains `graded_bedrock_<model-ID>.csv` and a
model-specific API log. Old report-path environment settings are ignored by
these runners. A conflicting `LLM_GRADER_MODEL` is rejected to prevent mixing
judges within one folder. Inherited resume logic does not validate changed
input rows; use fresh outputs if the raw reports change.

Offline validation passed for all four: identical grading-function syntax and
messages, Bedrock credential selection and endpoint, model IDs, CSV save/resume,
and missing-key rejection. No live inference or dataset grading was performed.

GLM 5 uses the same grading code as the DeepSeek Bedrock copy, changing only
the model ID and output folder. Its account access was verified separately
with a small live request; no dataset grading was started during setup.
Run `python grade_bedrock_glm_5.py` for all eight types, or add `--dry-run`
to validate paths without grading.
