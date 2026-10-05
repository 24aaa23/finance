#!/usr/bin/env python3
"""Generate four-model DAIL-SQL grading and metrics Markdown reports."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


FIELD_LIMIT = sys.maxsize
while True:
    try:
        csv.field_size_limit(FIELD_LIMIT)
        break
    except OverflowError:
        FIELD_LIMIT //= 10

GRADER = "gpt-5-mini"
PIPELINE = "DAIL-SQL"
SEMANTIC = ("MATCH", "MISMATCH", "PARTIAL")

CATEGORIES = [
    ("BM", "Benchmark", "wealth_management_125_question_benchmark.csv"),
    ("ARC", "At-Risk Critical", "wealth_management_at_risk_critical_125_questions.csv"),
    ("BS", "Batch Status", "wealth_management_batch_status_125_questions.csv"),
    ("EC", "Enrichment Context", "wealth_management_enrichment_context_125_questions.csv"),
    ("MC", "Multi-Step Comparative", "wealth_management_multi_step_comparative_125_questions.csv"),
    ("RC", "Reference Compliance", "wealth_management_reference_compliance_125_questions.csv"),
    ("SQ", "Scoring Quantitative", "wealth_management_scoring_quantitative_125_questions.csv"),
    ("TT", "Temporal Transaction", "wealth_management_temporal_transaction_125_questions.csv"),
]


@dataclass(frozen=True)
class Model:
    key: str
    label: str
    model_id: str
    input_price: float
    output_price: float
    path: Path


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent
    results = here.parents[1] / "results"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gpt-oss",
        type=Path,
        default=results / "dail_sql_gpt_oss_120b_domain_context_1000q_20261005_graded_gpt_5_mini.csv",
    )
    parser.add_argument("--kimi", type=Path, required=True)
    parser.add_argument("--gemma", type=Path, required=True)
    parser.add_argument("--deepseek", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=results)
    return parser.parse_args()


def read_rows(model: Model) -> list[dict[str, str]]:
    with model.path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [row.get("Sample Row ID", "").strip() for row in rows]
    if len(rows) != 1000 or len(set(ids)) != 1000 or any(not item for item in ids):
        raise ValueError(f"{model.label}: expected exactly 1,000 unique non-empty Sample Row IDs")
    graders = {(row.get("Direct LLM Grader Model") or "").strip() for row in rows}
    if graders != {GRADER}:
        raise ValueError(f"{model.label}: unexpected grader models: {sorted(graders)}")
    target_models = {(row.get("Target Model") or "").strip() for row in rows}
    if target_models != {model.model_id}:
        raise ValueError(f"{model.label}: unexpected target models: {sorted(target_models)}")
    return rows


def statuses(rows: list[dict[str, str]]) -> Counter[str]:
    return Counter((row.get("New Status") or "").strip().upper() for row in rows)


def counts(rows: list[dict[str, str]]) -> tuple[int, int, int, int, int]:
    values = statuses(rows)
    other = len(rows) - sum(values[status] for status in SEMANTIC)
    return len(rows), values["MATCH"], values["MISMATCH"], values["PARTIAL"], other


def result_row(labels: list[str], rows: list[dict[str, str]], bold_total: bool = False) -> str:
    total, match, mismatch, partial, other = counts(rows)
    total_text = f"**{total}**" if bold_total else str(total)
    return "| " + " | ".join(labels + [total_text, str(match), str(mismatch), str(partial), str(other)]) + " |"


def other_text(rows: list[dict[str, str]]) -> str:
    values = statuses(rows)
    details = [(key or "<blank>", value) for key, value in values.items() if key not in SEMANTIC]
    return "None" if not details else ", ".join(f"`{key}`: {value}" for key, value in sorted(details))


def group_by(rows: list[dict[str, str]], field: str, basename: bool = False) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (row.get(field) or "<blank>").strip()
        if basename:
            key = Path(key).name
        groups[key].append(row)
    return groups


def validate(models: list[Model], data: dict[str, list[dict[str, str]]]) -> None:
    reference_ids = {row["Sample Row ID"].strip() for row in data[models[0].key]}
    reference_queries = Counter((row.get("Query Type") or "<blank>").strip() for row in data[models[0].key])
    expected_sources = {source for _, _, source in CATEGORIES}
    for model in models:
        rows = data[model.key]
        ids = {row["Sample Row ID"].strip() for row in rows}
        if ids != reference_ids:
            raise ValueError(f"{model.label}: Sample Row ID set differs from GPT-OSS")
        query_counts = Counter((row.get("Query Type") or "<blank>").strip() for row in rows)
        if query_counts != reference_queries:
            raise ValueError(f"{model.label}: query-type distribution differs from GPT-OSS")
        categories = group_by(rows, "Source CSV", basename=True)
        if set(categories) != expected_sources:
            raise ValueError(f"{model.label}: unexpected category sources: {sorted(categories)}")
        for source in expected_sources:
            if len(categories[source]) != 125:
                raise ValueError(f"{model.label}: {source} has {len(categories[source])} rows instead of 125")


def query_report(models: list[Model], data: dict[str, list[dict[str, str]]]) -> str:
    lines = [
        "# DAIL-SQL grading results by query type — four pipeline-runner models", "",
        f"This report combines four independent 1,000-question DAIL-SQL runs graded by `{GRADER}`. "
        "`OTHER / ERROR` contains every status other than `MATCH`, `MISMATCH`, and `PARTIAL`.", "",
        "## Overall comparison", "",
        "| Pipeline-runner model | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in models:
        lines.append(result_row([model.label], data[model.key]))

    for model in models:
        rows = data[model.key]
        groups = group_by(rows, "Query Type")
        lines.extend([
            "", f"## {model.label}", "",
            f"Model ID: `{model.model_id}`", "",
            f"Source: `{model.path.name}`", "",
            "| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        for query_type in sorted(groups):
            lines.append(result_row([query_type], groups[query_type]))
        lines.append(result_row(["**Overall**"], rows, bold_total=True))
        lines.extend(["", f"Other status details: {other_text(rows)}."])
    lines.append("")
    return "\n".join(lines)


def category_report(models: list[Model], data: dict[str, list[dict[str, str]]]) -> str:
    lines = [
        "# DAIL-SQL grading results by 125-question category — four pipeline-runner models", "",
        f"Each run contains exactly 125 questions from each of eight benchmark categories and was graded by `{GRADER}`. "
        "`OTHER / ERROR` contains every status other than `MATCH`, `MISMATCH`, and `PARTIAL`.", "",
        "## Category key", "",
        "| Code | Category | Source dataset |", "|---|---|---|",
    ]
    for code, name, source in CATEGORIES:
        lines.append(f"| {code} | {name} | `{source}` |")

    lines.extend([
        "", "## Overall comparison", "",
        "| Pipeline-runner model | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for model in models:
        lines.append(result_row([model.label], data[model.key]))

    for model in models:
        rows = data[model.key]
        groups = group_by(rows, "Source CSV", basename=True)
        lines.extend([
            "", f"## {model.label}", "",
            f"Model ID: `{model.model_id}`", "",
            f"Source: `{model.path.name}`", "",
            "| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |",
            "|---|---|---:|---:|---:|---:|---:|",
        ])
        for code, name, source in CATEGORIES:
            lines.append(result_row([code, name], groups[source]))
        lines.append(result_row(["**Overall**", "**All categories**"], rows, bold_total=True))
        lines.extend(["", f"Other status details: {other_text(rows)}."])
    lines.append("")
    return "\n".join(lines)


def number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def metrics(model: Model, rows: list[dict[str, str]]) -> dict[str, float]:
    total, match, _, _, _ = counts(rows)
    input_tokens = sum(int(number(row.get("Generation Input Tokens"))) for row in rows)
    output_tokens = sum(int(number(row.get("Generation Output Tokens"))) for row in rows)
    generation_seconds = sum(number(row.get("Generation Latency Seconds")) for row in rows)
    execution_seconds = sum(number(row.get("Elapsed Seconds")) for row in rows)
    input_cost = input_tokens * model.input_price / 1_000_000
    output_cost = output_tokens * model.output_price / 1_000_000
    total_cost = input_cost + output_cost
    return {
        "total": total,
        "match": match,
        "accuracy": match / total * 100,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "generation_seconds": generation_seconds,
        "token_seconds": generation_seconds / output_tokens,
        "token_ms": generation_seconds * 1000 / output_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "average_cost": total_cost / total,
        "execution_seconds": execution_seconds,
        "efficiency": match / execution_seconds,
    }


def metrics_report(models: list[Model], data: dict[str, list[dict[str, str]]]) -> str:
    values = {model.key: metrics(model, data[model.key]) for model in models}
    lines = [
        "# DAIL-SQL four-model metrics (GPT-5 Mini grader)", "",
        f"This report compares four 1,000-question DAIL-SQL runs graded by `{GRADER}`. "
        "A correct answer is a row whose final `New Status` is `MATCH`.", "",
        "DAIL-SQL makes two model calls per question. Generation tokens and generation time include both the "
        "preliminary-SQL call and the final-SQL call.", "",
        "## Accuracy", "", "`Accuracy = MATCH answers / total questions × 100`", "",
        "| Pipeline-runner model | Questions | Correct (MATCH) | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for model in models:
        value = values[model.key]
        lines.append(f"| {model.label} | {int(value['total']):,} | {int(value['match']):,} | {value['accuracy']:.2f}% |")

    lines.extend([
        "", "## Token latency", "", "`Token latency = total generation time / total output tokens`", "",
        "| Pipeline-runner model | Input tokens | Output tokens | Generation time (s) | Seconds/output token | Milliseconds/output token |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for model in models:
        value = values[model.key]
        lines.append(
            f"| {model.label} | {int(value['input_tokens']):,} | {int(value['output_tokens']):,} | "
            f"{value['generation_seconds']:,.3f} | {value['token_seconds']:.6f} | {value['token_ms']:.3f} |"
        )

    lines.extend([
        "", "## Inference cost", "",
        "`Total cost = Σ[(input tokens × input price / 1,000,000) + (output tokens × output price / 1,000,000)]`", "",
        "`Average cost per question = total cost / total questions`", "",
        "Pricing assumptions use the same Amazon Bedrock Standard on-demand rates as the existing multi-model reports. "
        "GPT-5 Mini grader cost is excluded.", "",
        "| Pipeline-runner model | Input price / 1M | Output price / 1M | Input cost (USD) | Output cost (USD) | Total inference cost (USD) | Average cost/question (USD) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for model in models:
        value = values[model.key]
        lines.append(
            f"| {model.label} | ${model.input_price:.2f} | ${model.output_price:.2f} | "
            f"${value['input_cost']:.6f} | ${value['output_cost']:.6f} | ${value['total_cost']:.6f} | "
            f"${value['average_cost']:.9f} |"
        )

    lines.extend([
        "", "## Execution efficiency", "",
        "`Execution efficiency = correct answers / total execution time in seconds`", "",
        "Total execution time is the sum of per-question `Elapsed Seconds`, not concurrent wall-clock duration.", "",
        "| Pipeline-runner model | Correct (MATCH) | Total execution time (s) | Execution efficiency (correct answers/s) |",
        "|---|---:|---:|---:|",
    ])
    for model in models:
        value = values[model.key]
        lines.append(
            f"| {model.label} | {int(value['match']):,} | {value['execution_seconds']:,.3f} | "
            f"{value['efficiency']:.6f} |"
        )

    lines.extend(["", "## Model and source files", ""])
    for model in models:
        lines.append(f"- {model.label} (`{model.model_id}`): `{model.path.name}`")
    lines.extend(["", "Pricing source: [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).", ""])
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    models = [
        Model("gpt_oss", "GPT-OSS 120B", "openai.gpt-oss-120b-1:0", 0.15, 0.60, args.gpt_oss),
        Model("kimi", "Kimi K2 Thinking 1T", "moonshotai.kimi-k2-thinking", 0.60, 2.50, args.kimi),
        Model("gemma", "Gemma 3 27B IT", "google.gemma-3-27b-it", 0.23, 0.38, args.gemma),
        Model("deepseek", "DeepSeek V3.2 685B", "deepseek.v3.2", 0.62, 1.85, args.deepseek),
    ]
    data = {model.key: read_rows(model) for model in models}
    validate(models, data)
    reports = {
        "dail_sql_query_type_grading_results_multimodel_gpt_5_mini.md": query_report(models, data),
        "dail_sql_category_grading_results_125_each_multimodel_gpt_5_mini.md": category_report(models, data),
        "dail_sql_multimodel_metrics_gpt_5_mini.md": metrics_report(models, data),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in reports.items():
        path = args.output_dir / filename
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
