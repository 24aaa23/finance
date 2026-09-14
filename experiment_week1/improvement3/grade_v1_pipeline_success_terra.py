"""Grade only successful V1 final answers with the direct GPT-5.6 Terra grader.

The pipeline report remains untouched.  This script creates a separate, resumable CSV
whose rows retain ``Pipeline Execution Status`` and receive a separate Terra grade.
"""

import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA import (
    DEFAULT_LLM_GRADER_MODEL,
    GraderOutputError,
    api_logger,
    build_openai_grader_client,
    classify_grader_exception,
    parse_llm_json,
    truncate_for_prompt,
)


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.getenv("PIPELINE_OUTPUT_DIR", SCRIPT_DIR / "pipelien_output"))
DEFAULT_INPUT_FILES = [
    OUTPUT_DIR / "v1_queries_1_to_100.csv",
    OUTPUT_DIR / "v1_queries_351_to_442.csv",
]
GRADE_INPUT_FILES = [
    Path(item.strip())
    for item in os.getenv("V1_REPORT_FILES", ";".join(str(path) for path in DEFAULT_INPUT_FILES)).split(";")
    if item.strip()
]
GRADE_OUTPUT_FILE = Path(os.getenv(
    "GRADED_REPORT_FILE",
    OUTPUT_DIR / "graded_v1_pipeline_success_terra.csv",
))
LLM_GRADER_MODEL = os.getenv("LLM_GRADER_MODEL", DEFAULT_LLM_GRADER_MODEL)


def _set_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def load_successful_rows(paths: list[Path]) -> list[dict[str, Any]]:
    """Load and deduplicate successful rows without changing their source reports."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in paths:
        if not path.exists():
            print(f"[WARN] V1 report not found; skipping: {path}")
            continue
        report = pd.read_csv(path, dtype=str, keep_default_na=False)
        success = report[report.get("New Status", "").astype(str).str.strip().str.upper() == "PIPELINE_SUCCESS"]
        for item in success.to_dict(orient="records"):
            key = (str(path.resolve()), str(item.get("Sample Row ID", "")))
            if key in seen:
                continue
            seen.add(key)
            item["Report Source"] = str(path.resolve())
            item["Pipeline Execution Status"] = item.get("New Status", "")
            rows.append(item)
        print(f"[SYSTEM] {path.name}: selected {len(success)} PIPELINE_SUCCESS row(s).")
    return rows


def grade_final_output(question: str, ground_truth: str, final_output: str, client: Any, model: str) -> dict[str, Any]:
    """Grade the pipeline's final JSON, never its intermediate Scan rows."""
    prompt = f"""
You are a strict but fair evaluator for a finance knowledge-graph QA benchmark.

Compare the pipeline FINAL ANSWER against the SQL-derived ground truth for the user
question. The final answer may be JSON rows and may use different column names, but it
must contain the correct required entities, values, filters, grouping, aggregation,
derived values, ranking/order, and limits. Numeric strings and numbers are equivalent;
allow an absolute tolerance of 1.5 unless exact precision is explicitly required.

Return MATCH only when the final answer completely answers the question. Return PARTIAL
when it has meaningful correct content but misses or adds required information. Return
MISMATCH when it is materially wrong, incomplete, uses the wrong filter/grouping/
aggregation/ranking, or is empty while a non-empty answer is required. Return OTHER only
when an input is genuinely impossible to interpret.

Return only this JSON:
{{
  "status": "MATCH" | "MISMATCH" | "PARTIAL" | "OTHER",
  "reason": "short explanation",
  "evidence": {{"main_correct_parts": [], "main_missing_or_wrong_parts": []}}
}}

Question:
{truncate_for_prompt(question, 8000)}

Ground Truth JSON:
{truncate_for_prompt(ground_truth)}

Pipeline Final Answer JSON:
{truncate_for_prompt(final_output)}
""".strip()
    api_logger.log_call(question, "Grade_V1_Final_Output")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return only valid JSON; no markdown or prose outside JSON."},
            {"role": "user", "content": prompt},
        ],
    )
    if not response.choices:
        raise GraderOutputError("Terra grader returned no choices.")
    if str(response.choices[0].finish_reason or "").lower() == "length":
        raise GraderOutputError("Terra grader output was truncated: finish_reason=length.")
    content = response.choices[0].message.content
    result = parse_llm_json(content or "")
    status = str(result.get("status", "OTHER")).upper().strip()
    result["status"] = status if status in {"MATCH", "MISMATCH", "PARTIAL", "OTHER"} else "OTHER"
    return result


def _identity(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("Report Source", "")), str(row.get("Sample Row ID", ""))


def save_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    GRADE_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    temporary = GRADE_OUTPUT_FILE.with_suffix(GRADE_OUTPUT_FILE.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, GRADE_OUTPUT_FILE)


def grade_reports(dry_run: bool = False) -> Path:
    _set_csv_field_limit()
    source_rows = load_successful_rows(GRADE_INPUT_FILES)
    if not source_rows:
        raise RuntimeError("No PIPELINE_SUCCESS rows were found in the requested V1 report files.")

    existing: dict[tuple[str, str], dict[str, Any]] = {}
    if GRADE_OUTPUT_FILE.exists():
        existing_report = pd.read_csv(GRADE_OUTPUT_FILE, dtype=str, keep_default_na=False)
        existing = {_identity(row): row for row in existing_report.to_dict(orient="records")}
        print(f"[RESUME] Found {len(existing)} existing graded row(s).")

    if dry_run:
        print(f"[DRY RUN] Would grade {len(source_rows)} successful V1 row(s).")
        return GRADE_OUTPUT_FILE

    client = build_openai_grader_client()
    final_rows: list[dict[str, Any]] = []
    completed = {"MATCH", "MISMATCH", "PARTIAL", "OTHER"}
    for number, source in enumerate(source_rows, 1):
        key = _identity(source)
        old = existing.get(key, {})
        if str(old.get("Terra Grade Status", "")).upper() in completed:
            final_rows.append(old)
            print(f"[GRADE] {number}/{len(source_rows)}: resumed {old['Terra Grade Status']}", flush=True)
            continue
        updated = dict(source)
        try:
            result = grade_final_output(
                str(source.get("Question", "")),
                str(source.get("Ground Truth", "")),
                str(source.get("New Pipeline Result", "")),
                client,
                LLM_GRADER_MODEL,
            )
            updated["Terra Grade Status"] = result["status"]
            updated["Terra Grade Reason"] = result.get("reason", "")
            updated["Terra Grade Evidence"] = json.dumps(result.get("evidence", {}), ensure_ascii=False, default=str)
            updated["Terra Grader Model"] = LLM_GRADER_MODEL
        except Exception as exc:
            updated["Terra Grade Status"] = classify_grader_exception(exc)
            updated["Terra Grade Reason"] = str(exc)
            updated["Terra Grade Evidence"] = "{}"
            updated["Terra Grader Model"] = LLM_GRADER_MODEL
        final_rows.append(updated)
        save_rows(final_rows)
        print(f"[GRADE] {number}/{len(source_rows)}: {updated['Terra Grade Status']}", flush=True)

    api_logger.save()
    return GRADE_OUTPUT_FILE


if __name__ == "__main__":
    print("\n" + "=" * 56)
    print("GRADING SUCCESSFUL V1 FINAL OUTPUTS WITH GPT-5.6 TERRA")
    print("=" * 56)
    output = grade_reports(dry_run="--dry-run" in sys.argv)
    print(f"[SUCCESS] Graded report: {output}")
