# Parallel SPARQL ensemble baseline

For each benchmark question, `run_pipeline.py` starts three independent
SPARQL generation and execution branches. It returns the strict-majority
result when at least two normalized branch results agree. The runner is
single-shot and ungraded; grading is performed later with the shared grader.

Start Fuseki from the repository root, then run:

```bash
python baselines/parallel_pipeline_baseline/run_pipeline.py
```

`run.py` supplies the shared SPARQL parsing, validation, execution, and
consensus helpers used by the runner. The final graded report is in
`../results/`.
