"""
Base Text-to-SQL Pipeline — GPT-OSS 120B, single-shot, ungraded, concurrent
============================================================================

  1. INPUT      — Query + SQLite DB Schema
  2. GENERATE   — LLM produces SQL from query + schema (single attempt, no retry)
  3. EXECUTE    — Run SQL against SQLite database
  4. STORE      — Save full raw result rows + timing/token metrics; no grading here

Model: openai.gpt-oss-120b-1:0 (via Bedrock)

Questions are processed concurrently (bounded thread pool). Each worker opens
its own SQLite connection (sqlite3 connections are not thread-safe to share).
"""

import csv
import datetime
import argparse
import json
import os
import re
import sqlite3
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import pandas as pd
from openai import OpenAI as LLMClient


# ---------------------------------------------------------------------------
# 0. ENVIRONMENT
# ---------------------------------------------------------------------------

def load_local_env_file() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_candidates = [
        os.path.join(script_dir, ".env"),
        os.path.join(os.path.dirname(script_dir), ".env"),
        os.path.join(os.path.dirname(script_dir), "base_pipeline_qwen", ".env"),
    ]
    env_file = next((p for p in env_candidates if os.path.exists(p)), None)
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


load_local_env_file()

_csv_field_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_csv_field_limit)
        break
    except OverflowError:
        _csv_field_limit //= 10


# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASELINES_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
FINANCE_ROOT = os.path.abspath(os.path.join(BASELINES_ROOT, ".."))

TARGET_MODEL = os.getenv("TARGET_MODEL", "openai.gpt-oss-120b-1:0")
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION", "base-pipeline-sql-gpt-oss-120b-single-shot-ungraded-v1")
TEST_QUERY_LIMIT = int(os.getenv("TEST_QUERY_LIMIT", "0"))  # 0 = all
TEST_QUERY_OFFSET = int(os.getenv("TEST_QUERY_OFFSET", "0"))
PIPELINE_WORKERS = int(os.getenv("PIPELINE_WORKERS", "8"))

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", os.path.join(FINANCE_ROOT, "wealth_management_diverse.db"))
SQLITE_QUERY_TIMEOUT_SECONDS = max(0.0, float(os.getenv("SQLITE_QUERY_TIMEOUT_SECONDS", "60")))

SCRIPT_DIFF_ROOT = os.path.abspath(os.path.join(FINANCE_ROOT, "script_diff_llm"))
INPUT_SAMPLE_FILE = os.getenv(
    "INPUT_SAMPLE_FILE",
    os.path.join(BASELINES_ROOT, "dataset", "wealth_management_1000_questions.csv"),
)
OUTPUT_DIR = os.getenv("PIPELINE_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "output"))
REPORT_FILE = os.getenv(
    "REPORT_FILE",
    os.path.join(OUTPUT_DIR, "base_pipeline_sql_gpt_oss_120b_ungraded.csv"),
)
GROUND_TRUTH_JSON = os.getenv("GROUND_TRUTH_JSON", "")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)


# ---------------------------------------------------------------------------
# 2. API CLIENT
# ---------------------------------------------------------------------------

def build_gpt_oss_client() -> LLMClient:
    api_key = (
        os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not api_key:
        raise RuntimeError("AWS_BEDROCK_API_KEY is required for GPT-OSS 120B Bedrock endpoint.")
    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError("BEDROCK_REGION is required (e.g. us-east-1).")
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"
    return LLMClient(api_key=api_key, base_url=base_url, timeout=180, max_retries=1)


# ---------------------------------------------------------------------------
# 3. API LOGGER
# ---------------------------------------------------------------------------

class APILogger:
    def __init__(self):
        self.lock = threading.Lock()
        self.query_logs: Dict[str, Any] = {}
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(OUTPUT_DIR, f"api_usage_log_{timestamp}.json")

    def log_call(self, query: str, function_name: str):
        with self.lock:
            q_key = query or "Unknown_Query"
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


# ---------------------------------------------------------------------------
# 4. UTILITY FUNCTIONS
# ---------------------------------------------------------------------------

def sanitize_user_query(raw_query: str) -> str:
    normalized = unicodedata.normalize("NFKD", raw_query).encode("ascii", "ignore").decode("utf-8")
    cleaned = re.sub(r"[^\x20-\x7E]", "", normalized)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else "Invalid Query"


def strip_llm_reasoning_blocks(text: str) -> str:
    cleaned = re.sub(r"(?is)<reasoning>.*?</reasoning>", "", text or "")
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
    return cleaned.strip()


def is_quota_exhaustion_error(error: Any) -> bool:
    msg = str(error).lower()
    return any(marker in msg for marker in ("rate limit", "ratelimit", "quota", "throttl", "429", "too many requests"))


def supports_temperature(model: str) -> bool:
    return not str(model or "").lower().startswith("gpt-5")


# ---------------------------------------------------------------------------
# 5. SQLITE SCHEMA LOADING
# ---------------------------------------------------------------------------

def load_sqlite_schema(db_path: str) -> Dict[str, Any]:
    print(f"[SYSTEM] Loading SQLite schema from {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    schema: Dict[str, Any] = {}
    for table_name in tables:
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        columns = cursor.fetchall()
        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        row_count = cursor.fetchone()[0]

        column_info = []
        for col in columns:
            col_name = col[1]
            col_type = col[2]
            is_pk = col[5] > 0
            try:
                cursor.execute(
                    f'SELECT DISTINCT "{col_name}" FROM "{table_name}" '
                    f'WHERE "{col_name}" IS NOT NULL LIMIT 3'
                )
                samples = [str(r[0]) for r in cursor.fetchall()]
            except Exception:
                samples = []
            column_info.append({"name": col_name, "type": col_type, "is_primary_key": is_pk, "sample_values": samples})

        schema[table_name] = {"row_count": row_count, "columns": column_info}

    conn.close()
    print(f"[SYSTEM] Successfully loaded schema for {len(schema)} tables.")
    return schema


def build_schema_text(schema: Dict[str, Any]) -> str:
    lines = []
    for table_name, details in schema.items():
        row_count = details.get("row_count", 0)
        lines.append(f"Table: {table_name}  ({row_count} rows)")
        for col in details.get("columns", []):
            name = col["name"]
            dtype = col["type"]
            pk = " [PRIMARY KEY]" if col.get("is_primary_key") else ""
            samples = col.get("sample_values", [])
            sample_str = f"  -- e.g. {', '.join(repr(s) for s in samples[:3])}" if samples else ""
            lines.append(f"  - {name} ({dtype}){pk}{sample_str}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 6. SQLITE EXECUTION
# ---------------------------------------------------------------------------

def check_sqlite_health(db_path: str) -> None:
    if not os.path.exists(db_path):
        raise RuntimeError(f"SQLite database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("SELECT 1")
    conn.close()
    print("[SYSTEM] SQLite health check passed.")


def execute_sql_on_sqlite(
    sql_query: str,
    db_path: str = SQLITE_DB_PATH,
    timeout_seconds: float = SQLITE_QUERY_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    try:
        conn = sqlite3.connect(db_path, timeout=timeout_seconds)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        if rows:
            columns = [description[0] for description in cursor.description]
            data = [dict(zip(columns, row)) for row in rows]
        else:
            data = []
        conn.close()
        return {"status": "success", "data": data, "row_count": len(data), "sql": sql_query}
    except sqlite3.OperationalError as e:
        return {"status": "error", "error_message": f"SQLite operational error: {e}", "failed_sql": sql_query}
    except sqlite3.Error as e:
        return {"status": "error", "error_message": f"SQLite error: {e}", "failed_sql": sql_query}
    except Exception as e:
        return {"status": "error", "error_message": str(e), "failed_sql": sql_query}


# ---------------------------------------------------------------------------
# 7. GENERATE SQL (single attempt)
# ---------------------------------------------------------------------------

def generate_sql(query: str, schema_text: str, client: LLMClient, model: str) -> Dict[str, Any]:
    prompt = f"""You are a SQL query generator for a SQLite database about wealth management.

User Query: "{query}"

SQLite Database Schema:
{schema_text}

Return ONLY raw SQL text. Do not explain. Do not include <reasoning>, <think>, markdown, comments, or prose.
The first non-whitespace characters in your response must be SELECT, WITH, or another SQL keyword.

CRITICAL SQL RULES:

RULE 1 (TABLE NAMES): Use the exact table names from the schema above. All table names start with ATOM_.
Always quote table names with double quotes since they contain special characters.

RULE 2 (JOINS): All tables share the `investor_id` column. Use JOINs via investor_id to combine data from multiple tables.
Use LEFT JOIN when you need to preserve all rows from the primary table even if secondary table has no match.

RULE 3 (AGGREGATIONS): Use standard SQL aggregation functions: SUM(), AVG(), COUNT(), MIN(), MAX().
When using aggregations, ensure all non-aggregated SELECT columns are in the GROUP BY clause.
Cast text to REAL when doing math: CAST(column AS REAL).

RULE 4 (CASE-INSENSITIVE FILTERS): When filtering by text values, use LOWER() for case-insensitive matching.
Example: WHERE LOWER(risk_tolerance) = 'conservative'

RULE 5 (NEGATION): If the user query contains "never", "not", "excluding", "without", or "no X", use NOT IN, NOT EXISTS, or WHERE NOT.

RULE 6 (RANKING): For top/bottom/highest/lowest questions, use ORDER BY with LIMIT.
For "top N", use ORDER BY DESC LIMIT N. For "bottom N", use ORDER BY ASC LIMIT N.

RULE 7 (COUNT): Use COUNT(*) or COUNT(column) as appropriate. Use COUNT(DISTINCT column) only when the user asks for distinct/unique values.

RULE 8 (DATE HANDLING): Dates are stored as TEXT in YYYY-MM-DD format.
For month grouping, use SUBSTR(date_column, 1, 7) to get YYYY-MM.
For year grouping, use SUBSTR(date_column, 1, 4) to get YYYY.

RULE 9 (NULL HANDLING): Use COALESCE(column, default_value) to handle NULLs when needed.
For "for each" or "by" grouping queries, include rows where the group column might be NULL.

RULE 10 (ARITHMETIC): Be careful with division — use NULLIF(denominator, 0) to avoid division by zero.
Example: SUM(a) / NULLIF(COUNT(*), 0)

RULE 11 (SUBQUERIES): For complex multi-step queries, use CTEs (WITH clauses) or subqueries to break down the logic.

RULE 12 (ROUNDING): When the question asks for percentages or financial metrics, round to 2 decimal places: ROUND(value, 2).
"""

    api_logger.log_call(query, "Generate_SQL")
    request_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if supports_temperature(model):
        request_kwargs["temperature"] = 0.0

    t0 = time.perf_counter()
    response = client.chat.completions.create(**request_kwargs)
    latency = time.perf_counter() - t0
    result = response.choices[0].message.content.strip()
    usage = getattr(response, "usage", None)

    result = strip_llm_reasoning_blocks(result)
    if "```" in result:
        parts = result.split("```")
        if len(parts) >= 3:
            code_block = parts[1]
            if code_block.lower().startswith("sql"):
                code_block = code_block[3:]
            sql_query = code_block.strip()
        else:
            sql_query = result.replace("```sql", "").replace("```SQL", "").replace("```", "").strip()
    else:
        sql_query = result.strip()

    return {
        "sql": sql_query,
        "latency": latency,
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
    }


# ---------------------------------------------------------------------------
# 8. RESULT SERIALIZATION
# ---------------------------------------------------------------------------

def serialize_rows(rows: List[Dict[str, Any]]) -> str:
    return json.dumps(rows, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 9. DATASET LOADING
# ---------------------------------------------------------------------------

def load_input_samples(sample_file: str) -> pd.DataFrame:
    extension = os.path.splitext(sample_file)[1].lower()
    if extension in {".xlsx", ".xls"}:
        sheets = pd.read_excel(sample_file, sheet_name=None)
        frames = [
            frame
            for sheet_name, frame in sheets.items()
            if sheet_name != "Mapping Check" and {"question", "ground_truth_answer"}.issubset(frame.columns)
        ]
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
    return pd.read_csv(sample_file)


def load_ground_truth_json(json_file: str) -> Dict[str, str]:
    if not json_file:
        return {}
    if not os.path.exists(json_file):
        raise RuntimeError(f"Ground-truth JSON not found: {json_file}")
    with open(json_file, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return {str(key): json.dumps(value, ensure_ascii=False) for key, value in data.items()}
    if isinstance(data, list):
        mapping = {}
        for item in data:
            if isinstance(item, dict):
                for key in ("question_id", "Sample Row ID", "sample_row_id", "id"):
                    if item.get(key):
                        answer = item.get("ground_truth_answer", item.get("Ground Truth", item.get("answer", item)))
                        mapping[str(item[key])] = json.dumps(answer, ensure_ascii=False)
                        break
        return mapping
    return {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the base SQL pipeline.")
    parser.add_argument("--input-sample-file", default=INPUT_SAMPLE_FILE)
    parser.add_argument("--ground-truth-json", default=GROUND_TRUTH_JSON)
    parser.add_argument("--completed-results-json", dest="ground_truth_json", help=argparse.SUPPRESS)
    parser.add_argument("--report-file", default=REPORT_FILE)
    parser.add_argument("--pipeline-output-dir", default=OUTPUT_DIR)
    parser.add_argument("--test-query-limit", type=int, default=TEST_QUERY_LIMIT)
    parser.add_argument("--test-query-offset", type=int, default=TEST_QUERY_OFFSET)
    parser.add_argument("--pipeline-workers", type=int, default=PIPELINE_WORKERS)
    parser.add_argument("--sqlite-db-path", default=SQLITE_DB_PATH)
    return parser.parse_args()


REPORT_COLUMNS = [
    "Pipeline Version",
    "Sample Row ID",
    "Question",
    "Ground Truth",
    "Difficulty",
    "Category",
    "Query Type",
    "Source CSV",
    "New Status",
    "Generated SQL",
    "Scan Status",
    "Scan Row Count",
    "Scan Error",
    "Scan Raw Rows",
    "Target Model",
    "Generation Input Tokens",
    "Generation Output Tokens",
    "Generation Latency Seconds",
    "Execution Latency Seconds",
    "Started At",
    "Elapsed Seconds",
]


def process_question(record: Dict[str, Any], client: LLMClient, schema_text: str) -> Dict[str, Any]:
    query_start = time.perf_counter()
    started_at = datetime.datetime.now().isoformat(timespec="seconds")
    query = sanitize_user_query(str(record.get("Question", "")))
    ground_truth = str(record.get("Ground Truth", ""))
    sample_row_id = record.get("Sample Row ID", "")
    row_metadata = {
        "Difficulty": record.get("Difficulty", ""),
        "Category": record.get("Category", ""),
        "Query Type": record.get("Query Type", ""),
        "Source CSV": record.get("Source CSV", ""),
    }
    base_row = {
        "Pipeline Version": PIPELINE_VERSION,
        "Sample Row ID": sample_row_id,
        "Question": query,
        "Ground Truth": ground_truth,
        **row_metadata,
        "Target Model": TARGET_MODEL,
        "Started At": started_at,
    }

    try:
        gen = generate_sql(query=query, schema_text=schema_text, client=client, model=TARGET_MODEL)
    except Exception as gen_err:
        status = "QUOTA_EXHAUSTED" if is_quota_exhaustion_error(gen_err) else "GENERATE_ERROR"
        return {**base_row, "New Status": status, "Scan Error": str(gen_err),
                "Generated SQL": "", "Scan Status": "GENERATE_ERROR", "Scan Row Count": "",
                "Scan Raw Rows": "", "Generation Input Tokens": 0, "Generation Output Tokens": 0,
                "Generation Latency Seconds": "", "Execution Latency Seconds": "",
                "Elapsed Seconds": round(time.perf_counter() - query_start, 3)}

    sql = gen["sql"]
    if not sql.strip():
        return {**base_row, "New Status": "EMPTY_SQL", "Scan Error": "LLM returned empty SQL.",
                "Generated SQL": "", "Scan Status": "EMPTY_SQL", "Scan Row Count": "",
                "Scan Raw Rows": "", "Generation Input Tokens": gen["input_tokens"],
                "Generation Output Tokens": gen["output_tokens"],
                "Generation Latency Seconds": round(gen["latency"], 3), "Execution Latency Seconds": "",
                "Elapsed Seconds": round(time.perf_counter() - query_start, 3)}

    exec_t0 = time.perf_counter()
    scan_result = execute_sql_on_sqlite(sql, SQLITE_DB_PATH, SQLITE_QUERY_TIMEOUT_SECONDS)
    exec_latency = time.perf_counter() - exec_t0
    scan_status = scan_result.get("status", "error")

    if scan_status != "success":
        return {**base_row, "New Status": "EXEC_ERROR", "Scan Error": scan_result.get("error_message", ""),
                "Generated SQL": sql, "Scan Status": "EXEC_ERROR", "Scan Row Count": "",
                "Scan Raw Rows": "", "Generation Input Tokens": gen["input_tokens"],
                "Generation Output Tokens": gen["output_tokens"],
                "Generation Latency Seconds": round(gen["latency"], 3),
                "Execution Latency Seconds": round(exec_latency, 3),
                "Elapsed Seconds": round(time.perf_counter() - query_start, 3)}

    return {
        **base_row,
        "New Status": "OK",
        "Generated SQL": sql,
        "Scan Status": "success",
        "Scan Row Count": scan_result.get("row_count", 0),
        "Scan Error": "",
        "Scan Raw Rows": serialize_rows(scan_result.get("data", [])),
        "Generation Input Tokens": gen["input_tokens"],
        "Generation Output Tokens": gen["output_tokens"],
        "Generation Latency Seconds": round(gen["latency"], 3),
        "Execution Latency Seconds": round(exec_latency, 3),
        "Elapsed Seconds": round(time.perf_counter() - query_start, 3),
    }


def main():
    global INPUT_SAMPLE_FILE, GROUND_TRUTH_JSON, REPORT_FILE, OUTPUT_DIR
    global TEST_QUERY_LIMIT, TEST_QUERY_OFFSET, PIPELINE_WORKERS, SQLITE_DB_PATH

    args = parse_args()
    INPUT_SAMPLE_FILE = args.input_sample_file
    GROUND_TRUTH_JSON = args.ground_truth_json
    REPORT_FILE = args.report_file
    OUTPUT_DIR = args.pipeline_output_dir
    TEST_QUERY_LIMIT = args.test_query_limit
    TEST_QUERY_OFFSET = args.test_query_offset
    PIPELINE_WORKERS = args.pipeline_workers
    SQLITE_DB_PATH = args.sqlite_db_path
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    api_logger.log_file = os.path.join(
        OUTPUT_DIR,
        f"api_usage_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )

    print("\n" + "=" * 60)
    print("  BASE PIPELINE — SQL (GPT-OSS 120B, single-shot, ungraded)")
    print("=" * 60)
    print(f"[CONFIG] Target model: {TARGET_MODEL}")
    print(f"[CONFIG] Workers (concurrent questions): {PIPELINE_WORKERS}")
    print(f"[CONFIG] SQLite DB: {SQLITE_DB_PATH}")
    print(f"[CONFIG] Query window: offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT or 'all'}")
    print(f"[CONFIG] Report file: {REPORT_FILE}")
    if GROUND_TRUTH_JSON:
        print(f"[CONFIG] Full ground truth JSON: {GROUND_TRUTH_JSON}")
    script_start_time = time.perf_counter()

    print("\n[SYSTEM] Checking SQLite connectivity...")
    check_sqlite_health(SQLITE_DB_PATH)

    print("[SYSTEM] Building API client...")
    target_client = build_gpt_oss_client()

    print(f"\n[STEP 1] Loading schema from {SQLITE_DB_PATH}...")
    db_schema = load_sqlite_schema(SQLITE_DB_PATH)
    schema_text = build_schema_text(db_schema)

    print(f"\n[STEP 1] Loading dataset from {INPUT_SAMPLE_FILE}...")
    df_all = load_input_samples(INPUT_SAMPLE_FILE)
    if not {"question", "ground_truth_answer"}.issubset(df_all.columns):
        print(f"[ERROR] Dataset must have 'question' and 'ground_truth_answer' columns. Found: {list(df_all.columns)}")
        return

    ground_truth_by_question_id = load_ground_truth_json(GROUND_TRUTH_JSON)
    if ground_truth_by_question_id:
        if "question_id" not in df_all.columns:
            raise RuntimeError("Ground-truth JSON was provided, but dataset has no 'question_id' column to match on.")
        before_count = len(df_all)
        df_all = df_all[df_all["question_id"].astype(str).isin(ground_truth_by_question_id)].copy()
        df_all["ground_truth_answer"] = df_all["question_id"].astype(str).map(ground_truth_by_question_id)
        print(f"[STEP 1] Selected {len(df_all)} questions with full JSON ground truth out of {before_count}.")
        missing_in_excel = set(ground_truth_by_question_id) - set(df_all["question_id"].astype(str))
        if missing_in_excel:
            print(f"[WARN] {len(missing_in_excel)} JSON question IDs were not found in the Excel file.")

    records = pd.DataFrame({
        "Sample Row ID": df_all.get("question_id", df_all.get("global_question_id", pd.Series(range(1, len(df_all) + 1)))).astype(str),
        "Question": df_all["question"].astype(str),
        "Ground Truth": df_all["ground_truth_answer"].astype(str),
        "Difficulty": df_all.get("difficulty", pd.Series([""] * len(df_all))).astype(str),
        "Category": df_all.get("category", pd.Series([""] * len(df_all))).astype(str),
        "Query Type": df_all.get("query_type", pd.Series([""] * len(df_all))).astype(str),
        "Source CSV": df_all.get("source_csv", pd.Series([""] * len(df_all))).astype(str),
    })

    limit = TEST_QUERY_LIMIT if TEST_QUERY_LIMIT > 0 else len(records)
    test_records = records.iloc[TEST_QUERY_OFFSET: TEST_QUERY_OFFSET + limit].to_dict(orient="records")
    print(f"[STEP 1] Loaded {len(test_records)} queries for evaluation.")

    results_list: list = []
    completed_row_ids: set = set()
    if os.path.exists(REPORT_FILE):
        try:
            existing = pd.read_csv(REPORT_FILE)
            if "Sample Row ID" in existing.columns:
                status_series = existing.get("New Status", pd.Series(dtype=str)).astype(str).str.upper()
                keep_mask = ~status_series.isin({"CRASH", "QUOTA_EXHAUSTED"})
                existing = existing[keep_mask].copy()
                results_list = existing.to_dict(orient="records")
                completed_row_ids = set(existing["Sample Row ID"].astype(str))
                print(f"[RESUME] Found {len(results_list)} completed rows. Skipping them.")
        except Exception as e:
            print(f"[WARN] Could not read existing report: {e}. Starting fresh.")

    pending_records = [r for r in test_records if str(r.get("Sample Row ID", "")) not in completed_row_ids]
    skipped = len(test_records) - len(pending_records)
    if skipped:
        print(f"[RESUME] Skipping {skipped} already-completed queries.")
    print(f"[SYSTEM] Pending queries this run: {len(pending_records)}")

    results_lock = threading.Lock()

    def save_report():
        df_report = pd.DataFrame(results_list)
        for col in REPORT_COLUMNS:
            if col not in df_report.columns:
                df_report[col] = ""
        df_report = df_report[REPORT_COLUMNS]
        tmp_file = f"{REPORT_FILE}.tmp"
        df_report.to_csv(tmp_file, index=False)
        os.replace(tmp_file, REPORT_FILE)

    completed_count = 0
    total_pending = len(pending_records)
    quota_exhausted = threading.Event()

    def worker(record):
        if quota_exhausted.is_set():
            return None
        return process_question(record, target_client, schema_text)

    with ThreadPoolExecutor(max_workers=PIPELINE_WORKERS) as pool:
        futures = {pool.submit(worker, r): r for r in pending_records}
        for future in as_completed(futures):
            row = future.result()
            if row is None:
                continue
            with results_lock:
                results_list.append(row)
                completed_count += 1
                save_report()
                if completed_count % 10 == 0:
                    api_logger.save()
            print(f"  [{completed_count}/{total_pending}] {row['Sample Row ID']}: {row['New Status']} "
                  f"({row.get('Elapsed Seconds', '')}s)", flush=True)
            if row["New Status"] == "QUOTA_EXHAUSTED":
                print("[SYSTEM] Quota exhausted signal seen; not scheduling further new work.")
                quota_exhausted.set()

    api_logger.save()
    wall_clock = time.perf_counter() - script_start_time

    ok_count = sum(1 for r in results_list if str(r.get("New Status", "")).upper() == "OK")
    err_count = len(results_list) - ok_count

    print(f"\n{'=' * 60}")
    print("  PIPELINE RUN COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Report:       {REPORT_FILE}")
    print(f"  Total rows:   {len(results_list)}")
    print(f"  OK:           {ok_count}")
    print(f"  ERROR/OTHER:  {err_count}")
    print(f"  Wall clock:   {wall_clock:.1f}s ({wall_clock / 60:.1f}min)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
