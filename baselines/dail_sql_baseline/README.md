# DAIL-SQL GPT-OSS baseline

This directory contains the wealth-management adaptation of
[DAIL-SQL](https://github.com/BeachWang/DAIL-SQL), pinned during development to
upstream commit `2061f68112222083134a0c9e2877961ff315ff44`. The upstream
project is distributed under the Apache License 2.0; its license is retained in
`LICENSE.txt`.

The runner preserves DAIL-SQL's two-stage demonstration-selection flow:

1. Select nine examples using masked-question distance.
2. Generate preliminary SQL with GPT-OSS 120B.
3. Build a schema-masked skeleton from that preliminary SQL.
4. Select nine final examples by question distance, preferring skeleton
   similarity of at least `0.85`.
5. Generate final SQLite SQL and execute it against the database in read-only
   mode.

The example bank is the separate validated 300-question training workbook in
`dataset/`. The 1,000 evaluation questions are not used as demonstrations.
Exact question IDs and normalized question duplicates are also excluded.

## Adaptation from upstream

The upstream implementation uses Stanford CoreNLP and
`all-mpnet-base-v2`. This baseline uses local schema-aware masking and
normalized TF-IDF Euclidean distance so it runs in the same environment as the
other baselines without a Java service or an additional embedding model. The
SQL-code representation, QA example organization, preliminary generation,
SQL-skeleton reselection, and `0.85` threshold are retained.

Both `domain_intro.prompt` and `phase0_business_rules.md` are included in both
generation stages. The model is instructed to return only a complete SQLite
query without reasoning, prose, comments, or Markdown.

## Run

From the repository root:

```bash
pip install -r baselines/dail_sql_baseline/requirements.txt
cp baselines/dail_sql_baseline/environment.example baselines/base_pipeline_qwen/.env
python baselines/dail_sql_baseline/run_pipeline.py
```

Fill in the copied `.env` before running. The default inputs are:

- `wealth_management_diverse.db`
- `baselines/dataset/wealth_management_1000_questions.csv`
- `baselines/dail_sql_baseline/dataset/verification_results_v2_sql_correct_train_300.xlsx`
- `baselines/domain_intro.prompt`
- `baselines/phase0_business_rules.md`

The runner checkpoints its ungraded output under
`baselines/dail_sql_baseline/output/`. The committed raw and GPT-5 Mini graded
1,000-question reports are under `baselines/results/`.

## Grading shards

`scripts/gpt5mini_shards.py` splits a 1,000-row raw report into eight ordered
125-question files and recombines eight completed graded files. It validates
row counts, unique question IDs, column equality, and original order. It does
not contain or modify the grader prompt.
