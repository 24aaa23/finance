# Which runs to preserve or review

This guide refers to the inventory dated 16 October 2026. No deletion is authorized or performed. See [the complete inventory](README.md) and [primary reports](primary_reports.csv).

## Preserve for the paper

| Experiment | Location within script_diff_llm2 | What exists |
|---|---|---|
| Main hybrid, six graded model/context conditions | `ablations/v5_test1000/runs/{gpt_oss_120b,deepseek_v3_2,gemma_3_27b_it}/{without_context,with_context}/reliability_v6_01/` | Each has 1,000 raw and 1,000 graded rows. Preserve raw/graded pairs. |
| Alternative DeepSeek grader | `ablations/v5_test1000/runs/deepseek_v3_2/without_context/reliability_v6_01/graded_pipeline_grader3_gpt_5_mini.csv` | 1,000 rows, 810 matches; separate from grader 2 with 806 matches. |
| Improvement 10 SQL-only, four completed models | `ablations/improvement10_models/runs/{gpt_oss_120b,deepseek_v3_2,gemma_3_27b_it,qwen3_coder_480b}/run_01/parallel_workers4/` | Four raw/graded pairs, 1,000 rows each. |
| Improvement 11 KG-only | `ablations/improvement11_gpt_oss_120b/runs/azure_gpt_oss_120b/azure_resume8_01/parallel_workers8/` | Raw: 1,000 rows; graded: 829 rows. Grading is incomplete. |
| Original generic v5 result | `outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5/` | Raw/graded Terra pair; 811 matches in 1,000 graded rows. Different grader from current Mini runs. |
| Earlier context-v5 result | `outputs/openai_gpt_oss_120b/all/test1000/context_v5_01/` | Full raw + Mini graded pair; 5-row Terra grade is separate/incomplete. |
| Measurement sample | `ablations/v5_test1000/measurement/runs/sample40_01/` | Six complete 40-row samples for GPT-OSS/DeepSeek/Gemma; Kimi without context 40, with context only 2. Keep summaries and usage evidence. |
| Final NeoWealth adaptive result | `ablations/neowealth_hybrid/runs/gemini_3_8_flash/merged_full_context_repairs/run_01/` | 768 graded rows: 573 MATCH, 40 PARTIAL, 151 MISMATCH, 4 grader errors. |
| NeoWealth provenance | Same experiment: `without_context/run_01/`, `with_context/node_errors_context_01/`, `merged_context_repairs/run_01/`, `with_context/partial_mismatch_full_context_01/` | Original 768 rows; initial error retry 168; intermediate merged 768 raw/graded; expanded-context retry 321 raw/graded. Preserve context files, selection/merge manifests and source reports. |

## Incomplete experiments to archive or resume

These have distinct results. They are not proven redundant just because they are incomplete.

| Experiment | Saved raw rows | Grading |
|---|---:|---|
| Main SQL-only GPT-OSS with context, Bedrock | 1,000 | No graded CSV found |
| Main SQL-only GPT-OSS without context, Azure | 900 | No graded CSV found |
| Main SQL-only DeepSeek with context | 364 | No graded CSV found |
| Improvement10/11 hybrid GPT-OSS, Bedrock | 371 | No graded CSV found |
| Improvement10/11 hybrid GPT-OSS, Azure | 52 | No graded CSV found |
| Gemini on original WMI, with context | 259 | No graded CSV found |
| Gemini on original WMI, without context | 335 | No graded CSV found |
| Improvement 10 Kimi, parallel run | 345 | No graded CSV found |
| Main hybrid Kimi, with context, reliability_v6_01 | 666 | No graded CSV found |
| Main hybrid Kimi, without context, reliability_v6_01 | 1,000 | No graded CSV found |
| Main hybrid Qwen, each context condition | 1,000 each | No graded CSV found |

## Review first for cleanup

- `worker_*` and shard raw/debug CSVs: only remove after confirming the complete merged output contains all records you need. Do not delete their input CSVs if you plan to resume.
- `seed.csv` and `before_*` reports: preserve resume dependencies or archive the whole finished run; there are several exact seed/original duplicates.
- Improvement 10 early sequential reports: DeepSeek 83 rows, Gemma 62, GPT-OSS 87; completed 1,000-row parallel reports exist separately. The early rows may still be seed/provenance records.
- Azure connection smoke: one row, useful for diagnostics only.
- Old `generic_no_rules_v1`, `v2`, `v4`, early reruns and training variants: archive if not used in ablation/error-analysis claims. They are different experiments, not exact duplicates.
- Old training output variants are the largest cleanup area. The three `train_442_ab2` raw/graded files alone occupy about 384 MB, but contain distinct results/graders.

## Important distinction

The report counts 310 pipeline CSV artifacts, not 310 independent experiments. This includes raw/graded versions, workers, debug files, backups and measurement samples. Only 168 are classified as primary reports; consult the generated inventory for the current exact count. Complete row counts do not imply successful answers or fully resolved grades.
