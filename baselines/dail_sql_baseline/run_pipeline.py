#!/usr/bin/env python3
"""DAIL-SQL adaptation for the 1,000-question wealth-management benchmark.

The upstream DAIL-SQL flow is preserved in two stages:
1. Select nine examples by masked-question distance and generate preliminary SQL.
2. Re-select examples using preliminary-SQL skeleton similarity plus question
   distance, generate final SQL, and execute it read-only on SQLite.

The original implementation uses Stanford CoreNLP and all-mpnet-base-v2 for
schema linking and distance. This single-database adaptation performs local
schema-aware masking and normalized TF-IDF Euclidean distance so it can run in
the existing baseline environment without changing the database or downloading
additional models. Example organization and skeleton-threshold selection follow
the upstream DAIL-SQL configuration.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
from openai import OpenAI


HERE = Path(__file__).resolve().parent
FINANCE_ROOT = HERE.parent
if str(FINANCE_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_ROOT))

from model_provider import make_model_client, supports_temperature

DEFAULT_DATABASE = FINANCE_ROOT.parent / "wealth_management_diverse.db"
DEFAULT_BENCHMARK = FINANCE_ROOT / "dataset" / "wealth_management_1000_questions.csv"
DEFAULT_TRAINING = HERE / "dataset" / "verification_results_v2_sql_correct_train_300.xlsx"
DEFAULT_DOMAIN_INTRO = FINANCE_ROOT / "domain_intro.prompt"
DEFAULT_BUSINESS_RULES = FINANCE_ROOT / "phase0_business_rules.md"
DEFAULT_REPORT = HERE / "output" / "dail_sql_gpt_oss_120b_domain_context_1000q.csv"
DEFAULT_ENV = FINANCE_ROOT / "base_pipeline_qwen" / ".env"

VERSION = "dail-sql-gpt-oss-120b-domain-context-9shot-v1"
DEFAULT_MODEL = "openai.gpt-oss-120b-1:0"
FATAL_STATUSES = {"MODEL_NOT_FOUND", "QUOTA_EXHAUSTED", "API_AUTH_ERROR"}

_csv_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_csv_limit)
        break
    except OverflowError:
        _csv_limit //= 10

REPORT_COLUMNS = [
    "Pipeline Version", "Run Config", "Sample Row ID", "Question", "Ground Truth",
    "Difficulty", "Category", "Query Type", "Source CSV", "New Status",
    "Generated SQL", "Scan Status", "Scan Row Count", "Scan Error", "Scan Raw Rows",
    "Target Model", "Preliminary SQL", "Question-Mask Examples", "Final DAIL Examples",
    "Preliminary SQL Skeleton", "Selection Details", "Generation Input Tokens",
    "Generation Output Tokens", "Generation Latency Seconds", "Prepass Input Tokens",
    "Prepass Output Tokens", "Prepass Latency Seconds", "Final Input Tokens",
    "Final Output Tokens", "Final Latency Seconds", "Execution Latency Seconds",
    "Prompt Characters", "Started At", "Elapsed Seconds",
]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def make_client(env_file: Path, model: str) -> OpenAI:
    load_env(env_file)
    return make_model_client(model)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_reference_context(domain_intro: Path, business_rules: Path) -> str:
    return "\n\n".join([
        f"Domain introduction:\n{domain_intro.read_text(encoding='utf-8').strip()}",
        f"Phase 0 business rules:\n{business_rules.read_text(encoding='utf-8').strip()}",
    ])


def load_schema(database: Path) -> tuple[str, set[str], list[str]]:
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
        table_rows = conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        identifiers: set[str] = set()
        ddl = []
        tables = []
        for table, statement in table_rows:
            tables.append(table)
            identifiers.add(table.lower())
            if statement:
                ddl.append(statement.rstrip().rstrip(";") + ";")
            for column in conn.execute(f'PRAGMA table_info("{table}")').fetchall():
                identifiers.add(str(column[1]).lower())
    if not ddl:
        raise ValueError(f"No SQLite tables found in {database}")
    return "\n\n".join(ddl), identifiers, tables


def phrase_patterns(identifiers: set[str]) -> list[tuple[re.Pattern[str], str]]:
    values = set()
    for identifier in identifiers:
        values.add(identifier)
        values.add(identifier.replace("_", " "))
    patterns = []
    for value in sorted(values, key=len, reverse=True):
        if len(value) < 3:
            continue
        escaped = re.escape(value).replace(r"\ ", r"[\s_-]+")
        patterns.append((re.compile(rf"(?i)(?<![a-z0-9]){escaped}(?![a-z0-9])"), " <mask> "))
    return patterns


def mask_question(question: str, patterns: list[tuple[re.Pattern[str], str]]) -> str:
    text = question.lower()
    text = re.sub(r"'[^']*'|\"[^\"]*\"", " <unk> ", text)
    text = re.sub(r"\b(?:inv|goal|txn|batch|hold|scenario)[-_]?[a-z0-9-]+\b", " <unk> ", text, flags=re.I)
    text = re.sub(r"\b\d+(?:\.\d+)?\b", " <unk> ", text)
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return " ".join(re.findall(r"<mask>|<unk>|[a-z]+", text))


def tokenize_document(text: str) -> list[str]:
    return re.findall(r"<mask>|<unk>|[a-z][a-z0-9_]+", text.lower())


class QuestionDistanceIndex:
    def __init__(self, masked_questions: list[str]):
        self.documents = [tokenize_document(text) for text in masked_questions]
        document_frequency: Counter[str] = Counter()
        for tokens in self.documents:
            document_frequency.update(set(tokens))
        count = len(self.documents)
        self.idf = {token: math.log((count + 1) / (frequency + 1)) + 1 for token, frequency in document_frequency.items()}
        self.vectors = [self._vector(tokens) for tokens in self.documents]

    def _vector(self, tokens: list[str]) -> dict[str, float]:
        frequencies = Counter(token for token in tokens if token in self.idf)
        if not frequencies:
            return {}
        values = {token: frequency * self.idf[token] for token, frequency in frequencies.items()}
        norm = math.sqrt(sum(value * value for value in values.values())) or 1.0
        return {token: value / norm for token, value in values.items()}

    def distances(self, masked_question: str) -> list[float]:
        target = self._vector(tokenize_document(masked_question))
        result = []
        for vector in self.vectors:
            dot = sum(value * vector.get(token, 0.0) for token, value in target.items())
            result.append(math.sqrt(max(0.0, 2.0 - 2.0 * dot)))
        return result


def clean_model_sql(raw: str) -> str:
    text = re.sub(r"(?is)<(?:think|reasoning)>.*?</(?:think|reasoning)>", "", raw or "").strip()
    text = re.sub(r"(?is)^```(?:sql)?\s*|\s*```$", "", text).strip()
    match = re.search(r"(?is)\b(?:WITH|SELECT)\b", text)
    if not match:
        return ""
    text = text[match.start():].strip()
    if ";" in text:
        text = text.split(";", 1)[0].strip() + ";"
    return text


def sql_skeleton(sql: str, schema_identifiers: set[str]) -> str:
    text = clean_model_sql(sql).lower()
    text = re.sub(r"--[^\n]*|/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"", " _ ", text)
    text = re.sub(r"\b\d+(?:\.\d+)?\b", " _ ", text)
    tokens = re.findall(r">=|<=|<>|!=|[a-z_][a-z0-9_$]*|[(),.*=<>+\-/]", text)
    result = ["_" if token in schema_identifiers else token for token in tokens]
    skeleton = " ".join(result)
    while "_ , _" in skeleton:
        skeleton = skeleton.replace("_ , _", "_")
    return re.sub(r"\s+", " ", skeleton).strip()


def multiset_jaccard(left: str, right: str) -> float:
    a, b = Counter(left.split()), Counter(right.split())
    if not a and not b:
        return 1.0
    intersection = sum(min(a[token], b[token]) for token in a.keys() | b.keys())
    union = sum(max(a[token], b[token]) for token in a.keys() | b.keys())
    return intersection / union if union else 0.0


def build_prompt(
    question: str,
    examples: list[dict[str, str]],
    ddl: str,
    reference_context: str,
) -> str:
    example_blocks = [
        f"/* Answer the following: {example['question']} */\n{example['sql_query'].strip()}"
        for example in examples
    ]
    return "\n\n".join([
        "Reference context:\n" + reference_context,
        "/* Some SQL examples are provided based on similar problems: */\n" + "\n\n".join(example_blocks),
        "/* Given the following database schema: */\n" + ddl,
        f"/* Answer the following: {question} */",
        "Return only the complete SQLite SQL query. Do not include reasoning, explanations, markdown, comments, or prose.",
    ])


def generate_sql(client: OpenAI, model: str, prompt: str) -> dict[str, Any]:
    started = time.perf_counter()
    request: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if supports_temperature(model):
        request["temperature"] = 0
    response = client.chat.completions.create(**request)
    latency = time.perf_counter() - started
    if not response.choices:
        raise RuntimeError("Model returned no choices")
    finish_reason = str(response.choices[0].finish_reason or "").lower()
    if finish_reason == "length":
        raise RuntimeError("Model output was truncated: finish_reason=length")
    raw = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    return {
        "sql": clean_model_sql(raw),
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "latency": latency,
    }


def classify_api_error(exc: Exception) -> str:
    text = f"{getattr(exc, 'code', '')} {exc}".lower()
    if "model_not_found" in text or "does not exist or you do not have access" in text:
        return "MODEL_NOT_FOUND"
    if any(value in text for value in ("insufficient_quota", "credit_balance_exhausted", "no credits remaining", "quota")):
        return "QUOTA_EXHAUSTED"
    if "authentication" in text or "invalid api key" in text or "unauthorized" in text:
        return "API_AUTH_ERROR"
    if "rate limit" in text or "rate_limit" in text:
        return "RATE_LIMIT_ERROR"
    return "GENERATION_ERROR"


def sqlite_authorizer(action: int, arg1: str | None, arg2: str | None, db: str | None, trigger: str | None) -> int:
    allowed = {
        sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in {
        "load_extension", "writefile", "readfile", "fts3_tokenizer",
    }:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def execute_sql(database: Path, sql: str, timeout: float) -> dict[str, Any]:
    if not sql:
        return {"status": "EMPTY_SQL", "rows": [], "error": "Model returned no SQL", "latency": 0.0}
    started = time.perf_counter()
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=timeout) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.row_factory = sqlite3.Row
            conn.set_authorizer(sqlite_authorizer)
            cursor = conn.execute(sql)
            rows = [dict(row) for row in cursor.fetchall()]
        return {"status": "success", "rows": rows, "error": "", "latency": time.perf_counter() - started}
    except Exception as exc:
        return {"status": "EXEC_ERROR", "rows": [], "error": str(exc), "latency": time.perf_counter() - started}


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def read_existing(path: Path, config: str) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if rows and {row.get("Run Config", "") for row in rows} != {config}:
        raise ValueError(f"Existing report configuration differs: {path}")
    return rows


def select_examples(
    training: list[dict[str, str]],
    distances: list[float],
    target: dict[str, str],
    count: int,
    target_skeleton: str | None = None,
    threshold: float = 0.85,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    candidates = []
    target_id = target.get("global_question_id", "")
    target_question = " ".join(target["question"].lower().split())
    for index, example in enumerate(training):
        if example.get("global_question_id", "") == target_id:
            continue
        if " ".join(example["question"].lower().split()) == target_question:
            continue
        similarity = multiset_jaccard(example["sql_skeleton"], target_skeleton) if target_skeleton else None
        candidates.append((index, distances[index], similarity))
    ordered = sorted(candidates, key=lambda value: value[1])
    if target_skeleton:
        preferred = [value for value in ordered if (value[2] or 0.0) >= threshold]
        fallback = [value for value in ordered if (value[2] or 0.0) < threshold]
        ordered = preferred + fallback
    chosen = ordered[:count]
    return (
        [training[index] for index, _, _ in chosen],
        [
            {
                "global_question_id": training[index].get("global_question_id", ""),
                "question_distance": round(distance, 6),
                "skeleton_similarity": None if similarity is None else round(similarity, 6),
            }
            for index, distance, similarity in chosen
        ],
    )


def run(args: argparse.Namespace) -> None:
    for path in (args.database, args.benchmark, args.training, args.domain_intro, args.business_rules):
        if not path.exists():
            raise FileNotFoundError(path)
    client = make_client(args.env_file, args.model)
    ddl, identifiers, tables = load_schema(args.database)
    patterns = phrase_patterns(identifiers)
    reference_context = load_reference_context(args.domain_intro, args.business_rules)

    benchmark = pd.read_csv(args.benchmark, dtype=str, keep_default_na=False)
    training_frame = pd.read_excel(args.training, dtype=str, keep_default_na=False)
    required_eval = {"global_question_id", "question", "ground_truth_answer"}
    required_train = {"global_question_id", "question", "sql_query"}
    if not required_eval.issubset(benchmark.columns):
        raise ValueError(f"Benchmark missing columns: {sorted(required_eval - set(benchmark.columns))}")
    if not required_train.issubset(training_frame.columns):
        raise ValueError(f"Training workbook missing columns: {sorted(required_train - set(training_frame.columns))}")
    training = training_frame.to_dict(orient="records")
    for example in training:
        example["masked_question"] = mask_question(example["question"], patterns)
        example["sql_skeleton"] = sql_skeleton(example["sql_query"], identifiers)
    distance_index = QuestionDistanceIndex([example["masked_question"] for example in training])

    selected = benchmark.iloc[args.offset:] if args.limit == 0 else benchmark.iloc[args.offset:args.offset + args.limit]
    config = json.dumps({
        "version": VERSION, "model": args.model, "database": str(args.database.resolve()),
        "benchmark": str(args.benchmark.resolve()), "training": str(args.training.resolve()),
        "training_sha256": file_sha256(args.training), "k_shot": args.k_shot,
        "skeleton_threshold": args.skeleton_threshold, "workers": args.workers,
        "domain_intro_sha256": file_sha256(args.domain_intro),
        "business_rules_sha256": file_sha256(args.business_rules),
    }, sort_keys=True)
    rows = read_existing(args.report, config)
    completed = {row["Sample Row ID"] for row in rows}
    pending = [item for _, item in selected.iterrows() if str(item["global_question_id"]) not in completed]

    print(f"[CONFIG] Version: {VERSION}")
    print(f"[CONFIG] Model: {args.model}")
    print(f"[CONFIG] Tables: {len(tables)}; training examples: {len(training)}")
    print(f"[CONFIG] Benchmark questions: {len(selected)}; resumed: {len(completed)}; pending: {len(pending)}")
    print(f"[CONFIG] Report: {args.report}")

    lock = threading.Lock()
    fatal = threading.Event()
    finished = 0

    def process(item: pd.Series) -> dict[str, Any]:
        started_at = dt.datetime.now(dt.timezone.utc).isoformat()
        started = time.perf_counter()
        sample_id = str(item["global_question_id"])
        question = str(item["question"])
        base = {
            "Pipeline Version": VERSION, "Run Config": config, "Sample Row ID": sample_id,
            "Question": question, "Ground Truth": str(item["ground_truth_answer"]),
            "Difficulty": str(item.get("difficulty", "")), "Category": str(item.get("category", "")),
            "Query Type": str(item.get("query_type", "")), "Source CSV": str(item.get("source_csv", "")),
            "Target Model": args.model, "Started At": started_at,
        }
        masked = mask_question(question, patterns)
        distances = distance_index.distances(masked)
        pre_examples, pre_details = select_examples(training, distances, item.to_dict(), args.k_shot)
        pre_prompt = build_prompt(question, pre_examples, ddl, reference_context)
        try:
            pre = generate_sql(client, args.model, pre_prompt)
        except Exception as exc:
            status = classify_api_error(exc)
            if status in FATAL_STATUSES:
                fatal.set()
            return {**base, "New Status": status, "Scan Status": status, "Scan Error": str(exc),
                    "Question-Mask Examples": json.dumps(pre_details), "Prompt Characters": len(pre_prompt),
                    "Elapsed Seconds": round(time.perf_counter() - started, 3)}

        pre_skeleton = sql_skeleton(pre["sql"], identifiers)
        final_examples, final_details = select_examples(
            training, distances, item.to_dict(), args.k_shot,
            target_skeleton=pre_skeleton, threshold=args.skeleton_threshold,
        )
        final_prompt = build_prompt(question, final_examples, ddl, reference_context)
        try:
            final = generate_sql(client, args.model, final_prompt)
        except Exception as exc:
            status = classify_api_error(exc)
            if status in FATAL_STATUSES:
                fatal.set()
            return {**base, "New Status": status, "Scan Status": status, "Scan Error": str(exc),
                    "Preliminary SQL": pre["sql"], "Question-Mask Examples": json.dumps(pre_details),
                    "Final DAIL Examples": json.dumps(final_details), "Preliminary SQL Skeleton": pre_skeleton,
                    "Prepass Input Tokens": pre["input_tokens"], "Prepass Output Tokens": pre["output_tokens"],
                    "Prepass Latency Seconds": round(pre["latency"], 3),
                    "Prompt Characters": len(pre_prompt) + len(final_prompt),
                    "Elapsed Seconds": round(time.perf_counter() - started, 3)}

        execution = execute_sql(args.database, final["sql"], args.query_timeout)
        success = execution["status"] == "success"
        return {
            **base,
            "New Status": "UNGRADED" if success else execution["status"],
            "Generated SQL": final["sql"], "Scan Status": execution["status"],
            "Scan Row Count": len(execution["rows"]) if success else "", "Scan Error": execution["error"],
            "Scan Raw Rows": json.dumps(execution["rows"], ensure_ascii=False, default=str) if success else "",
            "Preliminary SQL": pre["sql"], "Question-Mask Examples": json.dumps(pre_details),
            "Final DAIL Examples": json.dumps(final_details), "Preliminary SQL Skeleton": pre_skeleton,
            "Selection Details": json.dumps({"method": "EUCDISMASKPRESKLSIMTHR", "k": args.k_shot,
                                                "threshold": args.skeleton_threshold}),
            "Generation Input Tokens": pre["input_tokens"] + final["input_tokens"],
            "Generation Output Tokens": pre["output_tokens"] + final["output_tokens"],
            "Generation Latency Seconds": round(pre["latency"] + final["latency"], 3),
            "Prepass Input Tokens": pre["input_tokens"], "Prepass Output Tokens": pre["output_tokens"],
            "Prepass Latency Seconds": round(pre["latency"], 3),
            "Final Input Tokens": final["input_tokens"], "Final Output Tokens": final["output_tokens"],
            "Final Latency Seconds": round(final["latency"], 3),
            "Execution Latency Seconds": round(execution["latency"], 3),
            "Prompt Characters": len(pre_prompt) + len(final_prompt),
            "Elapsed Seconds": round(time.perf_counter() - started, 3),
        }

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process, item) for item in pending]
        for future in as_completed(futures):
            row = future.result()
            with lock:
                rows.append(row)
                finished += 1
                write_report(args.report, rows)
            print(f"[{finished}/{len(pending)}] {row['Sample Row ID']}: {row.get('Scan Status', row.get('New Status'))}", flush=True)
            if fatal.is_set():
                for remaining in futures:
                    remaining.cancel()
                break

    print(f"Report: {args.report}")
    print(f"Rows: {len(rows)}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    result.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    result.add_argument("--training", type=Path, default=DEFAULT_TRAINING)
    result.add_argument("--domain-intro", type=Path, default=DEFAULT_DOMAIN_INTRO)
    result.add_argument("--business-rules", type=Path, default=DEFAULT_BUSINESS_RULES)
    result.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    result.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    result.add_argument("--model", default=DEFAULT_MODEL)
    result.add_argument("--k-shot", type=int, default=9)
    result.add_argument("--skeleton-threshold", type=float, default=0.85)
    result.add_argument("--workers", type=int, default=int(os.getenv("PIPELINE_WORKERS", "6")))
    result.add_argument("--query-timeout", type=float, default=60.0)
    result.add_argument("--offset", type=int, default=0)
    result.add_argument("--limit", type=int, default=0, help="0 means all remaining questions")
    return result


if __name__ == "__main__":
    run(parser().parse_args())
