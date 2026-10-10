# Neowealth hybrid experiment

This runs the current main decomposition/DAG pipeline with Gemini 3.8 Flash, native read-only DuckDB, and the matching Neowealth RDF graph. It does not convert DuckDB to SQLite. Use the existing key in `../gemini_3_8_flash/gemini.env`. All inference stages use Gemini; the optional separate grader uses GPT-5 mini and the project OPENAI_API_KEY.

Inputs:

- Database: `script_diff_llm2/neowealth.duckdb` (21 tables, 313 columns).
- Questions: `neowealth-master-question-bank_FINAL_DELIVERABLE.xlsx`, prepared into `data/benchmarks/neowealth_test.csv` (768 questions).
- Schema: `kg_output_neowealth/neowealth_schema.ttl`.
- Instance graph: `kg_output_neowealth/neowealth_kg.ttl` (includes schema; do not load data.ttl again).
- SQL asset: `data/sql/neowealth/asset.yaml`.
- Fuseki: `http://127.0.0.1:3031/neowealth/query`, separate from the original wealth endpoint.

The database SHA256 exactly matches the conversion summary source hash: `67e4c39a2637a4b0f895d554f36d480a70c7781447f60ac527073a58c003630b`. All 21 table row counts match the summary. This establishes that these are matching assets, not proof of answer accuracy. Graph schema descriptions are supplied metadata; old wealth context files, ground-truth overrides and ID alias maps are excluded. Gold answers remain evaluation/reporting data; gold SQL is excluded from prepared input. The graph uses hashed row IRIs: cross-backend plans must project the original identifier properties, rather than interpreting IRI suffixes as SQL IDs. No suffix-based identity mapping is fabricated.

Terminal 1, from `script_diff_llm2`:

```bash
bash ablations/neowealth_hybrid/start_fuseki.sh
```

Terminal 2, raw only:

```bash
bash ablations/neowealth_hybrid/run.sh raw run_01 4
```

Raw followed by grader 2 on GPT-5 mini:

```bash
bash ablations/neowealth_hybrid/run.sh all run_01 4
```

Grader only:

```bash
bash ablations/neowealth_hybrid/run.sh grade run_01 4
```

Repeat the same command to resume existing saved rows under the existing runner policy. Use a new tag for a fresh experiment. Four query workers run concurrently, with one DAG worker per question. The launcher allows query worker count changes in the same run tag. It rejects changes to the model, data, DAG worker count, or pipeline implementation in a nonempty run folder. Stop the existing run before restarting the same folder with a different worker count. Raw resumes skip saved rows according to the existing main runner policy; they do not promise to retry all saved failed questions.

DuckDB support loads physical columns, declared keys and foreign keys, bounded small text domains, validates SQL by native EXPLAIN, and serializes dates/decimals for reports. SQLite paths retain their existing behavior. SQLite-specific deterministic query shortcuts are bypassed for DuckDB, whose SQL is generated and repaired using native dialect instructions. Install `duckdb` in the interpreter used to launch the experiment (installed for /usr/bin/python3 in this workspace).

Validation: native DuckDB schema/query smoke checks and 11 backend/decomposition regression checks passed. No full Neowealth run or grading was launched during setup.

## Context retry of saved node failures

`retry_node_errors_context.py` freezes questions currently labelled `DAG_NODE_ERROR` from `without_context/run_01`. It reads question/reference rows from the evaluation input, without using reference answers in context preparation. The supplied `01_domain_and_business_rules.md` is compiled by the existing context agent, and only entries with valid source quotes, schema mappings and no detected conflicts are approved for this explicitly requested context experiment. Extraction is limited by the existing agent's candidate budget; it is not a guarantee that the full document is represented. Date-normalization contract limitations remain unchanged.

The separate context entry applies the document's mandatory DuckDB connection settings (`default_collation=nocase`, `default_null_order=nulls_last_on_asc_first_on_desc`) only to this experiment. The original no-context run remains unchanged. Selection and policy hashes are recorded in the output directory. New failures after the snapshot require a new run tag; restarting the same tag resumes the same frozen subset.

```bash
/usr/bin/python3 -u -B ablations/neowealth_hybrid/retry_node_errors_context.py --run-tag node_errors_context_01 --workers 4
```

Results and logs are under `runs/gemini_3_8_flash/with_context/node_errors_context_01`. No grader is launched for this retry subset. Because it selectively retries failures, its success rate must not be reported as a full-dataset with-context accuracy.

## Finish context repairs, then grade one combined full report

```bash
/usr/bin/python3 -u -B ablations/neowealth_hybrid/finish_context_merge_grade.py --workers 12 --grader-workers 4
```

This coordinator completes any remaining original questions without starting the original grader, expands the frozen context error subset to include every final node-error row while retaining saved context attempts, resumes context with twelve query workers, then writes and grades a separate full 768-row report under `runs/gemini_3_8_flash/merged_context_repairs/run_01`. It retains successful original outputs and replaces original failed rows only when the corresponding context retry executed successfully. The two source reports remain preserved. A merge summary and per-row source-condition columns track the adaptive recovery. This merged experiment is not a full with-context ablation. Grader 2 scoring remains unchanged.

Stop any independently running raw/context job before launching this coordinator. The coordinator lock prevents duplicate coordinator launches; it is not a lock on independently launched pipeline jobs.

## Full supplied context on grader PARTIAL/MISMATCH questions only

```bash
/usr/bin/python3 -u -B ablations/neowealth_hybrid/retry_graded_full_context.py --workers 12
```

This separate experiment waits until the combined grader CSV has all 768 rows, selects only `Original Grade` equal to `PARTIAL` or `MISMATCH`, and excludes the explicitly user-skipped question. It freezes the selected IDs and all 22 context sources: `01_domain_and_business_rules.md` plus every YAML in `primitves_updated_final`. No document is quarantined or truncated. Full source text is injected into every pipeline model request by an isolated adapter, instead of the capped entries-based context agent. This retains declared/inferred/observed provenance in the documents. Reference answers and grader reasons are not supplied as context. The extra context may substantially increase per-call tokens and latency; there is no guarantee of improvement and existing contract checks still apply.

Outputs: `runs/gemini_3_8_flash/with_context/partial_mismatch_full_context_01`, including the complete context bundle, source hashes, selection manifest, raw CSV and logs. Repeating the same command resumes the frozen subset; do not start a duplicate while the supervisor is active. No additional grader is launched by this job. The source combined grading and reports are unchanged. Report this as adaptive recovery, not an unbiased full-dataset accuracy experiment.
