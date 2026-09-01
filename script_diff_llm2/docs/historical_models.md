# Historical Model Directories

These historical experiment snapshots now live under `historical_models/`:

- `historical_models/deepseek.v3.2-abhinav/`
- `historical_models/google.gemini-3.6-flash-aman/`
- `historical_models/google.gemma-3-27b-it-aman/`
- `historical_models/mistral.mistral-large-3-675b-instruct-aman/`
- `historical_models/moonshotai.kimi-k2-thinking-aditya/`
- `historical_models/nvidia.nemotron-super-3-120b-aman/`
- `historical_models/openai.gpt-5.5-aman/`
- `historical_models/openai.gpt-oss-120b-aman/`
- `historical_models/qwen.qwen3-coder-480b-a35b-instruct-aman/`
- `historical_models/qwen.qwen3-vl-235b-a22b-instruct-aman/`

Reason:

- many legacy runners inside those directories compute the repo root from a fixed
  directory depth or older relative path assumptions
- the archived trees were grouped under one parent so the repository root reflects
  the canonical architecture more clearly
- the known `Path(...).resolve()` GPT-OSS wrappers were patched to remain
  location-independent after the move

Current canonical organization is:

- shared runtime:
  - `src/script_diff_llm/`
- model config:
  - `configs/models/`
- experiment config:
  - `configs/experiments/`
- SQL asset manifests:
  - `data/sql/`
- KG assets:
  - `data/kg/`
- generated model comparison/smoke artifacts:
  - `analysis/output/`

So active development is organized around the shared canonical layout, while the
older per-model snapshots are archived under `historical_models/`.
