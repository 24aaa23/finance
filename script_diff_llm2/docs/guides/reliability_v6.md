# Generic reliability v6: reruns and grading

Changes address invalid decomposition operators/bindings, local subquery validation,
physical-ID aliases, context visibility and deterministic SQL generation. The original
TERA-named grader is unchanged; the new wrapper selects GPT-5 Mini and schedules
its original row workflow with bounded concurrency.

Run from:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
```

Existing API environment files and Fuseki must be available. Sources remain the
1000-question workbook, SQL DB, schema, instance file and alias map listed in
`ablations/v5_test1000/README.md`; the launcher prints absolute paths.

## Recommended pilot before eight complete reruns

This selects 25 questions from the existing 1000-query workbook. It does not create
or switch databases/datasets. It runs raw pipelines only, one run at a time:

```bash
bash -e <<'SH'
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
for model in gpt_oss_120b deepseek_v3_2 gemma_3_27b_it kimi_k2_thinking; do
  for condition in without_context with_context; do
    bash ablations/v5_test1000/run_raw.sh "$model" "$condition" \
      --run-tag reliability_v6_pilot --limit 25 --offset 0 --workers 4
  done
 done
SH
```

Review each run's `raw_pipeline.csv`, `pipeline.log` and `domain_context_state.json`.
A first-25-question pilot verifies startup and basic execution; it does not establish
accuracy on comparative questions or on the complete benchmark. Additional windows
can be selected with `--offset` and `--limit` in a separate run tag.

## Complete raw reruns, all four models and both conditions

```bash
bash -e <<'SH'
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
for model in gpt_oss_120b deepseek_v3_2 gemma_3_27b_it kimi_k2_thinking; do
  for condition in without_context with_context; do
    bash ablations/v5_test1000/run_raw.sh "$model" "$condition" \
      --run-tag reliability_v6_01 --limit 1000 --offset 0 --workers 4
  done
 done
SH
```

The grader is not started. Repeating the command skips completed raw rows and reuses
successful context preparation. Do not mix these new implementations into `run_01`;
the resume guard rejects code/configuration changes when existing raw rows are present.
Changing the query window, model, worker settings or sources also requires a fresh tag.

A single run example:

```bash
bash ablations/v5_test1000/run_raw.sh gemma_3_27b_it with_context \
  --run-tag reliability_v6_01 --workers 4
```

## Context preparation and real business definitions

The current `phase0_business_rules.md` is evaluation-derived and remains excluded.
With-context runs can use eligible terminology from `domain_intro.prompt`; they are
not automatically using its operational formulas or thresholds. Context is not
expected to increase accuracy merely because files were supplied.

To prepare one model's context without querying the benchmark:

```bash
bash ablations/v5_test1000/run_raw.sh gpt_oss_120b with_context \
  --run-tag reliability_v6_01 --prepare-context-only
```

The log prints a review JSON path. The prepared cache may be reused by subsequent
runs with identical source documents, observed schema evidence and model.
Version 6 invalidates older context preparations and approvals. Review source ownership,
conflicts and formulas using database-owner documentation, not benchmark answers.
See `docs/domain_context.md` for `runners/review_domain_context.py` approval commands.

For independently verified production documents and an approval file, use explicit paths:

```bash
bash ablations/v5_test1000/run_raw.sh gpt_oss_120b with_context \
  --run-tag reliability_v6_reviewed_rules_01 \
  --domain-intro /absolute/path/to/database_intro.prompt \
  --business-rules /absolute/path/to/source_owned_business_rules.md \
  --approval-file /absolute/path/to/this_model_context_approval.json
```

Do not remove evaluation markers from the old Phase0 file to bypass exclusion.
Approvals bind to the model/document/schema fingerprint and entry evidence; prepare
and review each applicable bundle. Missing optional file paths in the normal generic
runner still preserve no-context operation; this ablation's explicit with-context
condition requires a usable active bundle and fails before questions if none exists.

## GPT-5 Mini grading after raw runs

Two requests may be in flight per report, but reports below are graded sequentially
so eight graders do not contend for the same quota. Use `--workers 1` if throttling
or timeouts increase. Never start two scripts against the same graded output CSV.

```bash
bash -e <<'SH'
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
for model in gpt_oss_120b deepseek_v3_2 gemma_3_27b_it kimi_k2_thinking; do
  for condition in without_context with_context; do
    /usr/bin/python3 -u ablations/v5_test1000/grade_only.py \
      "$model" "$condition" --run-tag reliability_v6_01 --workers 2
  done
 done
SH
```

Repeating resumes completed judgments and retries grader errors under the original
resume rules. The scoring prompts, tolerance, reference inputs and grading policy
have not changed. Quota exhaustion still requires available API quota; additional
concurrency cannot solve it.

For any existing raw report, including older v5 runs:

```bash
/usr/bin/python3 -u runners/grade_gpt_5_mini.py \
  --raw "$PWD/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5/raw_pipeline.csv" \
  --output "$PWD/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5/graded_pipeline_gpt_5_mini.csv" \
  --workers 2
```

The standalone wrapper locks its output against other parallel-wrapper instances.
The old sequential script does not participate in this lock, so ensure it is stopped
before grading the same CSV through this wrapper. Raw input and graded output must differ.

## Speed controls and checkpoint tradeoffs

The new SQL compilers avoid a Generate call for eligible plans while retaining
validation and execution. Their eligibility is conservative; multi-source plans
continue through existing generation/recovery.

Start with four raw query workers. If API capacity permits, use `--workers 6` in a
fresh run tag. More concurrency can increase rate limiting and may slow the run.
`--save-every 5` reduces repeated full-CSV writes; after an abrupt process kill, up
 to four rows since the last checkpoint can require rerunning. The default is one,
which preserves every completed row in the incremental CSV.

For grading, `--workers 2` retains per-completed-row checkpoints. The standalone
wrapper also supports `--save-every`, with the same checkpoint tradeoff. Neither
runner shortens prompts or bypasses scoring/validation to improve speed.

The implemented fixes and offline replays do not guarantee an accuracy target.
Measure final match counts and wall times using the same grader on both conditions.
