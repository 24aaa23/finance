# Base SQL baseline

`run_pipeline.py` generates one read-only SQLite query per benchmark question
with GPT-OSS 120B and executes it against the repository's
`wealth_management_diverse.db` database.

From the repository root:

```bash
python baselines/base_pipeline_sql/run_pipeline.py
```

The default benchmark is `../dataset/wealth_management_1000_questions.csv`.
Credentials are loaded from `../base_pipeline_qwen/.env` or shell variables.
The final offline-graded report is in `../results/`.
