# Finance baselines

This directory contains the five 1,000-question baseline pipelines and their
current GPT-5 Mini graded CSV reports. The current snapshot passes
`domain_intro.prompt` and `phase0_business_rules.md` to every generation call
in addition to the runtime schema/DDL or retrieved RDF facts. Earlier result
sets remain under `results/` as historical snapshots.

| Baseline | Code | Final graded result |
|---|---|---|
| Base SPARQL | `base_pipeline_qwen/` | `results/base_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv` |
| Base SQL | `base_pipeline_sql/` | `results/base_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv` |
| GraphRAG local retrieval | `graph_rag_local/` | `results/graph_rag_local_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv` |
| Parallel SPARQL ensemble | `parallel_pipeline_baseline/` | `results/parallel_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv` |
| Parallel SQL ensemble | `parallel_pipeline_sql_baseline/` | `results/parallel_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv` |

`results/query_type_grading_results_domain_context_gpt_5_mini.md` contains the independent MATCH,
MISMATCH, and PARTIAL counts for every query type in each pipeline.

`results/category_grading_results_125_each_domain_context_gpt_5_mini.md` contains the independent MATCH,
MISMATCH, and PARTIAL counts for each of the eight 125-question source
categories in every pipeline.

`results/baseline_changes_domain_context_20261004.md` records the prompt-context,
grading, operational, and result changes from the previous snapshot.

`results/baseline_metrics_domain_context_gpt_5_mini.md` reports accuracy, token latency,
inference cost, average inference cost per question, and execution efficiency
for every current baseline.

Only the local-retrieval GraphRAG baseline is included. The alternative
GraphRAG implementation and its reports are intentionally absent.

## Shared inputs

- `dataset/wealth_management_1000_questions.csv`: the 1,000-question benchmark.
- `domain_intro.prompt`: shared domain reference context passed verbatim.
- `phase0_business_rules.md`: shared business-rules reference passed verbatim.
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

The unchanged grader prompt used for these reports is stored in `grading/`.
Configure `OPENAI_API_KEY`, `RAW_REPORT_FILE`, `GRADED_REPORT_FILE`, and set
`LLM_GRADER_MODEL=gpt-5-mini`, then run:

```bash
python baselines/grading/grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py
```

No API keys or local `.env` files are included.

To rebuild the two Markdown summaries from the current graded CSVs:

```bash
python baselines/scripts/generate_grading_markdown.py
python baselines/scripts/generate_baseline_metrics.py
```
