# Finance baselines

This directory contains the five 1,000-question baseline pipelines and their
final GPT-5.6 TERA graded CSV reports.

| Baseline | Code | Final graded result |
|---|---|---|
| Base SPARQL | `base_pipeline_qwen/` | `results/base_pipeline_qwen_dir_gpt_oss_120b_1000q_graded_gpt_5_6_terra.csv` |
| Base SQL | `base_pipeline_sql/` | `results/base_pipeline_sql_gpt_oss_120b_1000q_graded_gpt_5_6_terra.csv` |
| GraphRAG local retrieval | `graph_rag_local/` | `results/graph_rag_local_only_gpt_oss_120b_1000q_graded_gpt_5_6_terra.csv` |
| Parallel SPARQL ensemble | `parallel_pipeline_baseline/` | `results/parallel_gpt_oss_120b_1000q_graded_gpt_5_6_terra.csv` |
| Parallel SQL ensemble | `parallel_pipeline_sql_baseline/` | `results/parallel_sql_gpt_oss_120b_1000q_graded_gpt_5_6_terra.csv` |

`results/query_type_grading_results.md` contains the independent MATCH,
MISMATCH, and PARTIAL counts for every query type in each pipeline.

Only the local-retrieval GraphRAG baseline is included. The alternative
GraphRAG implementation and its reports are intentionally absent.

## Shared inputs

- `dataset/wealth_management_1000_questions.csv`: the 1,000-question benchmark.
- `../wealth_management_diverse.db`: SQLite data used by SQL baselines.
- `../script_diff_llm/kg/wealth_management_diverse_kg.ttl`: RDF graph used by
  SPARQL and local GraphRAG baselines.
- `../script_diff_llm/kg/wealth_management_diverse_schema.ttl`: RDF schema.

## Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r baselines/requirements.txt
cp baselines/base_pipeline_qwen/environment.example baselines/base_pipeline_qwen/.env
```

Fill in the credentials in `.env`. The file is ignored by Git.

The SPARQL baselines require Fuseki:

```bash
fuseki-server --file=script_diff_llm/kg/wealth_management_diverse_kg.ttl /wealth
```

## Run the baselines

```bash
python baselines/base_pipeline_qwen/run_pipeline.py
python baselines/base_pipeline_sql/run_pipeline.py

python baselines/graph_rag_local/run_pipeline.py build-index
python baselines/graph_rag_local/run_pipeline.py run

python baselines/parallel_pipeline_baseline/run_pipeline.py
python baselines/parallel_pipeline_sql_baseline/run_pipeline.py
```

Each runner saves progress incrementally under its own `output/` directory.
The committed files under `results/` are the completed 1,000-question graded
reports, not resumable working outputs.

## Grading

The unchanged grader used for these reports is stored in `grading/`. Configure
`OPENAI_API_KEY`, `RAW_REPORT_FILE`, and `GRADED_REPORT_FILE`, then run:

```bash
python baselines/grading/grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py
```

No API keys or local `.env` files are included.
