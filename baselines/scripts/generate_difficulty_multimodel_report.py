#!/usr/bin/env python3
"""Generate difficulty-level grading analysis for every model and baseline."""

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
SEMANTIC = ("MATCH", "MISMATCH", "PARTIAL")
DIFFICULTIES = ("Easy", "Medium", "Hard", "Advanced", "Expert")


@dataclass(frozen=True)
class Model:
    key: str
    label: str
    model_id: str


@dataclass(frozen=True)
class Pipeline:
    key: str
    label: str
    directory: str
    gpt_oss_filename: str
    multimodel_filename: str


MODELS = (
    Model("gpt_oss_120b", "GPT-OSS 120B", "openai.gpt-oss-120b-1:0"),
    Model("kimi_k2_thinking_1t", "Kimi K2 Thinking 1T", "moonshotai.kimi-k2-thinking"),
    Model("gemma_3_27b_it", "Gemma 3 27B IT", "google.gemma-3-27b-it"),
    Model("deepseek_v3_2_685b", "DeepSeek V3.2 685B", "deepseek.v3.2"),
)

PIPELINES = (
    Pipeline(
        "base_sparql", "Base SPARQL", "base_pipeline_qwen",
        "base_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv",
        "base_sparql_{model}_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv",
    ),
    Pipeline(
        "base_sql", "Base SQL", "base_pipeline_sql",
        "base_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv",
        "base_sql_{model}_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv",
    ),
    Pipeline(
        "graph_rag_local", "GraphRAG Local", "graph_rag_baseline",
        "graph_rag_local_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv",
        "graph_rag_local_{model}_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv",
    ),
    Pipeline(
        "parallel_sparql", "Parallel SPARQL", "parallel_pipeline_baseline",
        "parallel_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv",
        "parallel_sparql_{model}_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv",
    ),
    Pipeline(
        "parallel_sql", "Parallel SQL", "parallel_pipeline_sql_baseline",
        "parallel_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv",
        "parallel_sql_{model}_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv",
    ),
    Pipeline(
        "dail_sql", "DAIL-SQL", "dail_sql_baseline",
        "dail_sql_gpt_oss_120b_domain_context_1000q_20261005_graded_gpt_5_mini.csv",
        "dail_sql_{model}_domain_intro_phase0_rules_1000q_graded_gpt_5_mini.csv",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--finance-root",
        type=Path,
        required=True,
        help="Finance directory containing all six baseline directories.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Markdown output path.")
    return parser.parse_args()


def csv_path(finance_root: Path, model: Model, pipeline: Pipeline) -> Path:
    output = finance_root / pipeline.directory / "output"
    if model.key == "gpt_oss_120b":
        return output / pipeline.gpt_oss_filename
    run_date = "20261005" if pipeline.key == "dail_sql" else "20261004"
    return (
        output
        / f"multimodel_domain_context_{run_date}"
        / model.key
        / pipeline.multimodel_filename.format(model=model.key)
    )


def read_rows(path: Path, model: Model, pipeline: Pipeline) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [(row.get("Sample Row ID") or "").strip() for row in rows]
    if len(rows) != 1000 or len(set(ids)) != 1000 or any(not item for item in ids):
        raise ValueError(f"{model.label} / {pipeline.label}: expected 1,000 unique non-empty IDs")
    graders = {(row.get("Direct LLM Grader Model") or "").strip() for row in rows}
    if graders != {GRADER}:
        raise ValueError(f"{model.label} / {pipeline.label}: unexpected grader models {sorted(graders)}")
    targets = {(row.get("Target Model") or "").strip() for row in rows}
    recorded_targets = {target for target in targets if target}
    if recorded_targets and recorded_targets != {model.model_id}:
        raise ValueError(f"{model.label} / {pipeline.label}: unexpected target models {sorted(targets)}")
    difficulties = {(row.get("Difficulty") or "").strip() for row in rows}
    if difficulties != set(DIFFICULTIES):
        raise ValueError(f"{model.label} / {pipeline.label}: unexpected difficulties {sorted(difficulties)}")
    return rows


def status_counts(rows: list[dict[str, str]]) -> Counter[str]:
    return Counter((row.get("New Status") or "").strip().upper() for row in rows)


def values(rows: list[dict[str, str]]) -> tuple[int, int, int, int, int]:
    counts = status_counts(rows)
    other = len(rows) - sum(counts[status] for status in SEMANTIC)
    return len(rows), counts["MATCH"], counts["MISMATCH"], counts["PARTIAL"], other


def result_row(labels: list[str], rows: list[dict[str, str]], bold: bool = False) -> str:
    total, match, mismatch, partial, other = values(rows)
    numbers = [str(total), str(match), str(mismatch), str(partial), str(other)]
    if bold:
        numbers = [f"**{value}**" for value in numbers]
    return "| " + " | ".join(labels + numbers) + " |"


def other_details(rows: list[dict[str, str]]) -> str:
    counts = status_counts(rows)
    details = [(key or "<blank>", count) for key, count in counts.items() if key not in SEMANTIC]
    return "None" if not details else ", ".join(f"`{key}`: {count}" for key, count in sorted(details))


def validate_benchmark(data: dict[tuple[str, str], list[dict[str, str]]]) -> Counter[str]:
    reference_rows = data[(MODELS[0].key, PIPELINES[0].key)]
    reference = {
        (row.get("Sample Row ID") or "").strip(): (row.get("Difficulty") or "").strip()
        for row in reference_rows
    }
    distribution = Counter(reference.values())
    for model in MODELS:
        for pipeline in PIPELINES:
            rows = data[(model.key, pipeline.key)]
            current = {
                (row.get("Sample Row ID") or "").strip(): (row.get("Difficulty") or "").strip()
                for row in rows
            }
            if current != reference:
                raise ValueError(f"{model.label} / {pipeline.label}: benchmark IDs or difficulty labels differ")
    return distribution


def build_report(
    data: dict[tuple[str, str], list[dict[str, str]]],
    distribution: Counter[str],
) -> str:
    lines = [
        "# Difficulty-level grading analysis across all baselines and models", "",
        f"This report covers 24 independent 1,000-question outputs: six pipelines run with four models and graded by `{GRADER}`. "
        "`OTHER / ERROR` contains every status other than `MATCH`, `MISMATCH`, and `PARTIAL`.", "",
        "The source data contains five difficulty levels. `Expert` is included so every pipeline total reconciles to 1,000 questions.", "",
        "## Benchmark difficulty distribution", "",
        "| Difficulty | Questions per pipeline |",
        "|---|---:|",
    ]
    for difficulty in DIFFICULTIES:
        lines.append(f"| {difficulty} | {distribution[difficulty]} |")
    lines.extend([f"| **Overall** | **{sum(distribution.values())}** |", ""])

    for model in MODELS:
        model_rows = [row for pipeline in PIPELINES for row in data[(model.key, pipeline.key)]]
        lines.extend([
            f"## {model.label}", "",
            f"Model ID: `{model.model_id}`", "",
            "### Model total across six pipelines", "",
            "| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        by_difficulty: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in model_rows:
            by_difficulty[(row.get("Difficulty") or "").strip()].append(row)
        for difficulty in DIFFICULTIES:
            lines.append(result_row([difficulty], by_difficulty[difficulty]))
        lines.append(result_row(["**Overall**"], model_rows, bold=True))
        lines.extend(["", "### Pipeline detail", ""])

        for pipeline in PIPELINES:
            rows = data[(model.key, pipeline.key)]
            groups: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in rows:
                groups[(row.get("Difficulty") or "").strip()].append(row)
            lines.extend([
                f"#### {pipeline.label}", "",
                "| Difficulty | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |",
                "|---|---:|---:|---:|---:|---:|",
            ])
            for difficulty in DIFFICULTIES:
                lines.append(result_row([difficulty], groups[difficulty]))
            lines.append(result_row(["**Overall**"], rows, bold=True))
            lines.extend(["", f"Other status details: {other_details(rows)}.", ""])
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    data: dict[tuple[str, str], list[dict[str, str]]] = {}
    for model in MODELS:
        for pipeline in PIPELINES:
            path = csv_path(args.finance_root, model, pipeline)
            data[(model.key, pipeline.key)] = read_rows(path, model, pipeline)
            print(f"validated {model.label} / {pipeline.label}: {path}", file=sys.stderr)
    distribution = validate_benchmark(data)
    report = build_report(data, distribution)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
