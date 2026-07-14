import os
import re
import json
import threading
import datetime
import time
from openai import OpenAI as LLMClient

# Re-use env loader and builders
def load_local_env_file() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_candidates = [
        os.path.join(script_dir, ".env"),
        os.path.join(os.path.dirname(script_dir), ".env"),
        os.path.join("/DATAAMAN/financial/aop_general_300_mismatch", ".env"),
    ]
    env_file = next((path for path in env_candidates if os.path.exists(path)), None)
    if not env_file:
        return
    with open(env_file, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


# Call env loader
load_local_env_file()

os.environ.setdefault("QUERY_SHUFFLE_SEED", "4043113952")

DEFAULT_LLM_MODEL = "openai.gpt-oss-120b-1:0"
GPT_OSS_MODEL = os.getenv("BEDROCK_GPT_OSS_MODEL", DEFAULT_LLM_MODEL)
LOCAL_MODEL = GPT_OSS_MODEL
PLANNER_MODEL = GPT_OSS_MODEL
REFINE_MODEL = GPT_OSS_MODEL
VALIDATE_MODEL = GPT_OSS_MODEL
EXPLAIN_MODEL = GPT_OSS_MODEL
SPARQL_GENERATION_MODEL = GPT_OSS_MODEL
PIPELINE_VERSION = os.getenv("GPT_OSS_LLM_GRADER_PIPELINE_VERSION", "aop-general-gpt-oss-120b-llm-grader-v1")

TEST_QUERY_LIMIT = int(os.getenv("TEST_QUERY_LIMIT", "300"))
TEST_QUERY_OFFSET = int(os.getenv("TEST_QUERY_OFFSET", "0"))
TEST_MAX_WORKERS = int(os.getenv("TEST_MAX_WORKERS", "1"))
SPARQL_SCAN_TIMEOUT_SECONDS = max(0.0, float(os.getenv("SPARQL_SCAN_TIMEOUT_SECONDS", "60")))
SPARQL_SCAN_MAX_RETRIES = max(1, int(os.getenv("SPARQL_SCAN_MAX_RETRIES", "3")))
SPARQL_SCAN_PROCESS_START_METHOD = os.getenv("SPARQL_SCAN_PROCESS_START_METHOD", "spawn")

BASE_DIR = r"C:\Users\AMAN KUMAR SINGH\Desktop\financial"
EXPERIMENT_DIR = os.path.join(BASE_DIR, "aop_generate_500_multitable")
OUTPUT_DIR = os.path.join(EXPERIMENT_DIR, "pipeline_output")
SCHEMA_FILE = os.path.join(BASE_DIR, "kg_output_fixed", "wealth_management_diverse_schema.ttl")
INSTANCE_FILE = os.path.join(BASE_DIR, "kg_output_fixed", "wealth_management_diverse_kg.ttl")
INPUT_SAMPLE_FILE = os.path.join(BASE_DIR, "dataset_new", "wealth_management_all_benchmark_questions_combined_shuffled_seed4043113952.csv")
REPORT_FILE = os.getenv("GPT_OSS_LLM_GRADER_REPORT_FILE", os.path.join(OUTPUT_DIR, "Pipeline_Retest_Report_gpt_oss_120b_llm_grader_newkg_300.csv"))
ALIAS_MAP_FILE = os.getenv("RDF_ALIAS_MAP_FILE", os.path.join(EXPERIMENT_DIR, "rdf_id_alias_map.json"))

os.makedirs(OUTPUT_DIR, exist_ok=True)
def build_bedrock_gpt_oss_client():
    """Build the Bedrock OpenAI-compatible client used by every LLM role."""
    api_key = (
        os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not api_key:
        raise RuntimeError(
            "AWS_BEDROCK_API_KEY is required for the GPT-OSS 120B Bedrock pipeline."
        )

    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError(
                "BEDROCK_REGION is required for the GPT-OSS 120B Bedrock endpoint "
                "(for example: BEDROCK_REGION=us-east-1)."
            )
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"

    return LLMClient(api_key=api_key, base_url=base_url)

def build_llm_client():
    return build_bedrock_gpt_oss_client()

def build_openai_sparql_client():
    return build_bedrock_gpt_oss_client()

def build_openai_planner_client():
    return build_bedrock_gpt_oss_client()

class APILogger:
    def __init__(self):
        self.lock = threading.Lock()
        self.query_logs = {}
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Save directly to the new organized folder
        self.log_file = os.path.join(OUTPUT_DIR, f"api_usage_log_{timestamp}.json")

    def log_call(self, query, function_name):
        with self.lock:
            q_key = query if query else "Unknown_Query"
            if q_key not in self.query_logs:
                self.query_logs[q_key] = {"total_calls": 0, "functions": {}}

            self.query_logs[q_key]["total_calls"] += 1
            self.query_logs[q_key]["functions"][function_name] = self.query_logs[q_key]["functions"].get(function_name, 0) + 1

    def save(self):
        with self.lock:
            with open(self.log_file, "w") as f:
                json.dump(self.query_logs, f, indent=4)

api_logger = APILogger()
