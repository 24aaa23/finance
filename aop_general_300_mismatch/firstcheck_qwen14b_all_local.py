"""Run the AOP pipeline with Qwen 14B for every LLM task except final grading."""

import os
import runpy


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11440/v1")

# Main semantic operators, DAG planning, and SPARQL generation all use Qwen 14B.
os.environ["LLM_MODEL"] = "qwen2.5-coder:14b"
os.environ["PLANNER_MODEL"] = "qwen2.5-coder:14b"
os.environ["OPENAI_SPARQL_MODEL"] = "qwen2.5-coder:14b"

# The planner and Generate clients use the same local OpenAI-compatible Ollama endpoint.
os.environ["LLM_BASE_URL"] = OLLAMA_BASE_URL
os.environ["OPENAI_BASE_URL"] = OLLAMA_BASE_URL
os.environ["OPENAI_API_KEY"] = "local-model"

# Only the fallback final-answer evaluator uses Qwen 32B.
os.environ["FINAL_EVALUATOR_MODEL"] = "qwen2.5-coder:32b"

# Keep this experiment independent from the GPT-assisted Qwen14 report.
os.environ["PIPELINE_VERSION"] = "qwen14-all-local-final-qwen32-v1"
os.environ["REPORT_FILE"] = os.path.join(
    SCRIPT_DIR,
    "Pipeline_Outputs",
    "Pipeline_Retest_Report_qwen14b_all_local.csv",
)

runpy.run_path(
    os.path.join(SCRIPT_DIR, "firstcheck_qwen14b.py"),
    run_name="__main__",
)
