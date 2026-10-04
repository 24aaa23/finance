# NeoWealth test dataset, unchanged v5 pipeline

The provided workbook has 768 questions on the `questions` sheet and normalized reference cells on `gold_answers`. `runners/prepare_neowealth_test.py` creates `data/benchmarks/neowealth_test.csv`, with stable task IDs and complete JSON references reconstructed from gold_answers. Valid embedded references are cross-checked, every row count is verified, and gold SQL is excluded from the prepared file. Six oversized-answer placeholders are reconstructed: T3_129, T3_133, T3_187, T3_190, T3_192 and T3_194. All 768 records pass the unchanged benchmark loader.

The new experiment is named `openai_gpt_oss_120b_neowealth_test`, with split `test`. Generation uses unchanged v5 code; grading uses the existing TERA grader against the workbook's references copied into the raw report. The previous 216-question override and the wealth-management identifier alias map are disabled. The optional semantic catalog remains disabled. Pipeline and grader source code are not changed by this setup.

## Required source assets

The workbook is a question/reference dataset, not the database it queries. Its tables include `dim_client_master` and `dim_mf_nav_history`; these are different from the existing wealth_management_diverse tables. At preparation time, the matching NeoWealth database and graph were not found in the repository. The full current pipeline also initializes RDF metadata, so it requires both the matching SQLite database and RDF schema/instance, not just an Excel question bank. A non-SQLite database requires a compatible SQLite export or a separately authorized adapter change.

Supply the matching assets at these default paths:

- `data/sql/neowealth/neowealth.db`
- `data/kg/neowealth_schema.ttl`
- `data/kg/neowealth_kg.ttl`

Alternatively export absolute paths using `NEOWEALTH_SQLITE_DB`, `NEOWEALTH_SCHEMA_FILE`, and `NEOWEALTH_INSTANCE_FILE` in the pipeline terminal. Do not use the old wealth-management database or graph. The launcher checks files before making model calls and stops if an asset is absent.

## Commands once the matching assets are available

In the Fuseki terminal:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
./tools/apache-jena-fuseki-6.1.0/fuseki-server \
  --localhost --port=3031 \
  --file="${NEOWEALTH_INSTANCE_FILE:-$PWD/data/kg/neowealth_kg.ttl}" /neowealth
```

In another terminal:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash runners/run_neowealth_test.sh all
```

This runs all 768 questions, then grades with the existing grader. It makes paid model calls. Reports use `outputs/openai_gpt_oss_120b/all/test/neowealth_v5/{raw_pipeline.csv,graded_pipeline_tera.csv}`, with version `generic-v5-neowealth-test`.

Resume the same run with the same command. Run/resume only raw generation or grading with:

```bash
bash runners/run_neowealth_test.sh raw
bash runners/run_neowealth_test.sh grade
```

Regenerate evaluation input if the workbook changes:

```bash
/usr/bin/python3 runners/prepare_neowealth_test.py
```

Use separate reports when changing the workbook/source assets; do not mix dataset revisions in one run. Grader input truncation for very large answers remains an existing limitation, as the grader is unchanged.
