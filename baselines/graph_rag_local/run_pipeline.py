"""Single-shot, ungraded, concurrent local-retrieval GraphRAG baseline.

Every question uses bounded neighborhood retrieval from a local SQLite/FTS
index built from the RDF graph, followed by one answer-generation call over
the retrieved facts. Fuseki is not used.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from openai import OpenAI

from env import load_base_pipeline_env
from graph_index import build_index, connect, retrieve, verify_index


HERE = Path(__file__).resolve().parent
BASELINES = HERE.parent
FINANCE = BASELINES.parent
DEFAULT_GRAPH = FINANCE / "script_diff_llm" / "kg" / "wealth_management_diverse_kg.ttl"
DEFAULT_BENCHMARK = BASELINES / "dataset" / "wealth_management_1000_questions.csv"
DEFAULT_INDEX = HERE / "output" / "graph_index.sqlite"
DEFAULT_REPORT = HERE / "output" / "graph_rag_local_only_gpt_oss_120b_1000q.csv"
DEFAULT_MODEL = os.getenv("BEDROCK_GPT_OSS_MODEL", "openai.gpt-oss-120b-1:0")
DEFAULT_WORKERS = int(os.getenv("PIPELINE_WORKERS", "8"))
VERSION = "graph-rag-local-retrieval-single-shot-ungraded-v1"

_csv_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_csv_limit)
        break
    except OverflowError:
        _csv_limit //= 10

REPORT_COLUMNS = [
    "Pipeline Version", "Sample Row ID", "Question", "Ground Truth",
    "Difficulty", "Category", "Query Type", "Source CSV", "New Pipeline Result",
    "Processed Rows", "New Status", "Comparison / Comments", "Started At",
    "Elapsed Seconds", "Model", "Input Tokens", "Output Tokens", "Seed URIs",
    "Retrieved Entity URIs", "Retrieved Entity Count", "Retrieved Triple Count",
    "Matched IDs", "Retrieval Truncated", "Applied Retrieval Limits",
    "Retrieval Context Characters", "Estimated Input Tokens",
    "Evidence URIs", "Answer Route", "Graph Query", "Model Audit",
    "Generation Latency Seconds",
]


def load_benchmark(path: Path) -> pd.DataFrame:
    frame = pd.read_excel(path) if path.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(path)
    required = {"global_question_id", "question", "ground_truth_answer"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Benchmark needs columns: {sorted(required)}")
    return frame


def make_client() -> OpenAI:
    load_base_pipeline_env()
    key = os.getenv("AWS_BEDROCK_API_KEY") or os.getenv("AWS_Bedrock_API_gpt_oss_120b") or os.getenv("BEDROCK_API_KEY")
    if not key:
        raise RuntimeError("Set AWS_BEDROCK_API_KEY for the GPT-OSS Bedrock endpoint.")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        if not region:
            raise RuntimeError("Set BEDROCK_REGION or BEDROCK_BASE_URL.")
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"
    return OpenAI(api_key=key, base_url=base_url, timeout=180, max_retries=1)


def parse_answer(raw: str, retrieved_uris: set[str]) -> dict:
    cleaned = re.sub(r"(?is)<(?:think|reasoning)>.*?</(?:think|reasoning)>", "", raw or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    decoder = json.JSONDecoder()
    candidates = [cleaned] + [cleaned[i:] for i, char in enumerate(cleaned) if char == "{"]
    for candidate in candidates:
        try:
            parsed, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict) or parsed.get("status") not in {"answered", "insufficient_evidence"}:
            continue
        if "answer" not in parsed:
            continue
        citations = parsed.get("evidence_uris", [])
        if not isinstance(citations, list):
            citations = []
        parsed["evidence_uris"] = [uri for uri in citations if uri in retrieved_uris]
        if parsed["status"] == "answered" and not parsed["evidence_uris"]:
            parsed["status"] = "insufficient_evidence"
            parsed["answer"] = None
        if parsed["status"] == "insufficient_evidence":
            parsed["answer"] = None
        return parsed
    raise ValueError("Model did not return the required answer JSON object")


def _answer_prompt(question: str, retrieval: dict) -> str:
    return (
        f"RDF facts:\n{retrieval['context']}\n\n"
        f"Question:\n{question}\n\n"
        "Return exactly one JSON object with keys status, answer, and evidence_uris. "
        "Set status to answered or insufficient_evidence."
    )


def estimate_input_tokens(messages: list[dict[str, str]]) -> int:
    payload = "\n".join(message["role"] + ": " + message["content"] for message in messages)
    return (len(payload.encode("utf-8")) + 2) // 3 + 64


def trim_retrieval_context(retrieval: dict, max_context_chars: int) -> bool:
    evidence = retrieval.get("evidence", [])
    kept: list[dict] = []
    total = 0
    for entry in evidence:
        block = entry.get("text")
        if block is None:
            break
        separator = 1 if kept else 0
        if total + separator + len(block) > max_context_chars:
            break
        kept.append(entry)
        total += separator + len(block)
    if len(kept) == len(evidence):
        return False
    if not kept and evidence:
        kept = [evidence[0]]
    if len(kept) == len(evidence):
        return False
    retrieval["evidence"] = kept
    retrieval["entities"] = [entry["uri"] for entry in kept]
    retrieval["context"] = "\n".join(entry["text"] for entry in kept)
    retrieval["truncated"] = True
    return True


def answer_question_single_shot(
    client: OpenAI,
    model: str,
    question: str,
    retrieval: dict,
    *,
    max_input_tokens: int = 105000,
) -> tuple[dict, int, int, float]:
    """One local-route answer-generation call. No JSON-retry, no context-length retry."""
    if not retrieval["entities"]:
        retrieval["estimated_input_tokens"] = 0
        return {"status": "insufficient_evidence", "answer": None, "evidence_uris": []}, 0, 0, 0.0

    # Pre-flight (non-API) trimming to fit the context budget before the single call.
    while True:
        messages = [
            {"role": "user", "content": _answer_prompt(question, retrieval)},
        ]
        estimate = estimate_input_tokens(messages)
        retrieval["estimated_input_tokens"] = estimate
        if estimate <= max_input_tokens:
            break
        target_chars = max(10000, int(len(retrieval["context"]) * max_input_tokens / estimate * 0.92))
        if not trim_retrieval_context(retrieval, target_chars):
            raise ValueError("Context cannot fit the input budget without removing the last entity")

    t0 = time.perf_counter()
    response = client.chat.completions.create(model=model, temperature=0, messages=messages)
    latency = time.perf_counter() - t0
    raw = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    audit = {
        "attempts": [{"raw_response": raw, "finish_reason": str(getattr(response.choices[0], "finish_reason", ""))}],
        "input_tokens": input_tokens, "output_tokens": output_tokens,
    }
    retrieval["model_audit"] = audit
    try:
        parsed = parse_answer(raw, set(retrieval["entities"]))
    except ValueError as exc:
        audit["attempts"][-1]["error"] = str(exc)
        parsed = {"status": "insufficient_evidence", "answer": None, "evidence_uris": []}
    return parsed, input_tokens, output_tokens, latency


def process_question(
    item: pd.Series,
    *,
    thread_local: threading.local,
    index_path: Path,
    client: OpenAI,
    model: str,
    args: argparse.Namespace,
) -> dict:
    sample_id = str(item["global_question_id"])
    started = dt.datetime.now().isoformat(timespec="seconds")
    start = time.perf_counter()
    question = str(item["question"])

    if not hasattr(thread_local, "conn"):
        thread_local.conn = connect(index_path, readonly=True)
    conn = thread_local.conn

    retrieval = retrieve(
        conn, question, max_seeds=args.max_seeds, max_neighbors=args.max_neighbors,
        max_triples=args.max_triples, max_chars=args.max_chars, max_hops=args.max_hops,
        exact_id_max_neighbors=args.exact_id_max_neighbors,
        exact_id_max_triples=args.exact_id_max_triples,
        exact_id_max_chars=args.exact_id_max_chars,
    )

    audit: dict = {}
    route = "local_entity"
    answer = {"status": "insufficient_evidence", "answer": None, "evidence_uris": []}
    input_tokens = output_tokens = 0
    status = "INSUFFICIENT_EVIDENCE"
    comment = ""
    latency = 0.0
    try:
        answer, input_tokens, output_tokens, latency = answer_question_single_shot(
            client, model, question, retrieval, max_input_tokens=args.max_input_tokens,
        )
        audit = retrieval.get("model_audit", {})
        status = "ANSWERED" if answer["status"] == "answered" else "INSUFFICIENT_EVIDENCE"
    except Exception as exc:
        audit = audit or retrieval.get("model_audit", {})
        input_tokens = audit.get("input_tokens", 0)
        output_tokens = audit.get("output_tokens", 0)
        status = "CRASH"
        comment = f"{type(exc).__name__}: {exc}"[:500]

    rendered = json.dumps(answer["answer"], ensure_ascii=False)
    return {
        "Answer Route": route, "Graph Query": audit.get("query", ""),
        "Model Audit": json.dumps(audit, ensure_ascii=False),
        "Pipeline Version": VERSION, "Sample Row ID": sample_id,
        "Question": question, "Ground Truth": str(item["ground_truth_answer"]),
        "Difficulty": str(item.get("difficulty", "")), "Category": str(item.get("category", "")),
        "Query Type": str(item.get("query_type", "")), "Source CSV": str(item.get("source_csv", "")),
        "New Pipeline Result": rendered, "Processed Rows": rendered,
        "New Status": status, "Comparison / Comments": comment,
        "Started At": started, "Elapsed Seconds": round(time.perf_counter() - start, 3),
        "Model": model, "Input Tokens": input_tokens, "Output Tokens": output_tokens,
        "Seed URIs": json.dumps(retrieval["seeds"]),
        "Retrieved Entity URIs": json.dumps(retrieval["entities"]),
        "Retrieved Entity Count": len(retrieval["entities"]),
        "Retrieved Triple Count": sum(entry["triples"] for entry in retrieval["evidence"]),
        "Matched IDs": json.dumps(retrieval["matched_ids"]),
        "Retrieval Truncated": retrieval["truncated"],
        "Applied Retrieval Limits": json.dumps(retrieval.get("applied_limits", {}), sort_keys=True),
        "Retrieval Context Characters": len(retrieval["context"]),
        "Estimated Input Tokens": retrieval.get("estimated_input_tokens", ""),
        "Evidence URIs": json.dumps(answer["evidence_uris"]),
        "Generation Latency Seconds": round(latency, 3),
    }


def write_report(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def run(args: argparse.Namespace) -> None:
    if not args.index.exists():
        raise FileNotFoundError(f"Index missing: {args.index}. Run build-index first.")
    index_conn = connect(args.index, readonly=True)
    verify_index(index_conn, args.graph)
    benchmark = load_benchmark(args.benchmark)
    selected = benchmark.iloc[args.offset:args.offset + args.limit] if args.limit else benchmark.iloc[args.offset:]

    rows: list[dict] = []
    completed: set[str] = set()
    if args.report.exists():
        with args.report.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        completed = {row["Sample Row ID"] for row in rows if row.get("New Status") in {"ANSWERED", "INSUFFICIENT_EVIDENCE"}}
        print(f"[RESUME] Found {len(completed)} completed rows.")

    client = make_client()

    thread_local = threading.local()
    lock = threading.Lock()
    pending = [item for _, item in selected.iterrows() if str(item["global_question_id"]) not in completed]
    print(f"[SYSTEM] Pending questions this run: {len(pending)} (workers={args.workers})")

    def save():
        write_report(args.report, rows)

    completed_count = 0

    def worker(item):
        return process_question(
            item, thread_local=thread_local, index_path=args.index,
            client=client, model=args.model, args=args,
        )

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(worker, item) for item in pending]
            for future in as_completed(futures):
                row = future.result()
                with lock:
                    rows.append(row)
                    completed_count += 1
                    save()
                print(
                    f"[{completed_count}/{len(pending)}] {row['Sample Row ID']}: {row['New Status']} "
                    f"({row['Answer Route']}); entities={row['Retrieved Entity Count']}",
                    flush=True,
                )
    finally:
        # Worker threads each opened their own read-only index connection;
        # those are reclaimed on process exit (SQLite read-only handles are cheap).
        index_conn.close()

    print(f"Report: {args.report}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-index")
    build.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    build.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    execute = sub.add_parser("run")
    execute.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    execute.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    execute.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    execute.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    execute.add_argument("--model", default=DEFAULT_MODEL)
    execute.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    execute.add_argument("--offset", type=int, default=0)
    execute.add_argument("--limit", type=int, default=0, help="0 means all remaining questions")
    execute.add_argument("--max-seeds", type=int, default=3)
    execute.add_argument("--max-neighbors", type=int, default=5000)
    execute.add_argument("--max-triples", type=int, default=5000)
    execute.add_argument("--max-hops", type=int, default=2)
    execute.add_argument("--max-chars", type=int, default=320000)
    execute.add_argument("--max-input-tokens", type=int, default=105000)
    execute.add_argument("--exact-id-max-neighbors", type=int, default=64)
    execute.add_argument("--exact-id-max-triples", type=int, default=1200)
    execute.add_argument("--exact-id-max-chars", type=int, default=100000)
    args = parser.parse_args()
    if args.command == "build-index":
        print(build_index(args.graph, args.index))
    else:
        run(args)


if __name__ == "__main__":
    main()
