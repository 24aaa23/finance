# Base SPARQL baseline

`run_pipeline.py` generates one SPARQL query per benchmark question with
GPT-OSS 120B, executes it against Fuseki, and writes an ungraded report. The
default benchmark is `../dataset/wealth_management_1000_questions.csv`.

Start Fuseki from the repository root, then run:

```bash
python baselines/base_pipeline_qwen/run_pipeline.py
```

Configuration is read from shell variables or `.env`. Use
`environment.example` as the template. The final offline-graded report is in
`../results/`.
