# Proprietary models: metrics report

This report covers three pipeline-runner models and six baselines per model. Accuracy uses the final `gpt-5-mini` grade; grader cost is excluded because the requested inference cost is for pipeline generation.

## Definitions

- `Accuracy = MATCH answers / total questions × 100`
- `Token latency = total generation time in seconds × 1,000 / total output tokens`
- `Inference cost = Σ[(input tokens × input price / 1,000,000) + (output tokens × output price / 1,000,000)]`
- `Average inference cost per question = total inference cost / total questions`
- `Execution efficiency = MATCH answers / total execution time in seconds`

For parallel ensembles, generation time and token counts are sums across all branch calls. Branches execute concurrently, so that generation-time total is model-call time rather than end-to-end wall-clock time. Execution time is the sum of each row's `Elapsed Seconds` value.

## Pricing assumptions

Rates were checked on 2026-10-07. GPT-6.1-Sol uses OpenAI standard pricing; Gemini-3.8-Flash uses Google's paid introductory standard rate through 2026-12-31. The Qwen run used Amazon Bedrock Mantle in `us-east-1`; because AWS's public pricing table does not expose this exact 480B Mantle row in its static content, its cost is an explicitly provisional estimate using $0.45 input and $1.80 output per million tokens. Replace those two rates if the AWS bill shows a different contracted or service-tier rate.

| Model | Model ID | Input / 1M tokens | Output / 1M tokens | Cost status |
|---|---|---:|---:|---|
| GPT-6.1-Sol | `gpt-6.1-sol` | $2.00 | $10.00 | Published standard rate |
| Gemini-3.8-Flash | `gemini-3.8-flash` | $0.75 | $3.75 | Published introductory standard rate |
| Qwen3-Coder-480B | `qwen.qwen3-coder-480b-a35b-instruct` | $0.45 | $1.80 | Provisional estimate; verify against AWS billing |

Sources: [OpenAI GPT-6.1-Sol model pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing), [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/), and [AWS Qwen3-Coder-480B model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-qwen-qwen3-coder-480b-a35b-instruct.html).

## Model-level aggregate across six baselines

| Model | Questions | Correct | Accuracy | Input tokens | Output tokens | Generation time (s) | Token latency (ms/output token) | Total cost | Avg. cost/question | Execution time (s) | Correct/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-6.1-Sol | 6,000 | 3,048 | 50.80% | 161,522,500 | 3,373,048 | 97,312.840 | 28.850 | $356.775480 | $0.059462580 | 67,601.644 | 0.045088 |
| Gemini-3.8-Flash | 6,000 | 3,044 | 50.73% | 191,219,333 | 1,807,463 | 413,277.816 | 228.651 | $150.192486 | $0.025032081 | 282,717.584 | 0.010767 |
| Qwen3-Coder-480B | 6,000 | 2,436 | 40.60% | 175,906,393 | 1,792,095 | 104,125.860 | 58.103 | $82.383648 | $0.013730608 | 76,805.969 | 0.031716 |

## Baseline-level detail

| Model | Baseline | Questions | Correct | Accuracy | Input tokens | Output tokens | Generation time (s) | Token latency (ms/output token) | Total cost | Avg. cost/question | Execution time (s) | Correct/s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-6.1-Sol | Base SPARQL | 1,000 | 513 | 51.30% | 9,511,009 | 324,575 | 9,454.180 | 29.128 | $22.267768 | $0.022267768 | 9,665.486 | 0.053075 |
| GPT-6.1-Sol | Base SQL | 1,000 | 641 | 64.10% | 7,759,286 | 258,378 | 7,996.789 | 30.950 | $18.102352 | $0.018102352 | 8,080.254 | 0.079329 |
| GPT-6.1-Sol | GraphRAG Local | 1,000 | 68 | 6.80% | 75,368,631 | 409,660 | 11,249.720 | 27.461 | $154.833862 | $0.154833862 | 12,603.230 | 0.005395 |
| GPT-6.1-Sol | Parallel SPARQL | 1,000 | 494 | 49.40% | 27,797,345 | 1,103,814 | 32,019.889 | 29.008 | $66.632830 | $0.066632830 | 14,566.267 | 0.033914 |
| GPT-6.1-Sol | Parallel SQL | 1,000 | 633 | 63.30% | 23,301,135 | 776,621 | 22,639.497 | 29.151 | $54.368480 | $0.054368480 | 8,665.657 | 0.073047 |
| GPT-6.1-Sol | DAIL-SQL | 1,000 | 699 | 69.90% | 17,785,094 | 500,000 | 13,952.765 | 27.906 | $40.570188 | $0.040570188 | 14,020.750 | 0.049855 |
| Gemini-3.8-Flash | Base SPARQL | 1,000 | 516 | 51.60% | 10,346,968 | 178,112 | 43,121.519 | 242.103 | $8.428146 | $0.008428146 | 43,482.237 | 0.011867 |
| Gemini-3.8-Flash | Base SQL | 1,000 | 612 | 61.20% | 8,563,968 | 144,892 | 40,006.589 | 276.113 | $6.966321 | $0.006966321 | 40,723.053 | 0.015028 |
| Gemini-3.8-Flash | GraphRAG Local | 1,000 | 69 | 6.90% | 96,683,529 | 321,606 | 31,774.264 | 98.799 | $73.718669 | $0.073718669 | 32,953.260 | 0.002094 |
| Gemini-3.8-Flash | Parallel SPARQL | 1,000 | 516 | 51.60% | 30,185,918 | 452,449 | 144,838.027 | 320.120 | $24.336122 | $0.024336122 | 67,134.076 | 0.007686 |
| Gemini-3.8-Flash | Parallel SQL | 1,000 | 571 | 57.10% | 25,603,058 | 430,100 | 111,992.410 | 260.387 | $20.815168 | $0.020815168 | 56,640.031 | 0.010081 |
| Gemini-3.8-Flash | DAIL-SQL | 1,000 | 760 | 76.00% | 19,835,892 | 280,304 | 41,545.007 | 148.214 | $15.928059 | $0.015928059 | 41,784.927 | 0.018188 |
| Qwen3-Coder-480B | Base SPARQL | 1,000 | 314 | 31.40% | 9,751,100 | 170,908 | 10,889.800 | 63.717 | $4.695629 | $0.004695629 | 10,949.869 | 0.028676 |
| Qwen3-Coder-480B | Base SQL | 1,000 | 522 | 52.20% | 7,953,100 | 128,895 | 7,395.137 | 57.373 | $3.810906 | $0.003810906 | 7,771.396 | 0.067169 |
| Qwen3-Coder-480B | GraphRAG Local | 1,000 | 58 | 5.80% | 87,635,389 | 386,409 | 29,284.693 | 75.787 | $40.131461 | $0.040131461 | 30,343.028 | 0.001911 |
| Qwen3-Coder-480B | Parallel SPARQL | 1,000 | 345 | 34.50% | 28,437,300 | 477,269 | 27,704.423 | 58.048 | $13.655869 | $0.013655869 | 10,166.530 | 0.033935 |
| Qwen3-Coder-480B | Parallel SQL | 1,000 | 517 | 51.70% | 23,859,300 | 382,414 | 17,989.668 | 47.042 | $11.425030 | $0.011425030 | 6,414.139 | 0.080603 |
| Qwen3-Coder-480B | DAIL-SQL | 1,000 | 680 | 68.00% | 18,270,204 | 246,200 | 10,862.139 | 44.119 | $8.664752 | $0.008664752 | 11,161.007 | 0.060926 |
