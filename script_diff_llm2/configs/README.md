Configuration is split into two layers:

- `models/`
  - provider and endpoint information for a model family
  - API key env names, base URL env name, region env names, default model ID
  - optional `stage_models` overrides so different pipeline stages can use different model IDs without changing Python code
  - `slug` controls the default output namespace

- `experiments/`
  - which model config to use
  - which benchmark file to run
  - which SQL asset and KG files to use
  - benchmark mode/split metadata
  - optional report basename
  - if `output_dir` is omitted, the runtime derives:
    `outputs/<model-slug>/<mode>/<split>/`

- `models/_template.yaml`
  - starting point for adding a new model
- `models/deepseek_v3_2.yaml`
  - concrete example for a Bedrock Mantle-hosted DeepSeek target model
- `models/qwen_qwen3_coder_480b_a35b_instruct.yaml`
  - concrete example for a Bedrock Mantle-hosted Qwen target model

- `experiments/_template.yaml`
  - starting point for adding a new experiment definition
- `experiments/deepseek_v3_2_all_train.yaml`
  - example experiment using the shared pipeline with DeepSeek config
- `experiments/qwen_qwen3_coder_480b_a35b_instruct_all_train.yaml`
  - example experiment using the shared pipeline with Qwen config

The canonical runner now resolves the pipeline from these YAML files instead of
hardcoding GPT-OSS-specific paths in Python.
