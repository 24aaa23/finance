# Script Diff LLM Experiments

This folder is intended to be self-contained for model comparison runs.

## Shared Files

- `dataset/verification_results_v2_sql_correct_train_300.xlsx`
- `dataset/verification_results_v2_sql_correct_test_142.xlsx`
- `kg/wealth_management_diverse_schema.ttl`
- `kg/wealth_management_diverse_kg.ttl`
- `kg/rdf_id_alias_map.json`
- `tools/apache-jena-fuseki-6.1.0/`

## Base Templates

The scripts were generated from `base_templates/original_9_1_full_pipeline_with_grader.py`.

The clean split templates are:

- `base_templates/run_pipeline_base.py`: pipeline only, no final MATCH/MISMATCH/PARTIAL grading
- `base_templates/grade_base_gptoss_deterministic.py`: GPT-OSS 120B deterministic grader only

## Layout

Each model folder has the same structure:

```text
<model-folder>/
  all/
    train/
      run_pipeline_*.py
      grade_*.py
      output/
    test/
      run_pipeline_*.py
      grade_*.py
      output/
  hybrid/
    train/
      run_pipeline_*.py
      grade_*.py
      output/
    test/
      run_pipeline_*.py
      grade_*.py
      output/
```

`all` means the target model is used for the whole pipeline.

`hybrid` means GPT-OSS 120B is used for the core structured steps:

```text
DAG planner
Query_Spec
SPARQL Generate
```

The target model is used for the remaining model-specific steps.

Grading is separate from pipeline generation. Pipeline scripts save raw execution results with
`New Status=PIPELINE_SUCCESS`, `PRE_SCAN_ERROR`, `SCAN_ERROR`, `CRASH`, or `QUOTA_EXHAUSTED`.
Then the folder's `grade_*.py` script reads that raw CSV and writes a graded CSV.

The grader uses:

```text
Requirement_Analyzer: GPT-OSS 120B
Column_Mapper: GPT-OSS 120B
Final comparison: deterministic Python
```

## Start Fuseki

From this folder:

```bat
start_fuseki.bat
```

The Fuseki endpoint used by scripts should be:

```text
http://127.0.0.1:3030/wealth/query
```

## Environment

Copy `env/.env.example` to `env/.env` and fill in the API keys/region.

The scripts load `.env` from their local folder, parent folders, or `script_diff_llm/env/.env`.

## Run Order

Example:

```bat
cd qwen.qwen3-coder-480b-a35b-instruct-aman\all\train
python run_pipeline_qwen_qwen3_coder_480b_a35b_instruct_all_train.py
python grade_qwen_qwen3_coder_480b_a35b_instruct_all_train.py
```

## Output Naming

Use this pattern inside each `output/` folder:

```text
raw_pipeline_<model>_<mode>_<split>.csv
graded_<model>_<mode>_<split>.csv
```

Example:

```text
qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/raw_pipeline_qwen3_coder_480b_all_train.csv
qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/graded_qwen3_coder_480b_all_train.csv
```
