# Grader agreement with GPT-5.6 TERA

Snapshot: 2026-10-02 12:44:43 IST

GPT-5 mini has the highest exact-label agreement with TERA, followed by GLM 5. This measures reproducibility of TERA judgments, not independently established grading accuracy.

## Method

- Each model has 1,000 saved rows across eight question types. Rows were joined by question type and Sample Row ID; duplicate keys were rejected.
- Question, Ground Truth and New Pipeline Result were verified identical to the reference on every row for every model.
- Reference labels come from Grade Status in pipelien_output_sql_gpt_oss_grader/*/graded_pipeline_v9_final_answers.csv. Its recorded model is gpt-5.6-terra. Candidate labels come from New Status in each model folder.
- TERA labels: 834 MATCH, 97 PARTIAL, 40 MISMATCH; 29 SKIPPED_EXECUTION_FAILURE rows excluded.
- Main ranking uses the same 950 questions with MATCH/PARTIAL/MISMATCH from every candidate and TERA. An additional 21 of TERA's 971 graded questions are excluded because at least one candidate returned an error or OTHER.
- Overlap means exactly the same label on the same question, including matching PARTIAL and MISMATCH decisions. It is not the percentage of answers marked MATCH.
- Candidate model errors and OTHER are separate from semantic disagreements. No APIs were called and no input reports were changed.

## Ranking on the same 950 questions

| Rank | Grader | Identical label | Different label | Agreement |
| --- | --- | ---: | ---: | ---: |
| 1 | GPT-5 mini | 917 | 33 | 96.53% |
| 2 | GLM 5 | 869 | 81 | 91.47% |
| 3 | Kimi K2.5 | 837 | 113 | 88.11% |
| 4 | Mistral Large 3 | 792 | 158 | 83.37% |
| 5 | DeepSeek V3.2 | 746 | 204 | 78.53% |
| 6 | Qwen3 235B | 697 | 253 | 73.37% |

## Agreement by question type on the common subset

| Question type | Questions | GPT-5 mini | GLM 5 | Kimi K2.5 | Mistral Large 3 | DeepSeek V3.2 | Qwen3 235B |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Benchmark | 118 | 100.00% (118/118) | 100.00% (118/118) | 100.00% (118/118) | 94.92% (112/118) | 82.20% (97/118) | 81.36% (96/118) |
| At Risk Critical | 110 | 93.64% (103/110) | 81.82% (90/110) | 82.73% (91/110) | 57.27% (63/110) | 50.00% (55/110) | 42.73% (47/110) |
| Batch Status | 123 | 100.00% (123/123) | 91.87% (113/123) | 92.68% (114/123) | 89.43% (110/123) | 78.86% (97/123) | 73.98% (91/123) |
| Enrichment Context | 120 | 96.67% (116/120) | 95.83% (115/120) | 89.17% (107/120) | 88.33% (106/120) | 92.50% (111/120) | 84.17% (101/120) |
| Multi Step Comparative | 117 | 94.02% (110/117) | 77.78% (91/117) | 74.36% (87/117) | 89.74% (105/117) | 77.78% (91/117) | 70.09% (82/117) |
| Reference Compliance | 121 | 93.39% (113/121) | 98.35% (119/121) | 94.21% (114/121) | 83.47% (101/121) | 82.64% (100/121) | 77.69% (94/121) |
| Scoring Quantitative | 118 | 94.07% (111/118) | 88.98% (105/118) | 77.97% (92/118) | 72.03% (85/118) | 68.64% (81/118) | 68.64% (81/118) |
| Temporal Transaction | 123 | 100.00% (123/123) | 95.93% (118/123) | 92.68% (114/123) | 89.43% (110/123) | 92.68% (114/123) | 85.37% (105/123) |

## Coverage across all 971 TERA-graded questions

Errors and OTHER count as no agreement in the common-denominator rate; the valid-label-only rate excludes them.

| Grader | Agrees | Different valid label | Error / OTHER | Agreement / 971 | Agreement on valid pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| GPT-5 mini | 934 | 36 | 1 | 96.19% | 934/970 (96.29%) |
| GLM 5 | 885 | 83 | 3 | 91.14% | 885/968 (91.43%) |
| Kimi K2.5 | 849 | 117 | 5 | 87.44% | 849/966 (87.89%) |
| Mistral Large 3 | 804 | 163 | 4 | 82.80% | 804/967 (83.14%) |
| DeepSeek V3.2 | 754 | 210 | 7 | 77.65% | 754/964 (78.22%) |
| Qwen3 235B | 704 | 266 | 1 | 72.50% | 704/970 (72.58%) |

## Decisions by TERA label

Each cell is the number receiving that candidate label. These tables use all 971 reference-graded questions.

### GPT-5 mini

Recorded model: `gpt-5-mini`.

| TERA label | Candidate MATCH | Candidate PARTIAL | Candidate MISMATCH | Error / OTHER |
| --- | ---: | ---: | ---: | ---: |
| MATCH | 816 | 17 | 0 | 1 |
| PARTIAL | 8 | 82 | 7 | 0 |
| MISMATCH | 0 | 4 | 36 | 0 |

Non-label outcomes: TOKEN_OUTPUT_ERROR: 1.

### GLM 5

Recorded model: `zai.glm-5`.

| TERA label | Candidate MATCH | Candidate PARTIAL | Candidate MISMATCH | Error / OTHER |
| --- | ---: | ---: | ---: | ---: |
| MATCH | 793 | 21 | 19 | 1 |
| PARTIAL | 4 | 52 | 39 | 2 |
| MISMATCH | 0 | 0 | 40 | 0 |

Non-label outcomes: TOKEN_OUTPUT_ERROR: 3.

### Kimi K2.5

Recorded model: `moonshotai.kimi-k2.5`.

| TERA label | Candidate MATCH | Candidate PARTIAL | Candidate MISMATCH | Error / OTHER |
| --- | ---: | ---: | ---: | ---: |
| MATCH | 759 | 65 | 6 | 4 |
| PARTIAL | 4 | 54 | 38 | 1 |
| MISMATCH | 0 | 4 | 36 | 0 |

Non-label outcomes: TOKEN_OUTPUT_ERROR: 5.

### Mistral Large 3

Recorded model: `mistral.mistral-large-3-675b-instruct`.

| TERA label | Candidate MATCH | Candidate PARTIAL | Candidate MISMATCH | Error / OTHER |
| --- | ---: | ---: | ---: | ---: |
| MATCH | 690 | 134 | 6 | 4 |
| PARTIAL | 13 | 82 | 2 | 0 |
| MISMATCH | 1 | 7 | 32 | 0 |

Non-label outcomes: TOKEN_OUTPUT_ERROR: 4.

### DeepSeek V3.2

Recorded model: `deepseek.v3.2`.

| TERA label | Candidate MATCH | Candidate PARTIAL | Candidate MISMATCH | Error / OTHER |
| --- | ---: | ---: | ---: | ---: |
| MATCH | 652 | 90 | 87 | 5 |
| PARTIAL | 5 | 68 | 22 | 2 |
| MISMATCH | 1 | 5 | 34 | 0 |

Non-label outcomes: OTHER: 2, TOKEN_OUTPUT_ERROR: 5.

### Qwen3 235B

Recorded model: `qwen.qwen3-235b-a22b-2507`.

| TERA label | Candidate MATCH | Candidate PARTIAL | Candidate MISMATCH | Error / OTHER |
| --- | ---: | ---: | ---: | ---: |
| MATCH | 624 | 105 | 104 | 1 |
| PARTIAL | 0 | 42 | 55 | 0 |
| MISMATCH | 0 | 2 | 38 | 0 |

Non-label outcomes: TOKEN_OUTPUT_ERROR: 1.

## Interpretation

GPT-5 mini is the closest substitute for TERA in this saved run. GLM 5 is the closest among the tested Bedrock graders. GLM 5 leads on Reference Compliance, while GPT-5 mini leads or ties for the highest agreement on the other seven types in the common subset.

GPT-5 mini agrees on 816/834 TERA MATCH labels, 82/97 PARTIAL labels, and 36/40 MISMATCH labels across the full eligible set. Its main differences are 17 TERA MATCH decisions changed to PARTIAL, eight PARTIAL decisions changed to MATCH, seven PARTIAL decisions changed to MISMATCH, and four MISMATCH decisions changed to PARTIAL; one additional row has TOKEN_OUTPUT_ERROR.

TERA is itself a model judge. Shared labels do not establish objective correctness; human adjudication of disagreements is required to measure grading accuracy. This is a comparison of saved runs, not a controlled benchmark proving that only model choice caused every difference in judgments.

## Source snapshot

SHA-256 hashes identify the exact report contents used.

| Relative report path | SHA-256 |
| --- | --- |
| `pipelien_output_sql_gpt_oss_grader\at_risk_critical\graded_pipeline_v9_final_answers.csv` | `25556bab637f9b0b99e3601bf9ecf2c8c37647f553dba3e77b1648011ad091f6` |
| `pipelien_output_sql_gpt_oss_grader\batch_status\graded_pipeline_v9_final_answers.csv` | `f2308aa78c823b73290f5f9dab5d6e68f5dae3a0759d79f66bb6b27376ede354` |
| `pipelien_output_sql_gpt_oss_grader\benchmark\graded_pipeline_v9_final_answers.csv` | `b2fe6abc9e856b2830723b5db4a35264757715f0495496a8a2f30da8b218e5f8` |
| `pipelien_output_sql_gpt_oss_grader\enrichment_context\graded_pipeline_v9_final_answers.csv` | `cc78e2c9ffa53e38c6cb9f14e71cc6f7c4a32d4db8ad88e38c898b27f1cb6ba8` |
| `pipelien_output_sql_gpt_oss_grader\multi_step_comparative\graded_pipeline_v9_final_answers.csv` | `3477a5455947265774f907f4905be4227d725b9bcb7470940bfcd504e994fb39` |
| `pipelien_output_sql_gpt_oss_grader\reference_compliance\graded_pipeline_v9_final_answers.csv` | `d1eddfd27d0065b62f94f9563e59fdc2b82f039e1434a5aa9383a050130d1cb8` |
| `pipelien_output_sql_gpt_oss_grader\scoring_quantitative\graded_pipeline_v9_final_answers.csv` | `81c5db4dc65a3be6c99286f8c4576757a4bf4f93fef8b7ed3e35e07e2b82b567` |
| `pipelien_output_sql_gpt_oss_grader\temporal_transaction\graded_pipeline_v9_final_answers.csv` | `02c380b528a18de1023f815bbeb172360108871c9a774b5d03a14b9aa9aa422f` |
| `pipelien_output_sql_gpt_5_mini\at_risk_critical\graded_openai_gpt-5-mini.csv` | `5dde1f483a35f5d9a3cd1a768c4eb7375987e03d00a0598b4bdfb0a9d847c7bd` |
| `pipelien_output_sql_gpt_5_mini\batch_status\graded_openai_gpt-5-mini.csv` | `b279b6462c7747ef4581f01ec06cc3a92332e33f52efa784faea833e6ac985c0` |
| `pipelien_output_sql_gpt_5_mini\benchmark\graded_openai_gpt-5-mini.csv` | `83e61214a34e775e17756dfc6fd65819194936bbb4615b4ea88b33c1c96a02cb` |
| `pipelien_output_sql_gpt_5_mini\enrichment_context\graded_openai_gpt-5-mini.csv` | `23b3cbc6edb921ee450499c50240120c07ce7d5dae607be359a6863ecb9d8e39` |
| `pipelien_output_sql_gpt_5_mini\multi_step_comparative\graded_openai_gpt-5-mini.csv` | `19f20e75eda1d10faf98474604844e2968f3990887cc68f8f558f3b1851e3b0a` |
| `pipelien_output_sql_gpt_5_mini\reference_compliance\graded_openai_gpt-5-mini.csv` | `5236c5a55281331b80d93f97456d3422f4486bf70de9f8a4d920a995d3014501` |
| `pipelien_output_sql_gpt_5_mini\scoring_quantitative\graded_openai_gpt-5-mini.csv` | `97f891e093c97a418f30da46d812783836f025c67faba3ed6329eea37a0bb658` |
| `pipelien_output_sql_gpt_5_mini\temporal_transaction\graded_openai_gpt-5-mini.csv` | `2fbd54f2d6e704e1973c9c1bae9ea5d08ef46eb3ac5dc01264343e73b1ad1c73` |
| `pipelien_output_sql_glm_5\at_risk_critical\graded_bedrock_zai.glm-5.csv` | `e3080164fb0b6f8314274777ffc6a9c8c54db18a1d906149180016ed2842e9c4` |
| `pipelien_output_sql_glm_5\batch_status\graded_bedrock_zai.glm-5.csv` | `0ace65dd578bfdc33e2f38f0a778367fb568124cdc3362d88bf39f400a80a15e` |
| `pipelien_output_sql_glm_5\benchmark\graded_bedrock_zai.glm-5.csv` | `0bc5b5ef3016d55f07d6e6621e653a7e12247d3ee59cc604dea92ff69f7cb647` |
| `pipelien_output_sql_glm_5\enrichment_context\graded_bedrock_zai.glm-5.csv` | `7b701478ac6d15ccf0fd173582d4a77e866ae170cab369d0d4c42d2bab745fb7` |
| `pipelien_output_sql_glm_5\multi_step_comparative\graded_bedrock_zai.glm-5.csv` | `1b151883d36669e1b936b27f4bb6e1518bf990c6564513f2d2109f288c52cf88` |
| `pipelien_output_sql_glm_5\reference_compliance\graded_bedrock_zai.glm-5.csv` | `98730960bd6009af53e43c5b6daa3701dbd09a3c5f60c1c579ebc9691926ab0f` |
| `pipelien_output_sql_glm_5\scoring_quantitative\graded_bedrock_zai.glm-5.csv` | `c39911941eb7c67a674566ed4db3c5d892272baa5c79f747a894588db79d58ea` |
| `pipelien_output_sql_glm_5\temporal_transaction\graded_bedrock_zai.glm-5.csv` | `c060d0ce5c028e1f18450309b80ef0e7e2c70ee0b7492cb1d86b72fe68e26293` |
| `pipelien_output_sql_kimi_k2_5\at_risk_critical\graded_bedrock_moonshotai.kimi-k2.5.csv` | `c9c19df767b2f7adaa552912c9ccd70a9e12d8e5d2d7e052fa793b43e604487f` |
| `pipelien_output_sql_kimi_k2_5\batch_status\graded_bedrock_moonshotai.kimi-k2.5.csv` | `d5b7bd120e973a78bde5bdf08b032ebae2ef592102c2f99464b5ff71eeea6a74` |
| `pipelien_output_sql_kimi_k2_5\benchmark\graded_bedrock_moonshotai.kimi-k2.5.csv` | `4ef2fffeb84adddb7cc2d4bc51d486b1ac382db668b01174c1dcdddb8ba1af7b` |
| `pipelien_output_sql_kimi_k2_5\enrichment_context\graded_bedrock_moonshotai.kimi-k2.5.csv` | `2c10a06fb6b536310104ef2b519ff5d7b76574004b1b3e44ffd914f65da5dd32` |
| `pipelien_output_sql_kimi_k2_5\multi_step_comparative\graded_bedrock_moonshotai.kimi-k2.5.csv` | `fe20a5eb67e14a83a2b55cb1f8f60122ae64f8aa655d68828575e9b2f6f094e9` |
| `pipelien_output_sql_kimi_k2_5\reference_compliance\graded_bedrock_moonshotai.kimi-k2.5.csv` | `60f4bd1c89c8d0b4c32ba2cefb3f9b5f837e77997546c1fbe1b3606dbca82f41` |
| `pipelien_output_sql_kimi_k2_5\scoring_quantitative\graded_bedrock_moonshotai.kimi-k2.5.csv` | `a70a32ad6c5f973f6009865b7e55b1295c82ffdfbb128f8726d7b8639922f086` |
| `pipelien_output_sql_kimi_k2_5\temporal_transaction\graded_bedrock_moonshotai.kimi-k2.5.csv` | `99fc30ab541dacea8b0c351ca690aa4b1b203b7a8e336ee0f9c37cd50cb36b1e` |
| `pipelien_output_sql_mistral_large_3\at_risk_critical\graded_bedrock_mistral.mistral-large-3-675b-instruct.csv` | `5418fe65dde1b697a7d47c0b7eaf5074116db80bca46836f51dc64654128ab64` |
| `pipelien_output_sql_mistral_large_3\batch_status\graded_bedrock_mistral.mistral-large-3-675b-instruct.csv` | `9b0ca0d5b42aa8fb75dcfac176005f0404faae4562d59b0b3a0e16ef4051728e` |
| `pipelien_output_sql_mistral_large_3\benchmark\graded_bedrock_mistral.mistral-large-3-675b-instruct.csv` | `f8e50a27a2fd068b8067d6033686518c7e8f211d29794589d612370d971c6f3d` |
| `pipelien_output_sql_mistral_large_3\enrichment_context\graded_bedrock_mistral.mistral-large-3-675b-instruct.csv` | `64954795b50407e183b61ad5ef33945447d326d7d7721982cdb1fc9829bf9c86` |
| `pipelien_output_sql_mistral_large_3\multi_step_comparative\graded_bedrock_mistral.mistral-large-3-675b-instruct.csv` | `f579211303f20364f4c54f6468b90fa10a4391d3191b41f818f9a6fb7c094cf5` |
| `pipelien_output_sql_mistral_large_3\reference_compliance\graded_bedrock_mistral.mistral-large-3-675b-instruct.csv` | `95462b3650ff81143fe7537603e65c1f47d3957406a2747f7762aa492867d1c6` |
| `pipelien_output_sql_mistral_large_3\scoring_quantitative\graded_bedrock_mistral.mistral-large-3-675b-instruct.csv` | `06fdd4ffa30c72a44a42a2bfb74ac369689d890296ce2ab49b4a194aa028216e` |
| `pipelien_output_sql_mistral_large_3\temporal_transaction\graded_bedrock_mistral.mistral-large-3-675b-instruct.csv` | `12fb7fe2ddca3096a726b7deaf672e7b8870ad04598340185a9136882af9d423` |
| `pipelien_output_sql_deepseek_v3_2\at_risk_critical\graded_bedrock_deepseek.v3.2.csv` | `63b51938f209e1a2921fc529457b784e2ad8549de33cb0570457a0fe7802af66` |
| `pipelien_output_sql_deepseek_v3_2\batch_status\graded_bedrock_deepseek.v3.2.csv` | `8e057501b22f2641d7fab1c67111c6422fa559dd9d33e41855aca0c8bcbb692b` |
| `pipelien_output_sql_deepseek_v3_2\benchmark\graded_bedrock_deepseek.v3.2.csv` | `20114a75fe70632978a96ba638acc4e83db0c59922a2a4362460510166d0279a` |
| `pipelien_output_sql_deepseek_v3_2\enrichment_context\graded_bedrock_deepseek.v3.2.csv` | `b2639cc0b0f8741ce543ab83d18f6a99baaa48412b4b2924d5fbb63ae3d448fa` |
| `pipelien_output_sql_deepseek_v3_2\multi_step_comparative\graded_bedrock_deepseek.v3.2.csv` | `4ac4ca7dd58c89bcd5c819052d93c645f6808c8ddd40377e8b6c013d2ee75421` |
| `pipelien_output_sql_deepseek_v3_2\reference_compliance\graded_bedrock_deepseek.v3.2.csv` | `151cbc3d2bcc34d0e0c656d49403d3334f12aec381358305062a6487a2ba5e1e` |
| `pipelien_output_sql_deepseek_v3_2\scoring_quantitative\graded_bedrock_deepseek.v3.2.csv` | `ac722b9fc885205e13d077b2ae161e4220337b438d6d7b41628fe74d90c96f07` |
| `pipelien_output_sql_deepseek_v3_2\temporal_transaction\graded_bedrock_deepseek.v3.2.csv` | `ae5ac4ed6ae515c1ca5c58232867d056a99610aacea35e31f7ff0143fc1d09eb` |
| `pipelien_output_sql_qwen3_235b_a22b\at_risk_critical\graded_bedrock_qwen.qwen3-235b-a22b-2507.csv` | `2def786170972701bf2a8763698f42ccebfebcb556b83ebe839dceb4fbab5706` |
| `pipelien_output_sql_qwen3_235b_a22b\batch_status\graded_bedrock_qwen.qwen3-235b-a22b-2507.csv` | `4dfe9af875a9e3adb7938563405b865c182cbce1b897297ddfed253de30849dd` |
| `pipelien_output_sql_qwen3_235b_a22b\benchmark\graded_bedrock_qwen.qwen3-235b-a22b-2507.csv` | `8bb0c8faa052ea4068aded6aed8182ca405b0136272179a306cc09b96837b847` |
| `pipelien_output_sql_qwen3_235b_a22b\enrichment_context\graded_bedrock_qwen.qwen3-235b-a22b-2507.csv` | `c521cf613901c8d358d286bbf950a0e3fce6639eb35f78f0dcd92174c05ca111` |
| `pipelien_output_sql_qwen3_235b_a22b\multi_step_comparative\graded_bedrock_qwen.qwen3-235b-a22b-2507.csv` | `ada2da18c95133198d3c90f278420690c1fcba47f4533a123dbdae3e40dd197c` |
| `pipelien_output_sql_qwen3_235b_a22b\reference_compliance\graded_bedrock_qwen.qwen3-235b-a22b-2507.csv` | `1687b54b50282d9fc6cd4664ea4d7532b563c06185df4a0761a56aab3fbc306a` |
| `pipelien_output_sql_qwen3_235b_a22b\scoring_quantitative\graded_bedrock_qwen.qwen3-235b-a22b-2507.csv` | `ee8c1b8240f9003f498e0c6217e66e06543ef12e6d9c167b46a57b31ccb3db3f` |
| `pipelien_output_sql_qwen3_235b_a22b\temporal_transaction\graded_bedrock_qwen.qwen3-235b-a22b-2507.csv` | `3af2bb7727b2f92d421294a68ba99869f67b9d6424fa2002311789b20e1c0e1e` |
