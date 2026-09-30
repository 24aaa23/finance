# Parallel SQL ensemble baseline

For each benchmark question, `run_pipeline.py` starts three independent SQL
generation and read-only SQLite execution branches. It returns the strict
majority result when at least two normalized branch results agree.

From the repository root:

```bash
python baselines/parallel_pipeline_sql_baseline/run_pipeline.py
```

The default database is the repository's `wealth_management_diverse.db`, and
the default benchmark is `../dataset/wealth_management_1000_questions.csv`.
The final offline-graded report is in `../results/`.
