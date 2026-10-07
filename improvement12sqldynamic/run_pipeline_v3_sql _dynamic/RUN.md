# Improvement12 dynamic pipeline

See the experiment's [README.md](../README.md) for all local paths, cache preparation,
eight-terminal commands, resume, grading and metrics. Run commands from
`improvement12sqldynamic`; this package requires no older experiment folder.

## Planning and repair

After Query Understanding, Retrieve and Decompose, three complete DAG candidates
are generated using declared schema, knowledge and resolved requirements. Candidate
generation/evaluation receives no result rows or ground-truth answers. Each retrieval
branch uses Query_Spec, Generate, Pre_Scan_Validate, Scan and Processing_Spec.
Calculations and dependencies vary. Planned raw operands are enforced in Query_Spec;
processing projects source columns while preserving rows, values, duplicates and NULLs.

Invalid structures, fields and compiler contracts are rejected. Select the cheapest
candidate with reward >= 0.9, breaking ties by reward; otherwise select highest reward
and then cost. If evaluations are unavailable, select the cheapest locally valid
candidate and record the unavailable score. Cost is a heuristic, not measured money
or latency. DAG_PLANNER_MAX_ROUNDS supports 1, 2 or 3 (default 3). Failure to produce
any valid candidate triggers an explicitly recorded fixed-DAG fallback.

Successful calculations run once as DAG nodes with local final projection/rounding.
Processing has three total attempts. Calculation has four total attempts: upfront
execution plus at most three existing Final_Spec repairs. Repairs receive structured
errors, previous spec, execution IDs and available schemas. Failed-plan descendants
are skipped; repaired dependencies execute from original processed branch data.
The existing missing-field upstream repair routing is retained.

Debug DAG Planning records selection/fallback. Debug Final Spec, Debug Repair Log and
execution logs record repairs. Rate limits propagate to the runner, which saves the
retryable row and stops. Source/data identity prevents accidental mixing; explicit
recovery modes create backups and record source/configuration provenance.

## Paths relative to the experiment root

- Workbook: `datatset/wealth_management_1000_test_set_questions.xlsx`.
- Full answers: `datatset/216_questions_full_results.json`.
- Combined output: `outputs/full_run/raw_pipeline.csv`.
- Category output: `outputs/question_types/<type>/raw_pipeline_v9.csv`.
- Direct default output: `outputs/direct_run/raw_pipeline.csv`.
- Combined cache/runtime: `outputs/full_run/knowledge_cache` and `outputs/full_run/runtime`.
- Shared category/direct cache/runtime: `.runtime/knowledge_v3` and `.runtime`.
- Version: `aop-improvement12-v3-dynamic`.

The legacy resume_442.py filename reads actual input manifests. This workbook has
1,000 questions. PIPELINE_SUCCESS confirms execution, not answer correctness.
