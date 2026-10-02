"""Three-copy, single-shot, ungraded Text-to-SQL ensemble baseline.

For every question, independent copies each perform exactly one:

    generate SQL -> execute read-only on SQLite

The pipeline returns a result only when a strict majority of successful copies
produce the same result set. It stores every branch's SQL, rows, diagnostics,
latency, and token usage for later offline grading. Ground truth is written to
the report but is never sent to the generator. Fuseki and the RDF graph are not
used by this baseline.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
from openai import OpenAI

from env import BASE_ENV, load_base_pipeline_env


load_base_pipeline_env()

HERE = Path(__file__).resolve().parent
BASELINES = HERE.parent
FINANCE = BASELINES.parent

VERSION = "parallel-text-to-sql-ensemble-single-shot-ungraded-v1"
DEFAULT_TARGET_MODEL = os.getenv("TARGET_MODEL", "openai.gpt-oss-120b-1:0")
DEFAULT_DATABASE = FINANCE / "wealth_management_diverse.db"
DEFAULT_BENCHMARK = BASELINES / "dataset" / "wealth_management_1000_questions.csv"
DEFAULT_REPORT = HERE / "output" / "parallel_sql_gpt_oss_120b_1000q.csv"
DEFAULT_QUESTION_WORKERS = int(os.getenv("PIPELINE_WORKERS", "3"))

FATAL_API_STATUSES = {
    "MODEL_NOT_FOUND",
    "QUOTA_EXHAUSTED",
    "RATE_LIMIT_ERROR",
    "API_AUTH_ERROR",
}

_csv_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_csv_limit)
        break
    except OverflowError:
        _csv_limit //= 10


REPORT_COLUMNS = [
    "Pipeline Version",
    "Run Config",
    "Sample Row ID",
    "Question",
    "Ground Truth",
    "Difficulty",
    "Category",
    "Query Type",
    "Source CSV",
    "Pipeline Status",
    "New Status",
    "Consensus Achieved",
    "Consensus Size",
    "Winning Copies",
    "Ensemble Result",
    "Processed Rows",
    "Final SQL",
    "Final Scan Row Count",
    "Branch Results",
    "Target Model",
    "Generation Input Tokens",
    "Generation Output Tokens",
    "Started At",
    "Elapsed Seconds",
]


class APILogger:
    """Thread-safe API-call counter with the same format as the other baselines."""

    def __init__(self, output_dir: Path):
        self._lock = threading.Lock()
        self._calls: dict[str, dict[str, Any]] = {}
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = output_dir / f"api_usage_log_{timestamp}.json"

    def log(self, question: str, operation: str) -> None:
        with self._lock:
            item = self._calls.setdefault(
                question or "Unknown_Query", {"total_calls": 0, "functions": {}}
            )
            item["total_calls"] += 1
            item["functions"][operation] = item["functions"].get(operation, 0) + 1

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(self._calls, indent=2), encoding="utf-8")
            temporary.replace(self.path)


@dataclass
class BranchResult:
    copy_id: int
    status: str = "STARTED"
    sql: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    result_fingerprint: str = ""
    error: str = ""
    generation_input_tokens: int = 0
    generation_output_tokens: int = 0
    generation_latency_seconds: float = 0.0
    execution_latency_seconds: float = 0.0
    elapsed_seconds: float = 0.0


def make_target_client() -> OpenAI:
    key = (
        os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not key:
        raise RuntimeError(f"A Bedrock API key is missing from the environment and {BASE_ENV}")
    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError("Set BEDROCK_REGION or BEDROCK_BASE_URL.")
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"
    return OpenAI(api_key=key, base_url=base_url, timeout=180, max_retries=1)


def classify_api_exception(exc: Exception) -> str:
    combined = f"{getattr(exc, 'code', '')} {exc}".lower()
    if "model_not_found" in combined or "does not exist or you do not have access" in combined:
        return "MODEL_NOT_FOUND"
    if any(marker in combined for marker in (
        "insufficient_quota", "credit_balance_exhausted", "no credits remaining", "quota"
    )):
        return "QUOTA_EXHAUSTED"
    if "rate_limit" in combined or "rate limit" in combined or "429" in combined:
        return "RATE_LIMIT_ERROR"
    if any(marker in combined for marker in (
        "authentication", "invalid api key", "access denied", "access_denied", "401"
    )):
        return "API_AUTH_ERROR"
    if any(marker in combined for marker in (
        "context_length_exceeded", "maximum context length", "finish_reason=length"
    )):
        return "TOKEN_OUTPUT_ERROR"
    return "GENERATION_ERROR"


def load_sqlite_schema(database: Path) -> dict[str, str]:
    """Read only table DDL. Do not read row counts or sample values."""
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        tables = list(connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ))
        schema: dict[str, str] = {}
        for table, ddl in tables:
            quoted_table = quote_identifier(table)
            if not ddl:
                columns = list(connection.execute(f"PRAGMA table_info({quoted_table})"))
                definitions = ", ".join(
                    f"{quote_identifier(column[1])} {column[2]}"
                    f"{' PRIMARY KEY' if column[5] else ''}"
                    for column in columns
                )
                ddl = f"CREATE TABLE {quoted_table} ({definitions})"
            schema[str(table)] = str(ddl).strip().rstrip(";") + ";"
        return schema
    finally:
        connection.close()


def quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def build_schema_text(schema: dict[str, str]) -> str:
    return "\n\n".join(schema.values())


def strip_reasoning_and_extract_sql(raw: str) -> str:
    text = re.sub(r"(?is)<(?:reasoning|think)>.*?</(?:reasoning|think)>", "", raw or "").strip()
    blocks = re.findall(r"```(?:sql)?\s*(.*?)```", text, flags=re.I | re.S)
    text = (blocks[-1] if blocks else text).strip()
    start = re.search(r"(?im)^\s*(?:SELECT|WITH)\b", text)
    return text[start.start():].strip() if start else text


def generate_sql(
    client: OpenAI,
    model: str,
    question: str,
    schema_text: str,
    copy_id: int,
    temperature: float,
    api_logger: APILogger,
) -> tuple[str, int, int]:
    prompt = f"""Database schema (DDL):
{schema_text}

Question:
{question}

Return only the SQL query. Do not include reasoning, explanations, markdown,
comments, or prose.
""".strip()
    request: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = temperature
    api_logger.log(question, f"Copy_{copy_id}_Generate_SQL")
    response = client.chat.completions.create(**request)
    if not response.choices:
        raise ValueError("SQL generator returned no choices.")
    if str(response.choices[0].finish_reason or "").lower() == "length":
        raise ValueError("SQL generator output was truncated: finish_reason=length.")
    usage = getattr(response, "usage", None)
    return (
        strip_reasoning_and_extract_sql(response.choices[0].message.content or ""),
        int(getattr(usage, "prompt_tokens", 0) or 0),
        int(getattr(usage, "completion_tokens", 0) or 0),
    )


def _authorize_read_only(action: int, arg1: str | None, arg2: str | None, db: str, trigger: str) -> int:
    allowed = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in {
        "load_extension", "readfile", "writefile"
    }:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def execute_sql(
    sql: str,
    database: Path,
    timeout_seconds: float,
    max_result_rows: int = 0,
) -> dict[str, Any]:
    """Execute exactly one statement using a read-only SQLite connection."""
    if not sql.strip():
        return {"status": "error", "data": [], "row_count": 0, "error_message": "Empty SQL query."}
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.set_authorizer(_authorize_read_only)
        deadline = time.monotonic() + timeout_seconds
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        cursor = connection.execute(sql)
        if cursor.description is None:
            raise ValueError("Generated statement did not return rows.")
        names = [description[0] for description in cursor.description]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate output column names; use unique aliases.")
        raw_rows = cursor.fetchmany(max_result_rows + 1) if max_result_rows else cursor.fetchall()
        if max_result_rows and len(raw_rows) > max_result_rows:
            raise ValueError(
                f"Result exceeds {max_result_rows} rows; cannot claim a complete result."
            )
        rows = [dict(row) for row in raw_rows]
        return {"status": "success", "data": rows, "row_count": len(rows)}
    except Exception as exc:  # preserve the failed branch without cancelling peers
        return {
            "status": "error",
            "data": [],
            "row_count": 0,
            "error_message": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if connection is not None:
            connection.set_progress_handler(None, 0)
            connection.close()


def normalize_consensus_value(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NULL", "NONE", "NAN"}:
        return None
    try:
        number = Decimal(text)
        if number.is_finite():
            normalized = format(number.normalize(), "f")
            return "0" if normalized in {"-0", "-0.0"} else normalized
    except (InvalidOperation, ValueError):
        pass
    return re.sub(r"\s+", " ", text).casefold()


def question_requires_order(question: str) -> bool:
    return bool(re.search(
        r"\b(top|bottom|highest|lowest|greatest|least|first|last|latest|earliest|"
        r"rank(?:ed|ing)?|order(?:ed)?|sort(?:ed)?|ascending|descending|chronological)\b",
        question,
        re.IGNORECASE,
    ))


def result_fingerprint(rows: list[dict[str, Any]], *, ordered: bool = False) -> str:
    """Normalize values but preserve column-name case, duplicates, and requested order."""
    normalized_rows = [
        json.dumps(
            {str(key): normalize_consensus_value(value) for key, value in sorted(row.items())},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in rows
    ]
    payload = json.dumps(
        normalized_rows if ordered else sorted(normalized_rows),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def serialize_rows(rows: list[dict[str, Any]], compact_after: int = 110_000) -> str:
    """Serialize every result row; use columnar JSON for size, never truncate."""
    serialized = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(serialized) <= compact_after:
        return serialized
    columns = list(dict.fromkeys(str(key) for row in rows for key in row))
    columnar = {
        "format": "columnar",
        "columns": columns,
        "rows": [[row.get(column) for column in columns] for row in rows],
        "total_rows": len(rows),
    }
    return json.dumps(columnar, ensure_ascii=False, separators=(",", ":"), default=str)


def run_branch(
    *,
    copy_id: int,
    question: str,
    schema_text: str,
    client: OpenAI,
    model: str,
    database: Path,
    query_timeout: float,
    max_result_rows: int,
    temperature: float,
    api_logger: APILogger,
) -> BranchResult:
    started = time.perf_counter()
    branch = BranchResult(copy_id=copy_id)
    try:
        generation_started = time.perf_counter()
        sql, input_tokens, output_tokens = generate_sql(
            client, model, question, schema_text, copy_id, temperature, api_logger
        )
        branch.generation_latency_seconds = round(time.perf_counter() - generation_started, 3)
        branch.sql = sql
        branch.generation_input_tokens = input_tokens
        branch.generation_output_tokens = output_tokens

        execution_started = time.perf_counter()
        scan = execute_sql(sql, database, query_timeout, max_result_rows)
        branch.execution_latency_seconds = round(time.perf_counter() - execution_started, 3)
        if scan["status"] != "success":
            branch.status = "SCAN_ERROR"
            branch.error = str(scan.get("error_message", "Unknown SQLite error"))[:1000]
            return branch

        branch.rows = scan["data"]
        branch.row_count = scan["row_count"]
        branch.result_fingerprint = result_fingerprint(
            branch.rows, ordered=question_requires_order(question)
        )
        branch.status = "COMPLETED"
        return branch
    except Exception as exc:
        branch.status = classify_api_exception(exc)
        branch.error = f"{type(exc).__name__}: {exc}"[:1000]
        return branch
    finally:
        branch.elapsed_seconds = round(time.perf_counter() - started, 3)


def find_consensus(branches: list[BranchResult]) -> tuple[list[BranchResult], int]:
    threshold = len(branches) // 2 + 1
    groups: dict[str, list[BranchResult]] = defaultdict(list)
    for branch in branches:
        if branch.status == "COMPLETED" and branch.result_fingerprint:
            groups[branch.result_fingerprint].append(branch)
    winner = max(
        groups.values(),
        key=lambda group: (len(group), -min(item.copy_id for item in group)),
        default=[],
    )
    return (winner if len(winner) >= threshold else []), threshold


def branch_summary(branch: BranchResult) -> dict[str, Any]:
    return {
        "copy_id": branch.copy_id,
        "status": branch.status,
        "sql": branch.sql,
        "row_count": branch.row_count,
        "rows": serialize_rows(branch.rows),
        "result_fingerprint": branch.result_fingerprint,
        "error": branch.error,
        "generation_input_tokens": branch.generation_input_tokens,
        "generation_output_tokens": branch.generation_output_tokens,
        "generation_latency_seconds": branch.generation_latency_seconds,
        "execution_latency_seconds": branch.execution_latency_seconds,
        "elapsed_seconds": branch.elapsed_seconds,
    }


def run_ensemble_question(
    *,
    question: str,
    schema_text: str,
    copies: int,
    branch_kwargs: dict[str, Any],
) -> dict[str, Any]:
    branches: list[BranchResult] = []
    with ThreadPoolExecutor(max_workers=copies, thread_name_prefix="sql-ensemble") as pool:
        futures = [
            pool.submit(
                run_branch,
                copy_id=copy_id,
                question=question,
                schema_text=schema_text,
                **branch_kwargs,
            )
            for copy_id in range(1, copies + 1)
        ]
        for future in as_completed(futures):
            branches.append(future.result())
    branches.sort(key=lambda branch: branch.copy_id)
    winners, threshold = find_consensus(branches)
    return {
        "pipeline_status": "CONSENSUS" if winners else "FAILURE_NO_CONSENSUS",
        "consensus": bool(winners),
        "consensus_size": len(winners),
        "threshold": threshold,
        "winners": winners,
        "winner": winners[0] if winners else None,
        "branches": branches,
    }


def load_benchmark(path: Path) -> pd.DataFrame:
    frame = pd.read_excel(path) if path.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(path)
    required = {"global_question_id", "question", "ground_truth_answer"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Benchmark must contain columns: {sorted(required)}")
    return frame


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_existing_report(path: Path, config: str) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if rows and any(row.get("Run Config") != config for row in rows):
        raise ValueError(f"Existing report uses a different configuration: {path}")
    return rows


def run(args: argparse.Namespace) -> None:
    if args.copies < 3 or args.copies % 2 == 0:
        raise ValueError("--copies must be an odd number of at least 3.")
    if args.workers < 1 or args.offset < 0 or args.limit < 0:
        raise ValueError("--workers must be positive; --offset and --limit must be nonnegative.")
    if args.query_timeout <= 0 or args.temperature < 0 or args.max_result_rows < 0:
        raise ValueError("Timeout must be positive; temperature and result-row cap must be nonnegative.")
    if not args.database.is_file():
        raise FileNotFoundError(args.database)
    if not args.benchmark.is_file():
        raise FileNotFoundError(args.benchmark)

    print(f"[SYSTEM] Loading SQLite schema from {args.database}...")
    schema_text = build_schema_text(load_sqlite_schema(args.database))
    benchmark = load_benchmark(args.benchmark)
    selected = (
        benchmark.iloc[args.offset:]
        if args.limit == 0
        else benchmark.iloc[args.offset:args.offset + args.limit]
    )
    config = json.dumps({
        "version": VERSION,
        "copies": args.copies,
        "target_model": args.target_model,
        "temperature": args.temperature,
        "database": str(args.database.resolve()),
        "benchmark": str(args.benchmark.resolve()),
        "query_timeout": args.query_timeout,
        "max_result_rows": args.max_result_rows,
    }, sort_keys=True)
    rows = read_existing_report(args.report, config)
    completed = {row["Sample Row ID"] for row in rows}
    pending = [
        item for _, item in selected.iterrows()
        if str(item["global_question_id"]) not in completed
    ]

    client = make_target_client()
    api_logger = APILogger(args.report.parent)
    branch_kwargs = {
        "client": client,
        "model": args.target_model,
        "database": args.database,
        "query_timeout": args.query_timeout,
        "max_result_rows": args.max_result_rows,
        "temperature": args.temperature,
        "api_logger": api_logger,
    }
    print(
        f"[SYSTEM] Pending questions: {len(pending)} "
        f"(question workers={args.workers}, copies={args.copies})"
    )

    results_lock = threading.Lock()
    fatal_api_failure = threading.Event()
    completed_count = 0

    def worker(item: pd.Series) -> dict[str, Any] | None:
        if fatal_api_failure.is_set():
            return None
        sample_id = str(item["global_question_id"])
        started_at = dt.datetime.now().isoformat(timespec="seconds")
        started = time.perf_counter()
        question = str(item["question"])
        outcome = run_ensemble_question(
            question=question,
            schema_text=schema_text,
            copies=args.copies,
            branch_kwargs=branch_kwargs,
        )
        winner: BranchResult | None = outcome["winner"]
        final_rows = winner.rows if winner else []
        branches: list[BranchResult] = outcome["branches"]
        return {
            "Pipeline Version": VERSION,
            "Run Config": config,
            "Sample Row ID": sample_id,
            "Question": question,
            "Ground Truth": str(item["ground_truth_answer"]),
            "Difficulty": str(item.get("difficulty", "")),
            "Category": str(item.get("category", "")),
            "Query Type": str(item.get("query_type", "")),
            "Source CSV": str(item.get("source_csv", "")),
            "Pipeline Status": outcome["pipeline_status"],
            "New Status": outcome["pipeline_status"],
            "Consensus Achieved": outcome["consensus"],
            "Consensus Size": outcome["consensus_size"],
            "Winning Copies": json.dumps([branch.copy_id for branch in outcome["winners"]]),
            "Ensemble Result": serialize_rows(final_rows),
            "Processed Rows": serialize_rows(final_rows),
            "Final SQL": winner.sql if winner else "",
            "Final Scan Row Count": winner.row_count if winner else "",
            "Branch Results": json.dumps(
                [branch_summary(branch) for branch in branches], ensure_ascii=False
            ),
            "Target Model": args.target_model,
            "Generation Input Tokens": sum(branch.generation_input_tokens for branch in branches),
            "Generation Output Tokens": sum(branch.generation_output_tokens for branch in branches),
            "Started At": started_at,
            "Elapsed Seconds": round(time.perf_counter() - started, 3),
        }

    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="sql-question") as pool:
        futures = [pool.submit(worker, item) for item in pending]
        for future in as_completed(futures):
            row = future.result()
            if row is None:
                continue
            branches = json.loads(row["Branch Results"])
            fatal_branch_count = sum(
                branch["status"] in FATAL_API_STATUSES for branch in branches
            )
            # One transient provider failure must not stop a question whose
            # remaining copies still reached strict consensus. Stop only when
            # a majority of copies reports a fatal provider condition.
            if fatal_branch_count >= args.copies // 2 + 1:
                fatal_api_failure.set()
            with results_lock:
                rows.append(row)
                completed_count += 1
                write_report(args.report, rows)
                if completed_count % 10 == 0:
                    api_logger.save()
            print(
                f"[{completed_count}/{len(pending)}] {row['Sample Row ID']}: "
                f"{row['Pipeline Status']}; consensus={row['Consensus Size']}/{args.copies}",
                flush=True,
            )
    api_logger.save()
    print(f"Report: {args.report}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-model", default=DEFAULT_TARGET_MODEL)
    parser.add_argument("--copies", type=int, default=int(os.getenv("PARALLEL_COPIES", "3")))
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_QUESTION_WORKERS,
        help="concurrent questions; each question uses --copies generator branches",
    )
    parser.add_argument("--offset", type=int, default=int(os.getenv("TEST_QUERY_OFFSET", "0")))
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("TEST_QUERY_LIMIT", "0")),
        help="0 means all remaining rows",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=float(os.getenv("GENERATION_TEMPERATURE", "0.3")),
    )
    parser.add_argument(
        "--query-timeout",
        type=float,
        default=float(os.getenv("SQLITE_QUERY_TIMEOUT_SECONDS", "60")),
    )
    parser.add_argument(
        "--max-result-rows",
        type=int,
        default=int(os.getenv("SQLITE_MAX_RESULT_ROWS", "0")),
        help="0 disables the row cap; a positive cap fails rather than truncates oversized results",
    )
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
