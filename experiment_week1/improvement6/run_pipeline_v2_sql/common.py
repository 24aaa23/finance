"""Foundational imports, constants, prompts, and API logging for the pipeline."""

import datetime
import difflib
import json
import multiprocessing
import os
import queue
import re
import socket
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import pandas as pd
import rdflib
from openai import OpenAI as LLMClient


def load_local_env_file() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(os.path.dirname(script_dir))
    workspace_dir = os.path.dirname(repo_dir)
    # Keep the experiment-local credentials as the package default so direct
    # `python run.py` launches and batch-runner children use the same setup.
    default_pipeline_env_file = os.path.join(os.path.dirname(script_dir), ".env")
    explicit_env_file = os.getenv("PIPELINE_ENV_FILE", "").strip()
    env_candidates = [
        explicit_env_file,
        default_pipeline_env_file,
        os.path.join(script_dir, ".env"),
        os.path.join(os.path.dirname(script_dir), ".env"),
        os.path.join(repo_dir, ".env"),
        os.path.join(workspace_dir, ".env"),
        os.path.join(repo_dir, "aop_generate_500_multitable", ".env"),
        os.path.join(repo_dir, "aop_general_300_mismatch", ".env"),
        os.path.join(workspace_dir, "aop_generate_500_multitable", ".env"),
        os.path.join(workspace_dir, "aop_general_300_mismatch", ".env"),
    ]
    env_file = next((path for path in env_candidates if os.path.exists(path)), None)
    if not env_file:
        return
    override_existing = (
        os.path.abspath(env_file) == os.path.abspath(default_pipeline_env_file)
        or (bool(explicit_env_file) and os.getenv("PIPELINE_ENV_OVERRIDE", "").strip().lower() in {"1", "true", "yes"})
    )
    with open(env_file, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            key = key.strip()
            if override_existing:
                os.environ[key] = value
            else:
                os.environ.setdefault(key, value)


load_local_env_file()
os.environ.setdefault("QUERY_SHUFFLE_SEED", "4043113952")

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(PACKAGE_DIR)
SCRIPT_EXPERIMENT_DIR = SCRIPT_DIR
SCRIPT_BASE_DIR = SCRIPT_DIR

DEFAULT_GPT_OSS_MODEL = "openai.gpt-oss-120b-1:0"
GPT_OSS_MODEL = os.getenv("BEDROCK_GPT_OSS_MODEL", DEFAULT_GPT_OSS_MODEL)
LOCAL_MODEL = GPT_OSS_MODEL
RAG_MODEL = GPT_OSS_MODEL
PLANNER_MODEL = GPT_OSS_MODEL
QUERY_SPEC_MODEL = GPT_OSS_MODEL
REFINE_MODEL = GPT_OSS_MODEL
VALIDATE_MODEL = GPT_OSS_MODEL
EXPLAIN_MODEL = GPT_OSS_MODEL
SPARQL_GENERATION_MODEL = GPT_OSS_MODEL
LLM_GRADER_MODEL = GPT_OSS_MODEL

DETERMINISTIC_EXPLAIN = os.getenv("DETERMINISTIC_EXPLAIN", "1").strip().lower() not in {"0", "false", "no"}
PIPELINE_VERSION = os.getenv("GPT_OSS_LLM_GRADER_PIPELINE_VERSION", "aop-improvement3-v9")

TEST_QUERY_LIMIT = int(os.getenv("TEST_QUERY_LIMIT", "100"))
TEST_QUERY_OFFSET = int(os.getenv("TEST_QUERY_OFFSET", "0"))
TEST_MAX_WORKERS = int(os.getenv("TEST_MAX_WORKERS", "1"))

SPARQL_SCAN_TIMEOUT_SECONDS = max(0.0, float(os.getenv("SPARQL_SCAN_TIMEOUT_SECONDS", "60")))
FUSEKI_ENDPOINT = os.getenv("FUSEKI_ENDPOINT", "http://127.0.0.1:3030/wealth/query")
FUSEKI_SCAN_TIMEOUT_SECONDS = max(0.0, float(os.getenv("FUSEKI_SCAN_TIMEOUT_SECONDS", "60")))
FUSEKI_METADATA_TIMEOUT_SECONDS = max(0.0, float(os.getenv("FUSEKI_METADATA_TIMEOUT_SECONDS", "60")))
SPARQL_SCAN_MAX_RETRIES = max(1, int(os.getenv("SPARQL_SCAN_MAX_RETRIES", "3")))
PRE_SCAN_VALIDATE_MAX_RETRIES = max(1, int(os.getenv("PRE_SCAN_VALIDATE_MAX_RETRIES", "3")))
POST_SCAN_VALIDATE_MAX_RETRIES = max(1, int(os.getenv("POST_SCAN_VALIDATE_MAX_RETRIES", "3")))
SCAN_REFINE_MAX_RETRIES = max(1, int(os.getenv("SCAN_REFINE_MAX_RETRIES", str(SPARQL_SCAN_MAX_RETRIES))))
SPARQL_SCAN_PROCESS_START_METHOD = os.getenv("SPARQL_SCAN_PROCESS_START_METHOD", "spawn")
SQLITE_DB_PATH = os.path.abspath(os.getenv(
    "SQLITE_DB_PATH", os.path.join(SCRIPT_DIR, "wealth_management_diverse.db")))
SQL_SCAN_TIMEOUT_SECONDS = max(0.0, float(os.getenv("SQL_SCAN_TIMEOUT_SECONDS", "60")))

BASE_DIR = os.getenv("BASE_DIR", SCRIPT_DIR)
EXPERIMENT_DIR = SCRIPT_DIR
OUTPUT_DIR = os.getenv("PIPELINE_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "pipelien_output_sql"))
SCHEMA_FILE = os.getenv(
    "SCHEMA_FILE",
    os.path.join(SCRIPT_DIR, "kg_output_fixed", "wealth_management_diverse_schema.ttl"),
)
INSTANCE_FILE = os.getenv(
    "INSTANCE_FILE",
    os.path.join(SCRIPT_DIR, "kg_output_fixed", "wealth_management_diverse_kg.ttl"),
)
INPUT_SAMPLE_FILE = os.getenv(
    "INPUT_SAMPLE_FILE",
    os.path.join(SCRIPT_DIR, "datatset", "wealth_management_1000_test_set_questions.xlsx"),
)
INPUT_SAMPLE_SHEET = os.getenv("INPUT_SAMPLE_SHEET", "").strip()
REPORT_FILE = os.getenv(
    "REPORT_FILE",
    os.path.join(OUTPUT_DIR, "raw_pipeline_v9.csv"),
)
ALIAS_MAP_FILE = os.getenv("RDF_ALIAS_MAP_FILE", os.path.join(SCRIPT_DIR, "rdf_id_alias_map.json"))
def _resolve_alias_map_file() -> str:
    env_path = os.getenv("RDF_ALIAS_MAP_FILE")
    if env_path and os.path.exists(env_path):
        return env_path
    candidates = [
        os.path.join(SCRIPT_DIR, "rdf_id_alias_map.json"),
        os.path.join(os.path.dirname(SCRIPT_DIR), "improvement1", "rdf_id_alias_map.json"),
        os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "aop_generate_500_multitable", "rdf_id_alias_map.json"),
    ]
    return next((c for c in candidates if os.path.exists(c)), candidates[0])


ALIAS_MAP_FILE = _resolve_alias_map_file()

RDF_ID_ALIAS_MAP = {}
FUSEKI_GRAPH_TERMS_CACHE = None

ROLE_PROMPTS = {
    "retrieve": (
        "Select exact SQLite table names needed by the question. Return the requested JSON."
    ),
    "query_spec": (
        "Describe one source retrieval using the documented JSON fields. Preserve exact conditions and keys."
    ),
    "processing_spec": (
        "Scanned rows pass through unchanged. All calculation planning belongs to Final_Spec."
    ),
    "final_spec": (
        "Build one executable relational plan from raw branch datasets to answer the original question. "
        "Use the documented JSON fields. Preserve conditions, missing values, and what each average counts."
    ),
    "decompose": (
        "Split the question into the necessary source retrievals. Preserve conditions and connections."
    ),
    "generate": (
        "Translate the supplied retrieval specification into raw SQLite SELECT SQL. Return only the query."
    ),
    "refine": (
        "Repair SQLite SELECT SQL using the supplied error and schema. Preserve the retrieval's meaning."
    ),
    "validate": (
        "Review whether retrieval and calculation answer the original question. Return the documented verdict."
    ),
    "explain": (
        "Present supplied result rows concisely. Preserve values and never invent data."
    ),
    "semantic": (
        "Use the supplied schema and data. Return the requested format without inventing facts."
    ),
    "planner": (
        "Use only the documented operations and schema when describing a calculation."
    ),
}

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)


class APILogger:
    def __init__(self):
        self.lock = threading.Lock()
        self.query_logs = {}
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(OUTPUT_DIR, f"api_usage_log_{timestamp}.json")

    def log_call(self, query, function_name):
        with self.lock:
            q_key = query if query else "Unknown_Query"
            if q_key not in self.query_logs:
                self.query_logs[q_key] = {"total_calls": 0, "functions": {}}
            self.query_logs[q_key]["total_calls"] += 1
            self.query_logs[q_key]["functions"][function_name] = (
                self.query_logs[q_key]["functions"].get(function_name, 0) + 1
            )

    def save(self):
        with self.lock:
            with open(self.log_file, "w") as f:
                json.dump(self.query_logs, f, indent=4)


api_logger = APILogger()
