"""Run the complete AOP pipeline locally with Qwen 2.5 Coder 32B."""

import os
import runpy


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11440/v1")
QWEN_MODEL = "qwen2.5-coder:32b"

# Every LLM role uses the local Qwen 32B model.
os.environ["LLM_MODEL"] = QWEN_MODEL
os.environ["PLANNER_MODEL"] = QWEN_MODEL
os.environ["REFINE_MODEL"] = QWEN_MODEL
os.environ["VALIDATE_MODEL"] = QWEN_MODEL
os.environ["EXPLAIN_MODEL"] = QWEN_MODEL
os.environ["OPENAI_SPARQL_MODEL"] = QWEN_MODEL

# Planner and SPARQL clients use Ollama's OpenAI-compatible endpoint.
os.environ["LLM_BASE_URL"] = OLLAMA_BASE_URL
os.environ["OPENAI_BASE_URL"] = OLLAMA_BASE_URL
os.environ["OPENAI_API_KEY"] = "local-model"

# Keep this experiment independent from the GPT-assisted Qwen 32B report.
os.environ["PIPELINE_VERSION"] = "qwen32b-all-local-v1"
os.environ["REPORT_FILE"] = os.path.join(
    SCRIPT_DIR,
    "Pipeline_Outputs",
    "Pipeline_Retest_Report_qwen32b_all_local.csv",
)

runpy.run_path(
    os.path.join(SCRIPT_DIR, "firstcheck_qwen32b.py"),
    run_name="__main__",
)
