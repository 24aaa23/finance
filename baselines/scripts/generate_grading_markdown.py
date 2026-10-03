#!/usr/bin/env python3
"""Build Markdown grading summaries from the committed 1,000-row CSV reports."""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


csv.field_size_limit(sys.maxsize)

BASELINES_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = BASELINES_ROOT / "results"

PIPELINES = [
    (
        "Base SPARQL",
        "base_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv",
    ),
    (
        "Base SQL",
        "base_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv",
    ),
    (
        "GraphRAG Local",
        "graph_rag_local_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv",
    ),
    (
        "Parallel SPARQL",
        "parallel_sparql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv",
    ),
    (
        "Parallel SQL",
        "parallel_sql_domain_intro_phase0_rules_1000q_20261004_graded_gpt_5_mini.csv",
    ),
]

SEMANTIC_STATUSES = ("MATCH", "MISMATCH", "PARTIAL")

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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1000:
        raise ValueError(f"{path.name}: expected 1,000 rows, found {len(rows)}")
    ids = [row.get("Sample Row ID", "") for row in rows]
    if len(set(ids)) != 1000 or any(not value for value in ids):
        raise ValueError(f"{path.name}: Sample Row ID values are missing or duplicated")
    models = {row.get("Direct LLM Grader Model", "") for row in rows}
    if models != {"gpt-5-mini"}:
        raise ValueError(f"{path.name}: unexpected grader models: {sorted(models)}")
    return rows


def status_counts(rows: list[dict[str, str]]) -> Counter[str]:
    return Counter((row.get("New Status") or "").strip().upper() for row in rows)


def result_row(label: str, rows: list[dict[str, str]]) -> str:
    counts = status_counts(rows)
    semantic_total = sum(counts[status] for status in SEMANTIC_STATUSES)
    other = len(rows) - semantic_total
    return (
        f"| {label} | {len(rows)} | {counts['MATCH']} | {counts['MISMATCH']} | "
        f"{counts['PARTIAL']} | {other} |"
    )


def other_status_text(rows: list[dict[str, str]]) -> str:
    counts = status_counts(rows)
    others = [(status or "<blank>", count) for status, count in counts.items() if status not in SEMANTIC_STATUSES]
    if not others:
        return "None"
    return ", ".join(f"`{status}`: {count}" for status, count in sorted(others))


def load_all() -> dict[str, tuple[str, list[dict[str, str]]]]:
    loaded = {}
    for label, filename in PIPELINES:
        loaded[label] = (filename, read_csv(RESULTS_DIR / filename))
    return loaded


def build_query_type_report(loaded: dict[str, tuple[str, list[dict[str, str]]]]) -> str:
    lines = [
        "# Domain-context baseline grading by query type",
        "",
        "Counts are grouped by the CSV `Query Type` field. Each pipeline is reported independently.",
        "The requested semantic grades are shown explicitly; `OTHER / ERROR` contains all remaining statuses so every table reconciles to 1,000 questions.",
        "",
        "## Overall",
        "",
        "| Pipeline | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, (_, rows) in loaded.items():
        lines.append(result_row(label, rows))

    for label, (filename, rows) in loaded.items():
        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            groups[(row.get("Query Type") or "<blank>").strip()].append(row)
        lines.extend([
            "",
            f"## {label}",
            "",
            f"Source: `{filename}`",
            "",
            "| Query Type | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        for query_type in sorted(groups):
            lines.append(result_row(query_type, groups[query_type]))
        lines.append(result_row("**Overall**", rows).replace("| 1000 |", "| **1000** |")
                     .replace("| **Overall** |", "| **Overall** |"))
        lines.extend(["", f"Other status details: {other_status_text(rows)}."])
    return "\n".join(lines) + "\n"


def build_category_report(loaded: dict[str, tuple[str, list[dict[str, str]]]]) -> str:
    lines = [
        "# Domain-context baseline grading by 125-question category",
        "",
        "Counts are grouped by the eight source datasets in the 1,000-question benchmark.",
        "Every pipeline contains exactly 125 questions from each category.",
        "`OTHER / ERROR` contains non-semantic statuses so every table reconciles exactly.",
        "",
        "## Category codes",
        "",
        "| Code | Category | Source dataset |",
        "|---|---|---|",
    ]
    for code, category, source in CATEGORIES:
        lines.append(f"| {code} | {category} | `{source}` |")

    lines.extend([
        "",
        "## Overall",
        "",
        "| Pipeline | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for label, (_, rows) in loaded.items():
        lines.append(result_row(label, rows))

    for label, (filename, rows) in loaded.items():
        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            groups[Path(row.get("Source CSV") or "").name].append(row)
        unexpected = sorted(set(groups) - {source for _, _, source in CATEGORIES})
        if unexpected:
            raise ValueError(f"{filename}: unexpected Source CSV values: {unexpected}")
        lines.extend([
            "",
            f"## {label}",
            "",
            f"Source: `{filename}`",
            "",
            "| Code | Category | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |",
            "|---|---|---:|---:|---:|---:|---:|",
        ])
        for code, category, source in CATEGORIES:
            category_rows = groups[source]
            if len(category_rows) != 125:
                raise ValueError(f"{filename}: {source} has {len(category_rows)} rows, expected 125")
            rendered = result_row(category, category_rows)
            lines.append(rendered.replace(f"| {category} |", f"| {code} | {category} |", 1))
        rendered_overall = result_row("All categories", rows)
        lines.append(rendered_overall.replace("| All categories |", "| **Overall** | **All categories** |", 1)
                     .replace("| 1000 |", "| **1000** |", 1))
        lines.extend(["", f"Other status details: {other_status_text(rows)}."])
    return "\n".join(lines) + "\n"


def main() -> None:
    loaded = load_all()
    query_path = RESULTS_DIR / "query_type_grading_results_domain_context_gpt_5_mini.md"
    category_path = RESULTS_DIR / "category_grading_results_125_each_domain_context_gpt_5_mini.md"
    query_path.write_text(build_query_type_report(loaded), encoding="utf-8")
    category_path.write_text(build_category_report(loaded), encoding="utf-8")
    print(query_path)
    print(category_path)


if __name__ == "__main__":
    main()
