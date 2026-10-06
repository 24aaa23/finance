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
if BASELINES_ROOT not in sys.path:
    sys.path.insert(0, BASELINES_ROOT)

from model_provider import make_model_client, supports_temperature

DOMAIN_INTRO_FILE = os.getenv("DOMAIN_INTRO_FILE", os.path.join(BASELINES_ROOT, "domain_intro.prompt"))
BUSINESS_RULES_FILE = os.getenv("BUSINESS_RULES_FILE", os.path.join(BASELINES_ROOT, "phase0_business_rules.md"))


def load_prompt_reference_context() -> str:
    sections = []
    for title, path in (
        ("Domain introduction", DOMAIN_INTRO_FILE),
        ("Phase 0 business rules", BUSINESS_RULES_FILE),
    ):
        with open(path, encoding="utf-8") as handle:
            sections.append(f"{title}:\n{handle.read().strip()}")
    return "\n\n".join(sections)


PROMPT_REFERENCE_CONTEXT = load_prompt_reference_context()

TARGET_MODEL = os.getenv("TARGET_MODEL", "openai.gpt-oss-120b-1:0")
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION", "base-sql-domain-intro-phase0-rules-v1")
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


def build_target_client(model: str) -> LLMClient:
    return make_model_client(model)


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


# ---------------------------------------------------------------------------
# 5. SQLITE SCHEMA LOADING
# ---------------------------------------------------------------------------

def load_sqlite_schema(db_path: str) -> Dict[str, str]:
    print(f"[SYSTEM] Loading SQLite DDL from {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )

    schema: Dict[str, str] = {}
    for table_name, ddl in cursor.fetchall():
        if not ddl:
            quoted_table = '"' + str(table_name).replace('"', '""') + '"'
            cursor.execute(f"PRAGMA table_info({quoted_table})")
            columns = ", ".join(
                f'{chr(34)}{str(col[1]).replace(chr(34), chr(34) * 2)}{chr(34)} '
                f'{col[2]}{" PRIMARY KEY" if col[5] else ""}'
                for col in cursor.fetchall()
            )
            ddl = f"CREATE TABLE {quoted_table} ({columns})"
        schema[str(table_name)] = str(ddl).strip().rstrip(";") + ";"

    conn.close()
    print(f"[SYSTEM] Successfully loaded DDL for {len(schema)} tables.")
    return schema


def build_schema_text(schema: Dict[str, str]) -> str:
    return "\n\n".join(schema.values())


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
    prompt = f"""Reference context:
{PROMPT_REFERENCE_CONTEXT}

Database schema (DDL):
{schema_text}

Question:
{query}

Return only the SQL query. Do not include reasoning, explanations, markdown,
comments, or prose.
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
        return pd.read_excel(sample_file)
    return pd.read_csv(sample_file)


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
    print("\n" + "=" * 60)
    print("  BASE PIPELINE — SQL (GPT-OSS 120B, single-shot, ungraded)")
    print("=" * 60)
    print(f"[CONFIG] Target model: {TARGET_MODEL}")
    print(f"[CONFIG] Workers (concurrent questions): {PIPELINE_WORKERS}")
    print(f"[CONFIG] SQLite DB: {SQLITE_DB_PATH}")
    print(f"[CONFIG] Query window: offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT or 'all'}")
    print(f"[CONFIG] Report file: {REPORT_FILE}")
    script_start_time = time.perf_counter()

    print("\n[SYSTEM] Checking SQLite connectivity...")
    check_sqlite_health(SQLITE_DB_PATH)

    print("[SYSTEM] Building API client...")
    target_client = build_target_client(TARGET_MODEL)

    print(f"\n[STEP 1] Loading schema from {SQLITE_DB_PATH}...")
    db_schema = load_sqlite_schema(SQLITE_DB_PATH)
    schema_text = build_schema_text(db_schema)

    print(f"\n[STEP 1] Loading dataset from {INPUT_SAMPLE_FILE}...")
    df_all = load_input_samples(INPUT_SAMPLE_FILE)
    if not {"question", "ground_truth_answer"}.issubset(df_all.columns):
        print(f"[ERROR] Dataset must have 'question' and 'ground_truth_answer' columns. Found: {list(df_all.columns)}")
        return

    records = pd.DataFrame({
        "Sample Row ID": df_all.get("global_question_id", pd.Series(range(1, len(df_all) + 1))).astype(str),
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
