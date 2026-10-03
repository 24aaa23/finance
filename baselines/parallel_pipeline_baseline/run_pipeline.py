"""Single-shot, ungraded, concurrent parallel Text-to-SPARQL ensemble baseline.

For every question, 3 independent copies each get exactly ONE
generate -> execute attempt (no per-branch repair retry, no ensemble
round retry). Every branch's full result (SPARQL, raw rows, execution
status, latency, tokens) is stored — not just the consensus winner — so
grading can happen later, per branch or on the consensus set.

Questions are processed concurrently (bounded outer thread pool); each
question's 3 copies run in their own inner thread pool, same as the
original design.

Reuses schema/prompt/execution/validation/consensus logic from run.py
(unchanged) and drops only the grading calls and the two retry loops.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from openai import OpenAI

from env import load_base_pipeline_env
import run as base  # reuse schema/prompt/execution/validation/consensus helpers, unmodified

load_base_pipeline_env()

HERE = Path(__file__).resolve().parent
BASELINES = HERE.parent
FINANCE = BASELINES.parent
SCRIPT_DIFF_ROOT = FINANCE / "script_diff_llm"

VERSION = "parallel-sparql-domain-intro-phase0-rules-v1"
DEFAULT_TARGET_MODEL = os.getenv("TARGET_MODEL", "openai.gpt-oss-120b-1:0")
DEFAULT_SCHEMA = SCRIPT_DIFF_ROOT / "kg" / "wealth_management_diverse_schema.ttl"
DEFAULT_BENCHMARK = BASELINES / "dataset" / "wealth_management_1000_questions.csv"
DEFAULT_REPORT = HERE / "output" / "parallel_pipeline_single_shot_ungraded.csv"
DEFAULT_FUSEKI_ENDPOINT = os.getenv("FUSEKI_ENDPOINT", "http://127.0.0.1:3030/wealth/query")
DEFAULT_QUESTION_WORKERS = int(os.getenv("PIPELINE_WORKERS", "3"))

# RDFLib's shared SPARQL parser grammar is not safe under concurrent parseQuery
# calls. Serialize only local validation; generation and Fuseki execution remain
# parallel.
SPARQL_VALIDATION_LOCK = threading.Lock()

_csv_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_csv_limit)
        break
    except OverflowError:
        _csv_limit //= 10

REPORT_COLUMNS = [
    "Pipeline Version", "Run Config", "Sample Row ID", "Question", "Ground Truth",
    "Difficulty", "Category", "Query Type", "Source CSV",
    "Pipeline Status", "New Status", "Consensus Achieved", "Consensus Size",
    "Winning Copies", "Ensemble Result", "Processed Rows", "Final SPARQL",
    "Final Scan Row Count", "Branch Results", "Target Model",
    "Generation Input Tokens", "Generation Output Tokens",
    "Started At", "Elapsed Seconds",
]


@dataclass
class BranchResult:
    copy_id: int
    status: str = "STARTED"
    sparql: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    result_fingerprint: str = ""
    error: str = ""
    generation_input_tokens: int = 0
    generation_output_tokens: int = 0
    generation_latency_seconds: float = 0.0
    execution_latency_seconds: float = 0.0
    elapsed_seconds: float = 0.0


def run_branch_single_shot(
    *,
    copy_id: int,
    question: str,
    schema_text: str,
    target_client: OpenAI,
    target_model: str,
    endpoint: str,
    scan_timeout: float,
    temperature: float,
    api_logger: "base.APILogger",
) -> BranchResult:
    """Exactly one generate + one execute. No repair, no grading."""
    started = time.perf_counter()
    branch = BranchResult(copy_id=copy_id)
    try:
        gen_t0 = time.perf_counter()
        sparql, input_tokens, output_tokens = base.generate_sparql(
            target_client, target_model, question, schema_text, copy_id,
            1, "", temperature, api_logger,
        )
        branch.generation_latency_seconds = round(time.perf_counter() - gen_t0, 3)
        branch.sparql = sparql
        branch.generation_input_tokens = input_tokens
        branch.generation_output_tokens = output_tokens

        try:
            with SPARQL_VALIDATION_LOCK:
                base.validate_generated_sparql(sparql, schema_text)
        except Exception as exc:
            scan = {"status": "error", "error_message": f"Pre-execution validation: {exc}"}
        else:
            exec_t0 = time.perf_counter()
            scan = base.execute_sparql(sparql, endpoint, scan_timeout)
            branch.execution_latency_seconds = round(time.perf_counter() - exec_t0, 3)

        if scan["status"] != "success":
            branch.status = "SCAN_ERROR"
            branch.error = str(scan.get("error_message", "Unknown Fuseki error"))
            return branch

        branch.rows = scan["data"]
        branch.row_count = scan["row_count"]
        branch.result_fingerprint = base.result_fingerprint(
            branch.rows, ordered=base.question_requires_order(question)
        )
        branch.status = "COMPLETED"
        return branch
    except Exception as exc:  # noqa: BLE001 - one branch must not cancel its peers
        classified = base.classify_grader_exception(exc)
        branch.status = classified if classified in base.FATAL_API_STATUSES else "GENERATION_ERROR"
        branch.error = f"{type(exc).__name__}: {exc}"[:500]
        return branch
    finally:
        branch.elapsed_seconds = round(time.perf_counter() - started, 3)


def find_consensus(branches: list[BranchResult]) -> tuple[list[BranchResult], int]:
    threshold = len(branches) // 2 + 1
    groups: dict[str, list[BranchResult]] = {}
    for b in branches:
        if b.result_fingerprint and b.status not in {"GENERATION_ERROR", "SCAN_ERROR"}:
            groups.setdefault(b.result_fingerprint, []).append(b)
    winner = max(groups.values(), key=lambda g: (len(g), -min(x.copy_id for x in g)), default=[])
    return (winner if len(winner) >= threshold else []), threshold


def branch_summary(branch: BranchResult) -> dict[str, Any]:
    return {
        "copy_id": branch.copy_id,
        "status": branch.status,
        "sparql": branch.sparql,
        "row_count": branch.row_count,
        "rows": base.serialize_rows_for_grading(branch.rows) if branch.rows else "[]",
        "result_fingerprint": branch.result_fingerprint,
        "error": branch.error,
        "generation_input_tokens": branch.generation_input_tokens,
        "generation_output_tokens": branch.generation_output_tokens,
        "generation_latency_seconds": branch.generation_latency_seconds,
        "execution_latency_seconds": branch.execution_latency_seconds,
        "elapsed_seconds": branch.elapsed_seconds,
    }


def run_ensemble_question_single_round(
    *,
    question: str,
    schema_text: str,
    copies: int,
    branch_kwargs: dict[str, Any],
) -> dict[str, Any]:
    branches: list[BranchResult] = []
    with ThreadPoolExecutor(max_workers=copies, thread_name_prefix="ensemble") as pool:
        futures = [
            pool.submit(run_branch_single_shot, copy_id=copy_id, question=question,
                        schema_text=schema_text, **branch_kwargs)
            for copy_id in range(1, copies + 1)
        ]
        for future in as_completed(futures):
            branches.append(future.result())
    branches.sort(key=lambda b: b.copy_id)
    winners, threshold = find_consensus(branches)
    return {
        "pipeline_status": "CONSENSUS" if winners else "FAILURE_NO_CONSENSUS",
        "consensus": bool(winners),
        "consensus_size": len(winners),
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
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def read_existing_report(path: Path, config: str) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if rows and any(row.get("Run Config") != config for row in rows):
        raise ValueError(f"Existing report uses a different configuration: {path}")
    return [row for row in rows if row.get("New Status", "").upper() not in base.GRADER_FAILURE_STATUSES]


def run(args: argparse.Namespace) -> None:
    if args.copies < 3 or args.copies % 2 == 0:
        raise ValueError("--copies must be an odd number of at least 3.")
    if not args.schema.is_file():
        raise FileNotFoundError(args.schema)
    if not args.benchmark.is_file():
        raise FileNotFoundError(args.benchmark)

    base.check_fuseki(args.fuseki_endpoint)
    target_client = base.make_target_client(args.target_model)
    metadata = base.load_schema(args.schema, args.fuseki_endpoint, args.metadata_timeout)
    schema_text = base.build_schema_text(metadata)
    benchmark = load_benchmark(args.benchmark)
    selected = benchmark.iloc[args.offset:] if args.limit == 0 else benchmark.iloc[args.offset:args.offset + args.limit]

    config = json.dumps({
        "version": VERSION, "copies": args.copies, "target_model": args.target_model,
        "temperature": args.temperature, "fuseki_endpoint": args.fuseki_endpoint,
        "schema": str(args.schema.resolve()), "benchmark": str(args.benchmark.resolve()),
    }, sort_keys=True)
    rows = read_existing_report(args.report, config)
    completed = {row["Sample Row ID"] for row in rows}

    api_logger = base.APILogger(args.report.parent)
    branch_kwargs = {
        "target_client": target_client,
        "target_model": args.target_model,
        "endpoint": args.fuseki_endpoint,
        "scan_timeout": args.scan_timeout,
        "temperature": args.temperature,
        "api_logger": api_logger,
    }

    pending = [item for _, item in selected.iterrows() if str(item["global_question_id"]) not in completed]
    print(f"[SYSTEM] Pending questions this run: {len(pending)} (question workers={args.workers}, copies={args.copies})")

    lock = threading.Lock()
    completed_count = 0
    quota_exhausted = threading.Event()

    def save():
        write_report(args.report, rows)

    def worker(item: pd.Series):
        if quota_exhausted.is_set():
            return None
        sample_id = str(item["global_question_id"])
        started_at = dt.datetime.now().isoformat(timespec="seconds")
        started = time.perf_counter()
        question = str(item["question"])
        ground_truth = str(item["ground_truth_answer"])
        outcome = run_ensemble_question_single_round(
            question=question, schema_text=schema_text, copies=args.copies, branch_kwargs=branch_kwargs,
        )
        winner: BranchResult | None = outcome["winner"]
        final_rows = winner.rows if winner else []
        branches = outcome["branches"]
        return {
            "Pipeline Version": VERSION, "Run Config": config, "Sample Row ID": sample_id,
            "Question": question, "Ground Truth": ground_truth,
            "Difficulty": str(item.get("difficulty", "")), "Category": str(item.get("category", "")),
            "Query Type": str(item.get("query_type", "")), "Source CSV": str(item.get("source_csv", "")),
            "Pipeline Status": outcome["pipeline_status"],
            "New Status": outcome["pipeline_status"],  # no grading; grade later from Branch Results
            "Consensus Achieved": outcome["consensus"],
            "Consensus Size": outcome["consensus_size"],
            "Winning Copies": json.dumps([b.copy_id for b in outcome["winners"]]),
            "Ensemble Result": base.serialize_rows_for_grading(final_rows),
            "Processed Rows": base.serialize_rows_for_grading(final_rows),
            "Final SPARQL": winner.sparql if winner else "",
            "Final Scan Row Count": winner.row_count if winner else "",
            "Branch Results": json.dumps([branch_summary(b) for b in branches], ensure_ascii=False),
            "Target Model": args.target_model,
            "Generation Input Tokens": sum(b.generation_input_tokens for b in branches),
            "Generation Output Tokens": sum(b.generation_output_tokens for b in branches),
            "Started At": started_at,
            "Elapsed Seconds": round(time.perf_counter() - started, 3),
        }

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(worker, item): item for item in pending}
        for future in as_completed(futures):
            row = future.result()
            if row is None:
                continue
            with lock:
                rows.append(row)
                completed_count += 1
                save()
                if completed_count % 10 == 0:
                    api_logger.save()
            print(
                f"[{completed_count}/{len(pending)}] {row['Sample Row ID']}: {row['Pipeline Status']}; "
                f"consensus={row['Consensus Size']}/{args.copies}",
                flush=True,
            )
            fatal = any(
                b["status"] in base.FATAL_API_STATUSES
                for b in json.loads(row["Branch Results"])
            )
            if fatal:
                print("[SYSTEM] Fatal API status seen on a branch; not scheduling further new work.", file=sys.stderr)
                quota_exhausted.set()

    api_logger.save()
    print(f"Report: {args.report}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-model", default=DEFAULT_TARGET_MODEL)
    parser.add_argument("--fuseki-endpoint", default=DEFAULT_FUSEKI_ENDPOINT)
    parser.add_argument("--copies", type=int, default=int(os.getenv("PARALLEL_COPIES", "3")))
    parser.add_argument("--workers", type=int, default=DEFAULT_QUESTION_WORKERS, help="concurrent questions (each uses --copies branches)")
    parser.add_argument("--offset", type=int, default=int(os.getenv("TEST_QUERY_OFFSET", "0")))
    parser.add_argument("--limit", type=int, default=int(os.getenv("TEST_QUERY_LIMIT", "0")), help="0 means all remaining rows")
    parser.add_argument("--temperature", type=float, default=float(os.getenv("GENERATION_TEMPERATURE", "0.3")))
    parser.add_argument("--scan-timeout", type=float, default=float(os.getenv("FUSEKI_SCAN_TIMEOUT_SECONDS", "60")))
    parser.add_argument("--metadata-timeout", type=float, default=float(os.getenv("FUSEKI_METADATA_TIMEOUT_SECONDS", "60")))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args)


if __name__ == "__main__":
    main()
