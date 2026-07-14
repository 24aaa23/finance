# General AOP mismatch experiment

- `random_300_mismatch.csv` contains 300 rows sampled from the `All_Queries` sheet of `AOP_Analysis_2.xlsx`.
- Only rows whose status is exactly `MISMATCH` were eligible.
- Sampling seed: `20260619`.
- Every model script reads the same sample.
- The LLM DAG planner and NetworkX DAG executor are retained.
- Multi-candidate planning is the default: GPT-5.2 handles candidate generation, DAG rewriting, and semantic reward evaluation as separate OpenAI calls.
- One-shot planning remains available only when `DAG_PLANNER_MODE=one_shot` is explicitly set.
- Invalid dynamic DAGs are rejected by Python before reward scoring. If all candidates fail, the planner dynamically retries for up to `DAG_PLANNER_MAX_ROUNDS` rounds (default: 3); no manual DAG is injected.
- Python is authoritative for DAG order/dependencies. The LLM reward evaluator scores only semantic efficiency and optional operators; a Python-valid DAG receives at least `0.5`, preventing evaluator contradictions from causing crashes.
- Hard-coded/manual fallback DAG node-and-edge dictionaries were removed.
- Entity aliases are normalized in the user query before planning/retrieval/generation, while generated SPARQL is normalized again before execution.
- Dedicated OpenAI clients are used for DAG planning (`PLANNER_MODEL`, default `gpt-5.2`) and SPARQL generation (`OPENAI_SPARQL_MODEL`, default `gpt-5.5`).
- Set `OPENAI_API_KEY` in the private `.env`; the same credential is used by both OpenAI clients.
- `Refine` deliberately remains on the selected local model, so OpenAI usage is limited to initial SPARQL generation and Generate-based logic retries.
- Model names are role-based: `LOCAL_MODEL`, `PLANNER_MODEL`, `REFINE_MODEL`, `VALIDATE_MODEL`, and `EXPLAIN_MODEL`. No legacy Llama-specific variable names remain.
- Local models are accessed only through the OpenAI-compatible server configured by `LLM_BASE_URL`; the unused direct Hugging Face/Transformers loading path was removed.
- The domain-specific `fallback_retrieve_classes()` keyword/scoring heuristic was removed. If `Retrieve` produces no valid classes, `Generate` receives the full dynamically loaded KG schema.
- Dataset-specific SPARQL predicate/class rewrites were removed. SPARQL cleanup now only strips Markdown fences, adds missing standard prefixes, and normalizes known RDF entity-ID aliases.
- Every sampled row receives a stable `Sample Row ID` from 1 to 300. Resume logic uses this ID rather than question text, so duplicate questions are still executed independently.
- Reports are written through a temporary file and atomically replaced after each completed row.

Setup:

```bash
python -m pip install -r requirements.txt
export OPENAI_API_KEY="..."
export OPENAI_SPARQL_MODEL="gpt-5.5"
python firstcheck_gemma4_26b.py
```

The scripts automatically load a private `.env` file from this folder. Real credentials belong in `.env`; `.env.example` must contain placeholders only.

Model scripts:

- `firstcheck_gemma4_26b.py`
- `firstcheck_gemma4_4b.py`
- `firstcheck_qwen14b.py`
- `firstcheck_qwen32b.py`
- `firstcheck_deepseek16b.py`

This is a hybrid agentic pipeline: the LLM dynamically plans an operator DAG and can trigger self-healing actions, while Python executes registered operators and enforces validation rules. It is more than a simple `if/else` pipeline, but it is not native provider-side function/tool calling because operators are dispatched by the local executor.
