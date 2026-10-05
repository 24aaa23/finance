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
from openai import OpenAI as LLMClient
from .input_paths import INPUT_ENV_KEYS, resolve_input_paths


def load_local_env_file() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Keep the experiment-local credentials as the package default so direct
    # `python run.py` launches and batch-runner children use the same setup.
    default_pipeline_env_file = os.path.join(os.path.dirname(script_dir), ".env")
    explicit_env_file = os.getenv("PIPELINE_ENV_FILE", "").strip()
    env_candidates = [explicit_env_file] if explicit_env_file else [default_pipeline_env_file]
    env_file = next((path for path in env_candidates if os.path.exists(path)), None)
    if not env_file:
        return
    override_existing = os.getenv("PIPELINE_ENV_OVERRIDE", "0") == "1"
    with open(env_file, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            key = key.strip()
            # Knowledge/data selection belongs to the launcher, not credentials.
            if key in INPUT_ENV_KEYS:
                continue
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

DETERMINISTIC_EXPLAIN = os.getenv("DETERMINISTIC_EXPLAIN", "1").strip().lower() not in {"0", "false", "no"}
PIPELINE_VERSION = "aop-improvement8-v1"
QUERY_UNDERSTANDING = os.getenv("QUERY_UNDERSTANDING", "1").lower() in {"1", "true", "yes"}
CONTRACT_CHECKS = os.getenv("CONTRACT_CHECKS", "1").lower() in {"1", "true", "yes"}
AGENT_CONSULTATION = os.getenv("AGENT_CONSULTATION", "1").lower() in {"1", "true", "yes"}
_input_paths = resolve_input_paths(os.environ)
DOMAIN_INTRO_FILE = _input_paths["DOMAIN_INTRO_FILE"]
BUSINESS_RULES_FILE = _input_paths["BUSINESS_RULES_FILE"]
TABLE_METADATA_DIR = _input_paths["TABLE_METADATA_DIR"]
KNOWLEDGE_CACHE_DIR = os.getenv("KNOWLEDGE_CACHE_DIR", os.path.join(SCRIPT_DIR, ".runtime", "knowledge"))

TEST_QUERY_LIMIT = int(os.getenv("TEST_QUERY_LIMIT", "100"))
TEST_QUERY_OFFSET = int(os.getenv("TEST_QUERY_OFFSET", "0"))
TEST_MAX_WORKERS = int(os.getenv("TEST_MAX_WORKERS", "1"))

SPARQL_SCAN_MAX_RETRIES = max(1, int(os.getenv("SPARQL_SCAN_MAX_RETRIES", "3")))
PRE_SCAN_VALIDATE_MAX_RETRIES = max(1, int(os.getenv("PRE_SCAN_VALIDATE_MAX_RETRIES", "3")))
POST_SCAN_VALIDATE_MAX_RETRIES = max(1, int(os.getenv("POST_SCAN_VALIDATE_MAX_RETRIES", "3")))
SCAN_REFINE_MAX_RETRIES = max(1, int(os.getenv("SCAN_REFINE_MAX_RETRIES", str(SPARQL_SCAN_MAX_RETRIES))))
SQLITE_DB_PATH = _input_paths["SQLITE_DB_PATH"]
SQL_SCAN_TIMEOUT_SECONDS = max(0.0, float(os.getenv("SQL_SCAN_TIMEOUT_SECONDS", "60")))

BASE_DIR = os.getenv("BASE_DIR", SCRIPT_DIR)
EXPERIMENT_DIR = SCRIPT_DIR
OUTPUT_DIR = os.getenv("PIPELINE_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "pipelien_output_sql"))
INPUT_SAMPLE_FILE = os.getenv(
    "INPUT_SAMPLE_FILE",
    os.path.join(SCRIPT_DIR, "questions.jsonl"),
)
INPUT_SAMPLE_SHEET = os.getenv("INPUT_SAMPLE_SHEET", "").strip()
REPORT_FILE = os.getenv(
    "REPORT_FILE",
    os.path.join(OUTPUT_DIR, "raw_pipeline_v9.csv"),
)

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
