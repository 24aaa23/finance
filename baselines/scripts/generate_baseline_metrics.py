#!/usr/bin/env python3
"""Build aggregate accuracy, latency, cost, and efficiency metrics."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


csv.field_size_limit(sys.maxsize)

BASELINES_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = BASELINES_ROOT / "results"
OUTPUT_PATH = RESULTS_DIR / "baseline_metrics_gpt_5_mini.md"

# Amazon Bedrock Standard on-demand pricing for gpt-oss-120b in us-east-1.
INPUT_PRICE_PER_MILLION = 0.15
OUTPUT_PRICE_PER_MILLION = 0.60

PIPELINES = [
    ("Base SPARQL", "base_sparql_dynamic_namespace_1000q_20261002_graded_gpt_5_mini.csv"),
    ("Base SQL", "base_pipeline_sql_schema_only_prompt_1000q_20261001_graded_gpt_5_mini.csv"),
    ("GraphRAG Local", "graph_rag_local_domain_neutral_prompt_1000q_20261001_graded_gpt_5_mini.csv"),
    ("Parallel SPARQL", "parallel_sparql_schema_only_prompt_parser_lock_1000q_20261002_graded_gpt_5_mini.csv"),
    ("Parallel SQL", "parallel_sql_schema_only_prompt_1000q_20261001_graded_gpt_5_mini.csv"),
]


def number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1000:
        raise ValueError(f"{path.name}: expected 1,000 rows, found {len(rows)}")
    ids = [row.get("Sample Row ID", "") for row in rows]
    if len(set(ids)) != 1000 or any(not value for value in ids):
        raise ValueError(f"{path.name}: Sample Row ID values are missing or duplicated")
    grader_models = {row.get("Direct LLM Grader Model", "") for row in rows}
    if grader_models != {"gpt-5-mini"}:
        raise ValueError(f"{path.name}: unexpected grader models: {sorted(grader_models)}")
    return rows


def parallel_generation_seconds(rows: list[dict[str, str]]) -> tuple[float, int, int]:
    seconds = 0.0
    branch_input_tokens = 0
    branch_output_tokens = 0
    for row in rows:
        branches = json.loads(row.get("Branch Results") or "[]")
        for branch in branches:
            seconds += number(branch.get("generation_latency_seconds"))
            branch_input_tokens += int(number(branch.get("generation_input_tokens")))
            branch_output_tokens += int(number(branch.get("generation_output_tokens")))
    return seconds, branch_input_tokens, branch_output_tokens


def calculate(label: str, filename: str) -> dict[str, object]:
    rows = load_rows(RESULTS_DIR / filename)
    correct = sum((row.get("New Status") or "").strip().upper() == "MATCH" for row in rows)
    input_column = "Input Tokens" if label == "GraphRAG Local" else "Generation Input Tokens"
    output_column = "Output Tokens" if label == "GraphRAG Local" else "Generation Output Tokens"
    input_tokens = sum(int(number(row.get(input_column))) for row in rows)
    output_tokens = sum(int(number(row.get(output_column))) for row in rows)

    if label.startswith("Parallel"):
        generation_seconds, branch_input_tokens, branch_output_tokens = parallel_generation_seconds(rows)
        if (input_tokens, output_tokens) != (branch_input_tokens, branch_output_tokens):
            raise ValueError(f"{filename}: aggregate token columns do not match branch totals")
    else:
        generation_seconds = sum(number(row.get("Generation Latency Seconds")) for row in rows)

    execution_seconds = sum(number(row.get("Elapsed Seconds")) for row in rows)
    total_cost = (
        input_tokens * INPUT_PRICE_PER_MILLION / 1_000_000
        + output_tokens * OUTPUT_PRICE_PER_MILLION / 1_000_000
    )
    return {
        "label": label,
        "filename": filename,
        "questions": len(rows),
        "correct": correct,
        "accuracy": correct / len(rows) * 100,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "generation_seconds": generation_seconds,
        "token_latency_seconds": generation_seconds / output_tokens,
        "token_latency_ms": generation_seconds * 1000 / output_tokens,
        "total_cost": total_cost,
        "average_cost": total_cost / len(rows),
        "execution_seconds": execution_seconds,
        "execution_efficiency": correct / execution_seconds,
    }


def build_report(metrics: list[dict[str, object]]) -> str:
    lines = [
        "# GPT-5 Mini graded baseline metrics",
        "",
        "All five reports contain 1,000 questions graded by `gpt-5-mini`. A correct answer is a row whose `New Status` is `MATCH`; `PARTIAL`, `MISMATCH`, and error statuses are not counted as correct.",
        "",
        "## Accuracy",
        "",
        "`Accuracy = MATCH answers / total questions × 100`",
        "",
        "| Pipeline | Questions | Correct (MATCH) | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for item in metrics:
        lines.append(
            f"| {item['label']} | {item['questions']:,} | {item['correct']:,} | {item['accuracy']:.2f}% |"
        )

    lines.extend([
        "",
        "## Token latency",
        "",
        "`Token latency = total generation time / total output tokens`",
        "",
        "For parallel ensembles, generation time is the sum of the three branch-call generation latencies, matching the summed branch token counts. Branch calls run concurrently, so this is model-call time per generated token rather than end-to-end wall-clock latency.",
        "",
        "| Pipeline | Input tokens | Output tokens | Generation time (s) | Seconds/output token | Milliseconds/output token |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for item in metrics:
        lines.append(
            f"| {item['label']} | {item['input_tokens']:,} | {item['output_tokens']:,} | "
            f"{item['generation_seconds']:,.3f} | {item['token_latency_seconds']:.6f} | "
            f"{item['token_latency_ms']:.3f} |"
        )

    lines.extend([
        "",
        "## Inference cost",
        "",
        "`Total cost = Σ[(input tokens × input price / 1,000,000) + (output tokens × output price / 1,000,000)]`",
        "",
        "`Average cost per question = total cost / 1,000`",
        "",
        "Pricing assumption: Amazon Bedrock Standard on-demand `openai.gpt-oss-120b-1:0` in `us-east-1`, at $0.15 per million input tokens and $0.60 per million output tokens. Source: [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/). Costs cover baseline generation only. GPT-5 Mini grader usage is not present in the result CSVs and is therefore excluded.",
        "",
        "| Pipeline | Input cost (USD) | Output cost (USD) | Total inference cost (USD) | Average cost/question (USD) |",
        "|---|---:|---:|---:|---:|",
    ])
    for item in metrics:
        input_cost = item["input_tokens"] * INPUT_PRICE_PER_MILLION / 1_000_000
        output_cost = item["output_tokens"] * OUTPUT_PRICE_PER_MILLION / 1_000_000
        lines.append(
            f"| {item['label']} | ${input_cost:.6f} | ${output_cost:.6f} | "
            f"${item['total_cost']:.6f} | ${item['average_cost']:.9f} |"
        )

    lines.extend([
        "",
        "## Execution efficiency",
        "",
        "`Execution efficiency = correct answers / total execution time in seconds`",
        "",
        "Total execution time is the sum of the per-question `Elapsed Seconds` field. It measures aggregate question-processing time, not the shorter wall-clock duration obtained by running multiple questions concurrently.",
        "",
        "| Pipeline | Correct (MATCH) | Total execution time (s) | Execution efficiency (correct answers/s) |",
        "|---|---:|---:|---:|",
    ])
    for item in metrics:
        lines.append(
            f"| {item['label']} | {item['correct']:,} | {item['execution_seconds']:,.3f} | "
            f"{item['execution_efficiency']:.6f} |"
        )

    lines.extend(["", "## Source files", ""])
    for item in metrics:
        lines.append(f"- **{item['label']}:** `{item['filename']}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    metrics = [calculate(label, filename) for label, filename in PIPELINES]
    OUTPUT_PATH.write_text(build_report(metrics), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
