# All graded CSVs — run descriptions and match accuracy

**82 graded CSVs** under `script_diff_llm2`, including one derived analysis extract. No files changed or deleted.

**Accuracy = MATCH rows / all rows currently saved in that file × 100.** PARTIAL and errors are not matches; grader errors remain in the denominator. Partial reports are not full-benchmark accuracy. Historical graders, datasets and modes differ, so these percentages are not a controlled ranking. Descriptions use folder/filename identity; unknown historical graders are explicitly marked.

The NeoWealth final combined accuracy is adaptive recovery, not a single-pass full-context experiment. The 321-row result is a selected failure subset. The backend-pattern extract is derived analysis, not a new run.

| ID | One-line run heading | MATCH / saved rows | Match accuracy |
|---|---|---:|---:|
| G01 | [Improvement 10 SQL-only — DeepSeek V3.2, four-worker run; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/improvement10_models/runs/deepseek_v3_2/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv) | 744/1000 | 74.40% |
| G02 | [Improvement 10 SQL-only — Gemma 3 27B IT, four-worker run; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/improvement10_models/runs/gemma_3_27b_it/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv) | 319/1000 | 31.90% |
| G03 | [Improvement 10 SQL-only — GPT-OSS 120B, four-worker run; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/improvement10_models/runs/gpt_oss_120b/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv) | 781/1000 | 78.10% |
| G04 | [Improvement 10 SQL-only — Qwen3 Coder 480B, four-worker run; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/improvement10_models/runs/qwen3_coder_480b/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv) | 704/1000 | 70.40% |
| G05 | [Improvement 11 KG-only — Azure GPT-OSS 120B, eight-worker continuation; grader 2 / GPT-5 mini (partial grading)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/improvement11_gpt_oss_120b/runs/azure_gpt_oss_120b/azure_resume8_01/parallel_workers8/graded_pipeline_gpt_5_mini.csv) | 650/829 | 78.41% |
| G06 | [NeoWealth Gemini hybrid — combined original run and initial context error repairs](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/neowealth_hybrid/runs/gemini_3_8_flash/merged_context_repairs/run_01/graded_pipeline_gpt_5_mini.csv) | 443/768 | 57.68% |
| G07 | [NeoWealth Gemini hybrid — final combined adaptive result after full-context repairs](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/neowealth_hybrid/runs/gemini_3_8_flash/merged_full_context_repairs/run_01/graded_pipeline_gpt_5_mini.csv) | 573/768 | 74.61% |
| G08 | [NeoWealth Gemini hybrid — 321 previously PARTIAL/MISMATCH questions retried with all 22 context documents](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/neowealth_hybrid/runs/gemini_3_8_flash/with_context/partial_mismatch_full_context_01/graded_pipeline_gpt_5_mini.csv) | 130/321 | 40.50% |
| G09 | [Main hybrid — DeepSeek V3.2, with context, reliability_v6_01; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/deepseek_v3_2/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv) | 783/1000 | 78.30% |
| G10 | [Main hybrid — DeepSeek V3.2, without context, reliability_v6_01; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/deepseek_v3_2/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv) | 806/1000 | 80.60% |
| G11 | [Main hybrid — DeepSeek V3.2, without context, reliability_v6_01; grader 3 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/deepseek_v3_2/without_context/reliability_v6_01/graded_pipeline_grader3_gpt_5_mini.csv) | 810/1000 | 81.00% |
| G12 | [Main hybrid — DeepSeek V3.2, without context, early run_01; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/deepseek_v3_2/without_context/run_01/graded_pipeline_gpt_5_mini.csv) | 359/601 | 59.73% |
| G13 | [Main hybrid — Gemma 3 27B IT, with context, reliability_v6_01; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/gemma_3_27b_it/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv) | 609/1000 | 60.90% |
| G14 | [Main hybrid — Gemma 3 27B IT, without context, reliability_v6_01; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/gemma_3_27b_it/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv) | 613/1000 | 61.30% |
| G15 | [Main hybrid — GPT-OSS 120B, with context, reliability_v6_01; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/gpt_oss_120b/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv) | 790/1000 | 79.00% |
| G16 | [Main hybrid — GPT-OSS 120B, without context, reliability_v6_01; grader 2 / GPT-5 mini](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/gpt_oss_120b/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv) | 789/1000 | 78.90% |
| G17 | [Derived backend-pattern analysis of the GPT-OSS 442-question semantic-fix training report (not an independent run)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/analysis/output/graded_backend_pattern_openai_gpt_oss_120b_all_train_442_semanticfix_terra.csv) | 221/442 | 50.00% |
| G18 | [Historical DeepSeek V3.2, all mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/all/train/output/graded_deepseek_v3_2_all_train.csv) | 107/442 | 24.21% |
| G19 | [Historical DeepSeek V3.2, all mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/all/train/output/graded_deepseek_v3_2_all_train_direct_llm_gpt_5_6_sol.csv) | 196/442 | 44.34% |
| G20 | [Historical DeepSeek V3.2, all mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/all/train/output/graded_deepseek_v3_2_all_train_gptoss_grader_check.csv) | 154/442 | 34.84% |
| G21 | [Historical DeepSeek V3.2, hybrid mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/hybrid/train/output/graded_deepseek_v3_2_hybrid_train.csv) | 111/442 | 25.11% |
| G22 | [Historical DeepSeek V3.2, hybrid mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/hybrid/train/output/graded_deepseek_v3_2_hybrid_train_direct_llm_gpt_5_6_sol.csv) | 65/442 | 14.71% |
| G23 | [Historical DeepSeek V3.2, hybrid mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/hybrid/train/output/graded_deepseek_v3_2_hybrid_train_gptoss_grader_check.csv) | 171/442 | 38.69% |
| G24 | [Historical Gemini 3.6 Flash, all mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemini-3.6-flash-aman/all/train/output/graded_google_gemini_3_6_flash_all_train.csv) | 130/442 | 29.41% |
| G25 | [Historical Gemini 3.6 Flash, all mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemini-3.6-flash-aman/all/train/output/graded_google_gemini_3_6_flash_all_train_direct_llm_gpt_5_6_sol.csv) | 60/442 | 13.57% |
| G26 | [Historical Gemini 3.6 Flash, all mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemini-3.6-flash-aman/all/train/output/graded_google_gemini_3_6_flash_all_train_gptoss_grader_check.csv) | 186/442 | 42.08% |
| G27 | [Historical Gemma 3 27B IT, all mode, test split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/all/test/output/graded_google_gemma_3_27b_it_all_test_gptoss_grader_check.csv) | 1/12 | 8.33% |
| G28 | [Historical Gemma 3 27B IT, all mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/all/train/output/graded_google_gemma_3_27b_it_all_train.csv) | 25/442 | 5.66% |
| G29 | [Historical Gemma 3 27B IT, all mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/all/train/output/graded_google_gemma_3_27b_it_all_train_direct_llm_gpt_5_6_sol.csv) | 98/442 | 22.17% |
| G30 | [Historical Gemma 3 27B IT, all mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/all/train/output/graded_google_gemma_3_27b_it_all_train_gptoss_grader_check.csv) | 32/442 | 7.24% |
| G31 | [Historical Gemma 3 27B IT, hybrid mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/hybrid/train/output/graded_google_gemma_3_27b_it_hybrid_train.csv) | 125/442 | 28.28% |
| G32 | [Historical Gemma 3 27B IT, hybrid mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/hybrid/train/output/graded_google_gemma_3_27b_it_hybrid_train_direct_llm_gpt_5_6_sol.csv) | 60/442 | 13.57% |
| G33 | [Historical Gemma 3 27B IT, hybrid mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/hybrid/train/output/graded_google_gemma_3_27b_it_hybrid_train_gptoss_grader_check.csv) | 169/442 | 38.24% |
| G34 | [Historical Mistral Large 3 675B, all mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/all/train/output/graded_mistral_mistral_large_3_675b_instruct_all_train.csv) | 59/442 | 13.35% |
| G35 | [Historical Mistral Large 3 675B, all mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/all/train/output/graded_mistral_mistral_large_3_675b_instruct_all_train_direct_llm_gpt_5_6_sol.csv) | 138/442 | 31.22% |
| G36 | [Historical Mistral Large 3 675B, all mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/all/train/output/graded_mistral_mistral_large_3_675b_instruct_all_train_gptoss_grader_check.csv) | 98/442 | 22.17% |
| G37 | [Historical Mistral Large 3 675B, hybrid mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/hybrid/train/output/graded_mistral_mistral_large_3_675b_instruct_hybrid_train.csv) | 124/442 | 28.05% |
| G38 | [Historical Mistral Large 3 675B, hybrid mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/hybrid/train/output/graded_mistral_mistral_large_3_675b_instruct_hybrid_train_direct_llm_gpt_5_6_sol.csv) | 56/442 | 12.67% |
| G39 | [Historical Mistral Large 3 675B, hybrid mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/hybrid/train/output/graded_mistral_mistral_large_3_675b_instruct_hybrid_train_gptoss_grader_check.csv) | 179/442 | 40.50% |
| G40 | [Historical Nemotron Super 3 120B, all mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/all/train/output/graded_nvidia_nemotron_super_3_120b_all_train.csv) | 63/442 | 14.25% |
| G41 | [Historical Nemotron Super 3 120B, all mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/all/train/output/graded_nvidia_nemotron_super_3_120b_all_train_direct_llm_gpt_5_6_sol.csv) | 71/442 | 16.06% |
| G42 | [Historical Nemotron Super 3 120B, all mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/all/train/output/graded_nvidia_nemotron_super_3_120b_all_train_gptoss_grader_check.csv) | 103/442 | 23.30% |
| G43 | [Historical Nemotron Super 3 120B, hybrid mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/hybrid/train/output/graded_nvidia_nemotron_super_3_120b_hybrid_train.csv) | 97/442 | 21.95% |
| G44 | [Historical Nemotron Super 3 120B, hybrid mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/hybrid/train/output/graded_nvidia_nemotron_super_3_120b_hybrid_train_direct_llm_gpt_5_6_sol.csv) | 37/442 | 8.37% |
| G45 | [Historical Nemotron Super 3 120B, hybrid mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/hybrid/train/output/graded_nvidia_nemotron_super_3_120b_hybrid_train_gptoss_grader_check.csv) | 129/442 | 29.19% |
| G46 | [Historical GPT-OSS 120B, all mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/openai.gpt-oss-120b-aman/all/train/output/graded_openai_gpt_oss_120b_all_train.csv) | 1/2 | 50.00% |
| G47 | [Historical GPT-OSS 120B, all mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/openai.gpt-oss-120b-aman/all/train/output/graded_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_sol.csv) | 80/442 | 18.10% |
| G48 | [Historical GPT-OSS 120B, all mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/openai.gpt-oss-120b-aman/all/train/output/graded_openai_gpt_oss_120b_all_train_gptoss_grader_check.csv) | 190/442 | 42.99% |
| G49 | [Historical Qwen3 Coder 480B, all mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_all_train.csv) | 40/442 | 9.05% |
| G50 | [Historical Qwen3 Coder 480B, all mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_all_train_direct_llm_gpt_5_6_sol.csv) | 55/442 | 12.44% |
| G51 | [Historical Qwen3 Coder 480B, all mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_all_train_gptoss_grader_check.csv) | 69/442 | 15.61% |
| G52 | [Historical Qwen3 Coder 480B, hybrid mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_hybrid_train.csv) | 126/442 | 28.51% |
| G53 | [Historical Qwen3 Coder 480B, hybrid mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_hybrid_train_direct_llm_gpt_5_6_sol.csv) | 50/442 | 11.31% |
| G54 | [Historical Qwen3 Coder 480B, hybrid mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_hybrid_train_gptoss_grader_check.csv) | 172/442 | 38.91% |
| G55 | [Historical Qwen3 VL 235B, all mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/all/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_all_train.csv) | 49/442 | 11.09% |
| G56 | [Historical Qwen3 VL 235B, all mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/all/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_all_train_direct_llm_gpt_5_6_sol.csv) | 55/442 | 12.44% |
| G57 | [Historical Qwen3 VL 235B, all mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/all/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_all_train_gptoss_grader_check.csv) | 77/442 | 17.42% |
| G58 | [Historical Qwen3 VL 235B, hybrid mode, train split — original grading (grader not identified by filename)](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_hybrid_train.csv) | 127/442 | 28.73% |
| G59 | [Historical Qwen3 VL 235B, hybrid mode, train split — GPT-5.6 Sol direct regrade](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_hybrid_train_direct_llm_gpt_5_6_sol.csv) | 51/442 | 11.54% |
| G60 | [Historical Qwen3 VL 235B, hybrid mode, train split — GPT-OSS grader check](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_hybrid_train_gptoss_grader_check.csv) | 175/442 | 39.59% |
| G61 | [GPT-OSS hybrid context_v5_01 — GPT-5 mini grading](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/context_v5_01/graded_pipeline_gpt_5_mini.csv) | 785/1000 | 78.50% |
| G62 | [GPT-OSS hybrid context_v5_01 — Terra grading, five-row fragment](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/context_v5_01/graded_pipeline_tera.csv) | 5/5 | 100.00% |
| G63 | [GPT-OSS generic no-rules hybrid v1_20261003 — Terra grading](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v1_20261003/graded_pipeline_tera.csv) | 579/1000 | 57.90% |
| G64 | [GPT-OSS generic no-rules hybrid v2_20261003 — Terra grading](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v2_20261003/graded_pipeline_tera.csv) | 721/1000 | 72.10% |
| G65 | [GPT-OSS generic no-rules hybrid v4 — Terra grading](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v4/graded_pipeline_tera.csv) | 646/1000 | 64.60% |
| G66 | [GPT-OSS generic no-rules hybrid v5 — Terra grading](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5/graded_pipeline_tera.csv) | 811/1000 | 81.10% |
| G67 | [GPT-OSS original 1,000-query test — direct LLM Terra grading](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/graded_pipeline_1000_test_direct_llm_terra.csv) | 698/1000 | 69.80% |
| G68 | [GPT-OSS original 1,000-query rerun — grader 2 file](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/graded_pipeline_openai_gpt_oss_120b_all_test1000_rerun_grader2.csv) | 637/1000 | 63.70% |
| G69 | [GPT-OSS early rerun 2026-10-03 02:31:43 — Terra, partial report](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/rerun_20261003_023143/graded_pipeline_tera.csv) | 282/865 | 32.60% |
| G70 | [GPT-OSS Original final605 training variant — Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_final605_terra.csv) | 269/605 | 44.46% |
| G71 | [GPT-OSS 442-question training ab2 variant — regraded](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_ab2_regraded.csv) | 188/442 | 42.53% |
| G72 | [GPT-OSS 442-question training ab2 variant — Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_ab2_terra.csv) | 126/442 | 28.51% |
| G73 | [GPT-OSS 442-training semantic ablation — 30-row fragment, Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_semantic_ab_terra.csv) | 12/30 | 40.00% |
| G74 | [GPT-OSS 442-question training semantic fix — Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_semanticfix_terra.csv) | 240/442 | 54.30% |
| G75 | [GPT-OSS 442-question training semantic fix v2 — Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_semanticfix_v2_terra.csv) | 215/442 | 48.64% |
| G76 | [GPT-OSS Original 442-question training run — Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_terra.csv) | 105/442 | 23.76% |
| G77 | [GPT-OSS 442-training ab1 variant — 78-row fragment, Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_terra_ab1.csv) | 19/78 | 24.36% |
| G78 | [GPT-OSS 442-question training ab14 variant — Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_terra_ab14.csv) | 108/442 | 24.43% |
| G79 | [GPT-OSS 605-question fast training variant — Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_fast_terra.csv) | 312/605 | 51.57% |
| G80 | [GPT-OSS 605-question final training run — direct LLM Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_final_direct_llm_terra.csv) | 374/605 | 61.82% |
| G81 | [GPT-OSS 605-question final semantic training variant — Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_final_semantic_terra.csv) | 308/605 | 50.91% |
| G82 | [GPT-OSS 605-question final training run — Terra](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_final_terra.csv) | 339/605 | 56.03% |

## File-by-file paths

### G01 — Improvement 10 SQL-only — DeepSeek V3.2, four-worker run; grader 2 / GPT-5 mini

**Match accuracy: 74.40% (744/1000).** PARTIAL: 155; MISMATCH: 97; other/error statuses: 4.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/improvement10_models/runs/deepseek_v3_2/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv)

`ablations/improvement10_models/runs/deepseek_v3_2/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv`

### G02 — Improvement 10 SQL-only — Gemma 3 27B IT, four-worker run; grader 2 / GPT-5 mini

**Match accuracy: 31.90% (319/1000).** PARTIAL: 91; MISMATCH: 585; other/error statuses: 5.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/improvement10_models/runs/gemma_3_27b_it/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv)

`ablations/improvement10_models/runs/gemma_3_27b_it/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv`

### G03 — Improvement 10 SQL-only — GPT-OSS 120B, four-worker run; grader 2 / GPT-5 mini

**Match accuracy: 78.10% (781/1000).** PARTIAL: 127; MISMATCH: 87; other/error statuses: 5.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/improvement10_models/runs/gpt_oss_120b/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv)

`ablations/improvement10_models/runs/gpt_oss_120b/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv`

### G04 — Improvement 10 SQL-only — Qwen3 Coder 480B, four-worker run; grader 2 / GPT-5 mini

**Match accuracy: 70.40% (704/1000).** PARTIAL: 127; MISMATCH: 140; other/error statuses: 29.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/improvement10_models/runs/qwen3_coder_480b/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv)

`ablations/improvement10_models/runs/qwen3_coder_480b/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv`

### G05 — Improvement 11 KG-only — Azure GPT-OSS 120B, eight-worker continuation; grader 2 / GPT-5 mini (partial grading)

**Match accuracy: 78.41% (650/829).** PARTIAL: 85; MISMATCH: 34; other/error statuses: 60.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/improvement11_gpt_oss_120b/runs/azure_gpt_oss_120b/azure_resume8_01/parallel_workers8/graded_pipeline_gpt_5_mini.csv)

`ablations/improvement11_gpt_oss_120b/runs/azure_gpt_oss_120b/azure_resume8_01/parallel_workers8/graded_pipeline_gpt_5_mini.csv`

### G06 — NeoWealth Gemini hybrid — combined original run and initial context error repairs

**Match accuracy: 57.68% (443/768).** PARTIAL: 114; MISMATCH: 207; other/error statuses: 4.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/neowealth_hybrid/runs/gemini_3_8_flash/merged_context_repairs/run_01/graded_pipeline_gpt_5_mini.csv)

`ablations/neowealth_hybrid/runs/gemini_3_8_flash/merged_context_repairs/run_01/graded_pipeline_gpt_5_mini.csv`

### G07 — NeoWealth Gemini hybrid — final combined adaptive result after full-context repairs

**Match accuracy: 74.61% (573/768).** PARTIAL: 40; MISMATCH: 151; other/error statuses: 4.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/neowealth_hybrid/runs/gemini_3_8_flash/merged_full_context_repairs/run_01/graded_pipeline_gpt_5_mini.csv)

`ablations/neowealth_hybrid/runs/gemini_3_8_flash/merged_full_context_repairs/run_01/graded_pipeline_gpt_5_mini.csv`

### G08 — NeoWealth Gemini hybrid — 321 previously PARTIAL/MISMATCH questions retried with all 22 context documents

**Match accuracy: 40.50% (130/321).** PARTIAL: 40; MISMATCH: 151; other/error statuses: 0.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/neowealth_hybrid/runs/gemini_3_8_flash/with_context/partial_mismatch_full_context_01/graded_pipeline_gpt_5_mini.csv)

`ablations/neowealth_hybrid/runs/gemini_3_8_flash/with_context/partial_mismatch_full_context_01/graded_pipeline_gpt_5_mini.csv`

### G09 — Main hybrid — DeepSeek V3.2, with context, reliability_v6_01; grader 2 / GPT-5 mini

**Match accuracy: 78.30% (783/1000).** PARTIAL: 92; MISMATCH: 100; other/error statuses: 25.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/deepseek_v3_2/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv)

`ablations/v5_test1000/runs/deepseek_v3_2/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv`

### G10 — Main hybrid — DeepSeek V3.2, without context, reliability_v6_01; grader 2 / GPT-5 mini

**Match accuracy: 80.60% (806/1000).** PARTIAL: 89; MISMATCH: 80; other/error statuses: 25.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/deepseek_v3_2/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv)

`ablations/v5_test1000/runs/deepseek_v3_2/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv`

### G11 — Main hybrid — DeepSeek V3.2, without context, reliability_v6_01; grader 3 / GPT-5 mini

**Match accuracy: 81.00% (810/1000).** PARTIAL: 83; MISMATCH: 82; other/error statuses: 25.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/deepseek_v3_2/without_context/reliability_v6_01/graded_pipeline_grader3_gpt_5_mini.csv)

`ablations/v5_test1000/runs/deepseek_v3_2/without_context/reliability_v6_01/graded_pipeline_grader3_gpt_5_mini.csv`

### G12 — Main hybrid — DeepSeek V3.2, without context, early run_01; grader 2 / GPT-5 mini

**Match accuracy: 59.73% (359/601).** PARTIAL: 35; MISMATCH: 151; other/error statuses: 56.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/deepseek_v3_2/without_context/run_01/graded_pipeline_gpt_5_mini.csv)

`ablations/v5_test1000/runs/deepseek_v3_2/without_context/run_01/graded_pipeline_gpt_5_mini.csv`

### G13 — Main hybrid — Gemma 3 27B IT, with context, reliability_v6_01; grader 2 / GPT-5 mini

**Match accuracy: 60.90% (609/1000).** PARTIAL: 85; MISMATCH: 288; other/error statuses: 18.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/gemma_3_27b_it/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv)

`ablations/v5_test1000/runs/gemma_3_27b_it/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv`

### G14 — Main hybrid — Gemma 3 27B IT, without context, reliability_v6_01; grader 2 / GPT-5 mini

**Match accuracy: 61.30% (613/1000).** PARTIAL: 82; MISMATCH: 292; other/error statuses: 13.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/gemma_3_27b_it/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv)

`ablations/v5_test1000/runs/gemma_3_27b_it/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv`

### G15 — Main hybrid — GPT-OSS 120B, with context, reliability_v6_01; grader 2 / GPT-5 mini

**Match accuracy: 79.00% (790/1000).** PARTIAL: 93; MISMATCH: 114; other/error statuses: 3.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/gpt_oss_120b/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv)

`ablations/v5_test1000/runs/gpt_oss_120b/with_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv`

### G16 — Main hybrid — GPT-OSS 120B, without context, reliability_v6_01; grader 2 / GPT-5 mini

**Match accuracy: 78.90% (789/1000).** PARTIAL: 109; MISMATCH: 101; other/error statuses: 1.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/ablations/v5_test1000/runs/gpt_oss_120b/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv)

`ablations/v5_test1000/runs/gpt_oss_120b/without_context/reliability_v6_01/graded_pipeline_gpt_5_mini.csv`

### G17 — Derived backend-pattern analysis of the GPT-OSS 442-question semantic-fix training report (not an independent run)

**Match accuracy: 50.00% (221/442).** PARTIAL: 139; MISMATCH: 52; other/error statuses: 30.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/analysis/output/graded_backend_pattern_openai_gpt_oss_120b_all_train_442_semanticfix_terra.csv)

`analysis/output/graded_backend_pattern_openai_gpt_oss_120b_all_train_442_semanticfix_terra.csv`

### G18 — Historical DeepSeek V3.2, all mode, train split — original grading (grader not identified by filename)

**Match accuracy: 24.21% (107/442).** PARTIAL: 59; MISMATCH: 204; other/error statuses: 72.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/all/train/output/graded_deepseek_v3_2_all_train.csv)

`historical_models/deepseek.v3.2-abhinav/all/train/output/graded_deepseek_v3_2_all_train.csv`

### G19 — Historical DeepSeek V3.2, all mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 44.34% (196/442).** PARTIAL: 88; MISMATCH: 98; other/error statuses: 60.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/all/train/output/graded_deepseek_v3_2_all_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/deepseek.v3.2-abhinav/all/train/output/graded_deepseek_v3_2_all_train_direct_llm_gpt_5_6_sol.csv`

### G20 — Historical DeepSeek V3.2, all mode, train split — GPT-OSS grader check

**Match accuracy: 34.84% (154/442).** PARTIAL: 123; MISMATCH: 93; other/error statuses: 72.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/all/train/output/graded_deepseek_v3_2_all_train_gptoss_grader_check.csv)

`historical_models/deepseek.v3.2-abhinav/all/train/output/graded_deepseek_v3_2_all_train_gptoss_grader_check.csv`

### G21 — Historical DeepSeek V3.2, hybrid mode, train split — original grading (grader not identified by filename)

**Match accuracy: 25.11% (111/442).** PARTIAL: 98; MISMATCH: 210; other/error statuses: 23.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/hybrid/train/output/graded_deepseek_v3_2_hybrid_train.csv)

`historical_models/deepseek.v3.2-abhinav/hybrid/train/output/graded_deepseek_v3_2_hybrid_train.csv`

### G22 — Historical DeepSeek V3.2, hybrid mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 14.71% (65/442).** PARTIAL: 32; MISMATCH: 39; other/error statuses: 306.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/hybrid/train/output/graded_deepseek_v3_2_hybrid_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/deepseek.v3.2-abhinav/hybrid/train/output/graded_deepseek_v3_2_hybrid_train_direct_llm_gpt_5_6_sol.csv`

### G23 — Historical DeepSeek V3.2, hybrid mode, train split — GPT-OSS grader check

**Match accuracy: 38.69% (171/442).** PARTIAL: 161; MISMATCH: 87; other/error statuses: 23.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/deepseek.v3.2-abhinav/hybrid/train/output/graded_deepseek_v3_2_hybrid_train_gptoss_grader_check.csv)

`historical_models/deepseek.v3.2-abhinav/hybrid/train/output/graded_deepseek_v3_2_hybrid_train_gptoss_grader_check.csv`

### G24 — Historical Gemini 3.6 Flash, all mode, train split — original grading (grader not identified by filename)

**Match accuracy: 29.41% (130/442).** PARTIAL: 85; MISMATCH: 206; other/error statuses: 21.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemini-3.6-flash-aman/all/train/output/graded_google_gemini_3_6_flash_all_train.csv)

`historical_models/google.gemini-3.6-flash-aman/all/train/output/graded_google_gemini_3_6_flash_all_train.csv`

### G25 — Historical Gemini 3.6 Flash, all mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 13.57% (60/442).** PARTIAL: 26; MISMATCH: 25; other/error statuses: 331.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemini-3.6-flash-aman/all/train/output/graded_google_gemini_3_6_flash_all_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/google.gemini-3.6-flash-aman/all/train/output/graded_google_gemini_3_6_flash_all_train_direct_llm_gpt_5_6_sol.csv`

### G26 — Historical Gemini 3.6 Flash, all mode, train split — GPT-OSS grader check

**Match accuracy: 42.08% (186/442).** PARTIAL: 159; MISMATCH: 76; other/error statuses: 21.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemini-3.6-flash-aman/all/train/output/graded_google_gemini_3_6_flash_all_train_gptoss_grader_check.csv)

`historical_models/google.gemini-3.6-flash-aman/all/train/output/graded_google_gemini_3_6_flash_all_train_gptoss_grader_check.csv`

### G27 — Historical Gemma 3 27B IT, all mode, test split — GPT-OSS grader check

**Match accuracy: 8.33% (1/12).** PARTIAL: 7; MISMATCH: 4; other/error statuses: 0.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/all/test/output/graded_google_gemma_3_27b_it_all_test_gptoss_grader_check.csv)

`historical_models/google.gemma-3-27b-it-aman/all/test/output/graded_google_gemma_3_27b_it_all_test_gptoss_grader_check.csv`

### G28 — Historical Gemma 3 27B IT, all mode, train split — original grading (grader not identified by filename)

**Match accuracy: 5.66% (25/442).** PARTIAL: 39; MISMATCH: 259; other/error statuses: 119.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/all/train/output/graded_google_gemma_3_27b_it_all_train.csv)

`historical_models/google.gemma-3-27b-it-aman/all/train/output/graded_google_gemma_3_27b_it_all_train.csv`

### G29 — Historical Gemma 3 27B IT, all mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 22.17% (98/442).** PARTIAL: 78; MISMATCH: 158; other/error statuses: 108.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/all/train/output/graded_google_gemma_3_27b_it_all_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/google.gemma-3-27b-it-aman/all/train/output/graded_google_gemma_3_27b_it_all_train_direct_llm_gpt_5_6_sol.csv`

### G30 — Historical Gemma 3 27B IT, all mode, train split — GPT-OSS grader check

**Match accuracy: 7.24% (32/442).** PARTIAL: 119; MISMATCH: 172; other/error statuses: 119.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/all/train/output/graded_google_gemma_3_27b_it_all_train_gptoss_grader_check.csv)

`historical_models/google.gemma-3-27b-it-aman/all/train/output/graded_google_gemma_3_27b_it_all_train_gptoss_grader_check.csv`

### G31 — Historical Gemma 3 27B IT, hybrid mode, train split — original grading (grader not identified by filename)

**Match accuracy: 28.28% (125/442).** PARTIAL: 88; MISMATCH: 207; other/error statuses: 22.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/hybrid/train/output/graded_google_gemma_3_27b_it_hybrid_train.csv)

`historical_models/google.gemma-3-27b-it-aman/hybrid/train/output/graded_google_gemma_3_27b_it_hybrid_train.csv`

### G32 — Historical Gemma 3 27B IT, hybrid mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 13.57% (60/442).** PARTIAL: 31; MISMATCH: 48; other/error statuses: 303.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/hybrid/train/output/graded_google_gemma_3_27b_it_hybrid_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/google.gemma-3-27b-it-aman/hybrid/train/output/graded_google_gemma_3_27b_it_hybrid_train_direct_llm_gpt_5_6_sol.csv`

### G33 — Historical Gemma 3 27B IT, hybrid mode, train split — GPT-OSS grader check

**Match accuracy: 38.24% (169/442).** PARTIAL: 156; MISMATCH: 95; other/error statuses: 22.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/google.gemma-3-27b-it-aman/hybrid/train/output/graded_google_gemma_3_27b_it_hybrid_train_gptoss_grader_check.csv)

`historical_models/google.gemma-3-27b-it-aman/hybrid/train/output/graded_google_gemma_3_27b_it_hybrid_train_gptoss_grader_check.csv`

### G34 — Historical Mistral Large 3 675B, all mode, train split — original grading (grader not identified by filename)

**Match accuracy: 13.35% (59/442).** PARTIAL: 60; MISMATCH: 199; other/error statuses: 124.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/all/train/output/graded_mistral_mistral_large_3_675b_instruct_all_train.csv)

`historical_models/mistral.mistral-large-3-675b-instruct-aman/all/train/output/graded_mistral_mistral_large_3_675b_instruct_all_train.csv`

### G35 — Historical Mistral Large 3 675B, all mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 31.22% (138/442).** PARTIAL: 91; MISMATCH: 99; other/error statuses: 114.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/all/train/output/graded_mistral_mistral_large_3_675b_instruct_all_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/mistral.mistral-large-3-675b-instruct-aman/all/train/output/graded_mistral_mistral_large_3_675b_instruct_all_train_direct_llm_gpt_5_6_sol.csv`

### G36 — Historical Mistral Large 3 675B, all mode, train split — GPT-OSS grader check

**Match accuracy: 22.17% (98/442).** PARTIAL: 118; MISMATCH: 102; other/error statuses: 124.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/all/train/output/graded_mistral_mistral_large_3_675b_instruct_all_train_gptoss_grader_check.csv)

`historical_models/mistral.mistral-large-3-675b-instruct-aman/all/train/output/graded_mistral_mistral_large_3_675b_instruct_all_train_gptoss_grader_check.csv`

### G37 — Historical Mistral Large 3 675B, hybrid mode, train split — original grading (grader not identified by filename)

**Match accuracy: 28.05% (124/442).** PARTIAL: 95; MISMATCH: 201; other/error statuses: 22.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/hybrid/train/output/graded_mistral_mistral_large_3_675b_instruct_hybrid_train.csv)

`historical_models/mistral.mistral-large-3-675b-instruct-aman/hybrid/train/output/graded_mistral_mistral_large_3_675b_instruct_hybrid_train.csv`

### G38 — Historical Mistral Large 3 675B, hybrid mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 12.67% (56/442).** PARTIAL: 28; MISMATCH: 39; other/error statuses: 319.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/hybrid/train/output/graded_mistral_mistral_large_3_675b_instruct_hybrid_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/mistral.mistral-large-3-675b-instruct-aman/hybrid/train/output/graded_mistral_mistral_large_3_675b_instruct_hybrid_train_direct_llm_gpt_5_6_sol.csv`

### G39 — Historical Mistral Large 3 675B, hybrid mode, train split — GPT-OSS grader check

**Match accuracy: 40.50% (179/442).** PARTIAL: 165; MISMATCH: 76; other/error statuses: 22.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/mistral.mistral-large-3-675b-instruct-aman/hybrid/train/output/graded_mistral_mistral_large_3_675b_instruct_hybrid_train_gptoss_grader_check.csv)

`historical_models/mistral.mistral-large-3-675b-instruct-aman/hybrid/train/output/graded_mistral_mistral_large_3_675b_instruct_hybrid_train_gptoss_grader_check.csv`

### G40 — Historical Nemotron Super 3 120B, all mode, train split — original grading (grader not identified by filename)

**Match accuracy: 14.25% (63/442).** PARTIAL: 58; MISMATCH: 267; other/error statuses: 54.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/all/train/output/graded_nvidia_nemotron_super_3_120b_all_train.csv)

`historical_models/nvidia.nemotron-super-3-120b-aman/all/train/output/graded_nvidia_nemotron_super_3_120b_all_train.csv`

### G41 — Historical Nemotron Super 3 120B, all mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 16.06% (71/442).** PARTIAL: 29; MISMATCH: 75; other/error statuses: 267.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/all/train/output/graded_nvidia_nemotron_super_3_120b_all_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/nvidia.nemotron-super-3-120b-aman/all/train/output/graded_nvidia_nemotron_super_3_120b_all_train_direct_llm_gpt_5_6_sol.csv`

### G42 — Historical Nemotron Super 3 120B, all mode, train split — GPT-OSS grader check

**Match accuracy: 23.30% (103/442).** PARTIAL: 136; MISMATCH: 149; other/error statuses: 54.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/all/train/output/graded_nvidia_nemotron_super_3_120b_all_train_gptoss_grader_check.csv)

`historical_models/nvidia.nemotron-super-3-120b-aman/all/train/output/graded_nvidia_nemotron_super_3_120b_all_train_gptoss_grader_check.csv`

### G43 — Historical Nemotron Super 3 120B, hybrid mode, train split — original grading (grader not identified by filename)

**Match accuracy: 21.95% (97/442).** PARTIAL: 86; MISMATCH: 235; other/error statuses: 24.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/hybrid/train/output/graded_nvidia_nemotron_super_3_120b_hybrid_train.csv)

`historical_models/nvidia.nemotron-super-3-120b-aman/hybrid/train/output/graded_nvidia_nemotron_super_3_120b_hybrid_train.csv`

### G44 — Historical Nemotron Super 3 120B, hybrid mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 8.37% (37/442).** PARTIAL: 32; MISMATCH: 46; other/error statuses: 327.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/hybrid/train/output/graded_nvidia_nemotron_super_3_120b_hybrid_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/nvidia.nemotron-super-3-120b-aman/hybrid/train/output/graded_nvidia_nemotron_super_3_120b_hybrid_train_direct_llm_gpt_5_6_sol.csv`

### G45 — Historical Nemotron Super 3 120B, hybrid mode, train split — GPT-OSS grader check

**Match accuracy: 29.19% (129/442).** PARTIAL: 162; MISMATCH: 127; other/error statuses: 24.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/nvidia.nemotron-super-3-120b-aman/hybrid/train/output/graded_nvidia_nemotron_super_3_120b_hybrid_train_gptoss_grader_check.csv)

`historical_models/nvidia.nemotron-super-3-120b-aman/hybrid/train/output/graded_nvidia_nemotron_super_3_120b_hybrid_train_gptoss_grader_check.csv`

### G46 — Historical GPT-OSS 120B, all mode, train split — original grading (grader not identified by filename)

**Match accuracy: 50.00% (1/2).** PARTIAL: 0; MISMATCH: 1; other/error statuses: 0.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/openai.gpt-oss-120b-aman/all/train/output/graded_openai_gpt_oss_120b_all_train.csv)

`historical_models/openai.gpt-oss-120b-aman/all/train/output/graded_openai_gpt_oss_120b_all_train.csv`

### G47 — Historical GPT-OSS 120B, all mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 18.10% (80/442).** PARTIAL: 33; MISMATCH: 54; other/error statuses: 275.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/openai.gpt-oss-120b-aman/all/train/output/graded_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/openai.gpt-oss-120b-aman/all/train/output/graded_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_sol.csv`

### G48 — Historical GPT-OSS 120B, all mode, train split — GPT-OSS grader check

**Match accuracy: 42.99% (190/442).** PARTIAL: 136; MISMATCH: 95; other/error statuses: 21.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/openai.gpt-oss-120b-aman/all/train/output/graded_openai_gpt_oss_120b_all_train_gptoss_grader_check.csv)

`historical_models/openai.gpt-oss-120b-aman/all/train/output/graded_openai_gpt_oss_120b_all_train_gptoss_grader_check.csv`

### G49 — Historical Qwen3 Coder 480B, all mode, train split — original grading (grader not identified by filename)

**Match accuracy: 9.05% (40/442).** PARTIAL: 72; MISMATCH: 157; other/error statuses: 173.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_all_train.csv)

`historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_all_train.csv`

### G50 — Historical Qwen3 Coder 480B, all mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 12.44% (55/442).** PARTIAL: 43; MISMATCH: 39; other/error statuses: 305.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_all_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_all_train_direct_llm_gpt_5_6_sol.csv`

### G51 — Historical Qwen3 Coder 480B, all mode, train split — GPT-OSS grader check

**Match accuracy: 15.61% (69/442).** PARTIAL: 110; MISMATCH: 90; other/error statuses: 173.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_all_train_gptoss_grader_check.csv)

`historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/all/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_all_train_gptoss_grader_check.csv`

### G52 — Historical Qwen3 Coder 480B, hybrid mode, train split — original grading (grader not identified by filename)

**Match accuracy: 28.51% (126/442).** PARTIAL: 95; MISMATCH: 198; other/error statuses: 23.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_hybrid_train.csv)

`historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_hybrid_train.csv`

### G53 — Historical Qwen3 Coder 480B, hybrid mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 11.31% (50/442).** PARTIAL: 23; MISMATCH: 37; other/error statuses: 332.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_hybrid_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_hybrid_train_direct_llm_gpt_5_6_sol.csv`

### G54 — Historical Qwen3 Coder 480B, hybrid mode, train split — GPT-OSS grader check

**Match accuracy: 38.91% (172/442).** PARTIAL: 154; MISMATCH: 93; other/error statuses: 23.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_hybrid_train_gptoss_grader_check.csv)

`historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_coder_480b_a35b_instruct_hybrid_train_gptoss_grader_check.csv`

### G55 — Historical Qwen3 VL 235B, all mode, train split — original grading (grader not identified by filename)

**Match accuracy: 11.09% (49/442).** PARTIAL: 48; MISMATCH: 134; other/error statuses: 211.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/all/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_all_train.csv)

`historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/all/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_all_train.csv`

### G56 — Historical Qwen3 VL 235B, all mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 12.44% (55/442).** PARTIAL: 34; MISMATCH: 45; other/error statuses: 308.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/all/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_all_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/all/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_all_train_direct_llm_gpt_5_6_sol.csv`

### G57 — Historical Qwen3 VL 235B, all mode, train split — GPT-OSS grader check

**Match accuracy: 17.42% (77/442).** PARTIAL: 85; MISMATCH: 69; other/error statuses: 211.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/all/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_all_train_gptoss_grader_check.csv)

`historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/all/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_all_train_gptoss_grader_check.csv`

### G58 — Historical Qwen3 VL 235B, hybrid mode, train split — original grading (grader not identified by filename)

**Match accuracy: 28.73% (127/442).** PARTIAL: 98; MISMATCH: 195; other/error statuses: 22.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_hybrid_train.csv)

`historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_hybrid_train.csv`

### G59 — Historical Qwen3 VL 235B, hybrid mode, train split — GPT-5.6 Sol direct regrade

**Match accuracy: 11.54% (51/442).** PARTIAL: 32; MISMATCH: 35; other/error statuses: 324.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_hybrid_train_direct_llm_gpt_5_6_sol.csv)

`historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_hybrid_train_direct_llm_gpt_5_6_sol.csv`

### G60 — Historical Qwen3 VL 235B, hybrid mode, train split — GPT-OSS grader check

**Match accuracy: 39.59% (175/442).** PARTIAL: 166; MISMATCH: 79; other/error statuses: 22.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_hybrid_train_gptoss_grader_check.csv)

`historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/hybrid/train/output/graded_qwen_qwen3_vl_235b_a22b_instruct_hybrid_train_gptoss_grader_check.csv`

### G61 — GPT-OSS hybrid context_v5_01 — GPT-5 mini grading

**Match accuracy: 78.50% (785/1000).** PARTIAL: 81; MISMATCH: 129; other/error statuses: 5.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/context_v5_01/graded_pipeline_gpt_5_mini.csv)

`outputs/openai_gpt_oss_120b/all/test1000/context_v5_01/graded_pipeline_gpt_5_mini.csv`

### G62 — GPT-OSS hybrid context_v5_01 — Terra grading, five-row fragment

**Match accuracy: 100.00% (5/5).** PARTIAL: 0; MISMATCH: 0; other/error statuses: 0.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/context_v5_01/graded_pipeline_tera.csv)

`outputs/openai_gpt_oss_120b/all/test1000/context_v5_01/graded_pipeline_tera.csv`

### G63 — GPT-OSS generic no-rules hybrid v1_20261003 — Terra grading

**Match accuracy: 57.90% (579/1000).** PARTIAL: 45; MISMATCH: 365; other/error statuses: 11.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v1_20261003/graded_pipeline_tera.csv)

`outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v1_20261003/graded_pipeline_tera.csv`

### G64 — GPT-OSS generic no-rules hybrid v2_20261003 — Terra grading

**Match accuracy: 72.10% (721/1000).** PARTIAL: 57; MISMATCH: 215; other/error statuses: 7.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v2_20261003/graded_pipeline_tera.csv)

`outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v2_20261003/graded_pipeline_tera.csv`

### G65 — GPT-OSS generic no-rules hybrid v4 — Terra grading

**Match accuracy: 64.60% (646/1000).** PARTIAL: 44; MISMATCH: 303; other/error statuses: 7.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v4/graded_pipeline_tera.csv)

`outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v4/graded_pipeline_tera.csv`

### G66 — GPT-OSS generic no-rules hybrid v5 — Terra grading

**Match accuracy: 81.10% (811/1000).** PARTIAL: 61; MISMATCH: 126; other/error statuses: 2.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5/graded_pipeline_tera.csv)

`outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5/graded_pipeline_tera.csv`

### G67 — GPT-OSS original 1,000-query test — direct LLM Terra grading

**Match accuracy: 69.80% (698/1000).** PARTIAL: 165; MISMATCH: 104; other/error statuses: 33.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/graded_pipeline_1000_test_direct_llm_terra.csv)

`outputs/openai_gpt_oss_120b/all/test1000/graded_pipeline_1000_test_direct_llm_terra.csv`

### G68 — GPT-OSS original 1,000-query rerun — grader 2 file

**Match accuracy: 63.70% (637/1000).** PARTIAL: 137; MISMATCH: 202; other/error statuses: 24.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/graded_pipeline_openai_gpt_oss_120b_all_test1000_rerun_grader2.csv)

`outputs/openai_gpt_oss_120b/all/test1000/graded_pipeline_openai_gpt_oss_120b_all_test1000_rerun_grader2.csv`

### G69 — GPT-OSS early rerun 2026-10-03 02:31:43 — Terra, partial report

**Match accuracy: 32.60% (282/865).** PARTIAL: 38; MISMATCH: 537; other/error statuses: 8.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/test1000/rerun_20261003_023143/graded_pipeline_tera.csv)

`outputs/openai_gpt_oss_120b/all/test1000/rerun_20261003_023143/graded_pipeline_tera.csv`

### G70 — GPT-OSS Original final605 training variant — Terra

**Match accuracy: 44.46% (269/605).** PARTIAL: 211; MISMATCH: 57; other/error statuses: 68.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_final605_terra.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_final605_terra.csv`

### G71 — GPT-OSS 442-question training ab2 variant — regraded

**Match accuracy: 42.53% (188/442).** PARTIAL: 167; MISMATCH: 60; other/error statuses: 27.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_ab2_regraded.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_ab2_regraded.csv`

### G72 — GPT-OSS 442-question training ab2 variant — Terra

**Match accuracy: 28.51% (126/442).** PARTIAL: 94; MISMATCH: 195; other/error statuses: 27.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_ab2_terra.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_ab2_terra.csv`

### G73 — GPT-OSS 442-training semantic ablation — 30-row fragment, Terra

**Match accuracy: 40.00% (12/30).** PARTIAL: 8; MISMATCH: 7; other/error statuses: 3.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_semantic_ab_terra.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_semantic_ab_terra.csv`

### G74 — GPT-OSS 442-question training semantic fix — Terra

**Match accuracy: 54.30% (240/442).** PARTIAL: 132; MISMATCH: 41; other/error statuses: 29.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_semanticfix_terra.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_semanticfix_terra.csv`

### G75 — GPT-OSS 442-question training semantic fix v2 — Terra

**Match accuracy: 48.64% (215/442).** PARTIAL: 131; MISMATCH: 65; other/error statuses: 31.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_semanticfix_v2_terra.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_semanticfix_v2_terra.csv`

### G76 — GPT-OSS Original 442-question training run — Terra

**Match accuracy: 23.76% (105/442).** PARTIAL: 70; MISMATCH: 181; other/error statuses: 86.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_terra.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_terra.csv`

### G77 — GPT-OSS 442-training ab1 variant — 78-row fragment, Terra

**Match accuracy: 24.36% (19/78).** PARTIAL: 12; MISMATCH: 31; other/error statuses: 16.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_terra_ab1.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_terra_ab1.csv`

### G78 — GPT-OSS 442-question training ab14 variant — Terra

**Match accuracy: 24.43% (108/442).** PARTIAL: 76; MISMATCH: 172; other/error statuses: 86.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_terra_ab14.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_openai_gpt_oss_120b_all_train_442_terra_ab14.csv`

### G79 — GPT-OSS 605-question fast training variant — Terra

**Match accuracy: 51.57% (312/605).** PARTIAL: 166; MISMATCH: 56; other/error statuses: 71.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_fast_terra.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_fast_terra.csv`

### G80 — GPT-OSS 605-question final training run — direct LLM Terra

**Match accuracy: 61.82% (374/605).** PARTIAL: 113; MISMATCH: 80; other/error statuses: 38.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_final_direct_llm_terra.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_final_direct_llm_terra.csv`

### G81 — GPT-OSS 605-question final semantic training variant — Terra

**Match accuracy: 50.91% (308/605).** PARTIAL: 171; MISMATCH: 56; other/error statuses: 70.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_final_semantic_terra.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_final_semantic_terra.csv`

### G82 — GPT-OSS 605-question final training run — Terra

**Match accuracy: 56.03% (339/605).** PARTIAL: 135; MISMATCH: 40; other/error statuses: 91.

[Open graded CSV](/home/kritik/Desktop/neosapiens/finance/script_diff_llm2/outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_final_terra.csv)

`outputs/openai_gpt_oss_120b/all/train/graded_pipeline_605_final_terra.csv`

