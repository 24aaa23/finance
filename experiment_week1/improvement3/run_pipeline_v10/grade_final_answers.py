"""V4 final-answer grader; execution status and semantic grade are separate."""

import argparse
import csv
import datetime
import json
import os
import re
import sys
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from typing import Any

import pandas as pd


def load_local_env_file() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_candidates = [
        os.path.join(script_dir, ".env"),
        os.path.join(os.path.dirname(script_dir), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(script_dir)), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))), "env", ".env"),
    ]
    env_file = next((path for path in env_candidates if os.path.exists(path)), None)
    if not env_file:
        return
    with open(env_file, encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


_csv_field_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_csv_field_limit)
        break
    except OverflowError:
        _csv_field_limit //= 10

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.getenv("PIPELINE_OUTPUT_DIR", os.path.join(os.path.dirname(SCRIPT_DIR), "pipelien_output"))
DEFAULT_LLM_GRADER_MODEL = "gpt-5.6-terra"
LLM_GRADER_MODEL = os.getenv("LLM_GRADER_MODEL", DEFAULT_LLM_GRADER_MODEL)
RAW_REPORT_FILE = os.getenv("RAW_REPORT_FILE", os.path.join(OUTPUT_DIR, "raw_pipeline_v4.csv"))
REPORT_FILE = os.getenv("GRADED_REPORT_FILE", os.path.join(OUTPUT_DIR, "graded_pipeline_v4_final_answers.csv"))


class APILogger:
    def __init__(self):
        self.lock = threading.Lock()
        self.query_logs = {}
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(OUTPUT_DIR, f"api_usage_log_direct_llm_grader_{timestamp}.json")

    def log_call(self, query: str, function_name: str) -> None:
        with self.lock:
            q_key = query if query else "Unknown_Query"
            if q_key not in self.query_logs:
                self.query_logs[q_key] = {"total_calls": 0, "functions": {}}
            self.query_logs[q_key]["total_calls"] += 1
            self.query_logs[q_key]["functions"][function_name] = self.query_logs[q_key]["functions"].get(function_name, 0) + 1

    def save(self) -> None:
        with self.lock:
            with open(self.log_file, "w", encoding="utf-8") as handle:
                json.dump(self.query_logs, handle, indent=2)


api_logger = APILogger()


class GraderOutputError(RuntimeError):
    """Raised when the grader response is empty, truncated, or not valid JSON."""


class GraderAuthenticationError(RuntimeError):
    """Grading stopped until the configured credentials are corrected."""


def classify_grader_exception(exc: Exception) -> str:
    """Convert grader/API failures into explicit, non-semantic CSV statuses."""
    error_text = str(exc).lower()
    error_code = str(getattr(exc, "code", "") or "").lower()
    combined = f"{error_code} {error_text}"

    if getattr(exc, "status_code", None) == 401 or any(
        marker in combined for marker in ("invalid_api_key", "incorrect api key", "error code: 401")
    ):
        return "AUTHENTICATION_ERROR"
    if "model_not_found" in combined or "does not exist or you do not have access" in combined:
        return "MODEL_NOT_FOUND"
    if any(marker in combined for marker in ("insufficient_quota", "credit_balance_exhausted", "no credits remaining")):
        return "QUOTA_EXHAUSTED"
    if "rate_limit" in combined or "rate limit" in combined:
        return "RATE_LIMIT_ERROR"
    if isinstance(exc, GraderOutputError) or any(
        marker in combined
        for marker in (
            "context_length_exceeded",
            "maximum context length",
            "max_tokens",
            "max_output_tokens",
            "finish_reason=length",
        )
    ):
        return "TOKEN_OUTPUT_ERROR"
    return "GRADER_API_ERROR"


def build_openai_grader_client():
    from openai import OpenAI as LLMClient

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for GPT-5.6 Terra direct LLM grader calls.")
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        return LLMClient(api_key=api_key, base_url=base_url)
    return LLMClient(api_key=api_key)


def parse_llm_json(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    text = re.sub(r"<(?:thought|reasoning)>.*?</(?:thought|reasoning)>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    text = text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise GraderOutputError("Direct grader returned empty or invalid JSON output.")


def truncate_for_prompt(value: str, max_chars: int = 60000) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head
    return text[:head] + "\n...[TRUNCATED_FOR_PROMPT]...\n" + text[-tail:]


def direct_llm_grade_row(question: str, ground_truth: str, final_answer: str, client, model: str) -> dict[str, Any]:
    prompt = f"""
You are a strict but fair evaluator for a finance knowledge-graph QA benchmark.

You will receive:
1. The user question.
2. The SQL-derived ground truth JSON.
3. The pipeline final answer rows JSON.

Your task:
Decide whether the pipeline final answer rows correctly answer the user question, using the ground truth as the reference.

Important grading rule:
Compare only the information required by the question. If the ground truth contains extra fields that are not needed to answer the question, do not penalize the pipeline for omitting them. Extra harmless columns in the pipeline output are also acceptable if the requested answer is correct.

What to check:
- Required rows/entities: Are the required investors, holdings, goals, transactions, groups, or records present?
- Required values: Are the values required by the question the same as the ground truth values?
- Required columns/metrics: Are all values needed to answer the question present, even if column names differ?
- Filters/conditions: Did the result apply the question's filters correctly?
- Grouping: If the question asks "for each" or "across", are the correct groups present?
- Aggregation: If the question asks count, sum, average, min, max, total, net, etc., are the computed values correct and equal to the ground truth?
- Ranking/order: If the question asks top, bottom, highest, lowest, greatest, least, first, latest, or ordered results, is the ranking/order and limit correct?
- Entity sets: If the question asks for a list/set of entities, compare the entity set. Missing required entities or extra wrong entities should not be MATCH.
- Empty results: If ground truth is empty and the question expects no matching records, an empty final result can be MATCH. If ground truth is non-empty and final result is empty, it is usually MISMATCH.
- Extra rows: Extra incorrect rows should reduce the grade. If the correct answer is present but extra wrong rows are included, use PARTIAL unless the extras do not affect the requested answer.
- Field-name differences: Do not require identical field names when the meaning and values clearly correspond.
- Numeric formatting: Treat numeric strings and numbers as equivalent when values are materially the same.
- Numeric tolerance: If the ground truth contains numeric value X, treat the final answer value as correct when it is between X - 1.5 and X + 1.5, unless the question explicitly requires exact precision.
- Column resolution: Do not require identical column names. Resolve meaning semantically from the question, ground truth fields, and final answer fields. For example, investor id, investor profile, group labels, percentages, averages, totals, and counts may use different aliases if the required meaning is present.

Label definitions:
MATCH:
Use MATCH when the final answer rows completely answer what the question asks. The answer must have the required rows/entities, values, filters, grouping, aggregation, and ranking/order when applicable. All values required by the question must be semantically equal to the ground truth values. Missing unused ground-truth fields or extra harmless columns are okay.

PARTIAL:
Use PARTIAL when the final answer rows answer part of the question correctly, but some required information is missing, incomplete, extra, or wrong. Examples: some correct rows but missing others, correct grouping but one metric wrong/missing, correct entities but wrong aggregation, correct top results but wrong order, correct values for some but not all groups, or correct answer plus extra wrong rows.

MISMATCH:
Use MISMATCH when the final answer rows do not answer the question, are mostly wrong, use wrong filters/entities, use wrong aggregation/ranking, return empty when the ground truth has required results, have required values that conflict with the ground truth, or are unrelated to the ground truth.

OTHER:
Use OTHER only when the input is impossible to judge, malformed beyond interpretation, or the ground truth itself is unusable. Do not use OTHER just because the answer is wrong; use MISMATCH for wrong answers.

Return only JSON with this schema:
{{
  "status": "MATCH" | "MISMATCH" | "PARTIAL" | "OTHER",
  "reason": "short explanation",
  "evidence": {{
    "main_correct_parts": [],
    "main_missing_or_wrong_parts": []
  }}
}}

Question:
{truncate_for_prompt(question, 8000)}

Ground Truth JSON:
{truncate_for_prompt(ground_truth)}

Pipeline Final Answer:
{truncate_for_prompt(final_answer)}
""".strip()

    api_logger.log_call(question, "Direct_LLM_Grade")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict senior finance benchmark grader with 15 years of experience evaluating "
                    "wealth-management database answers. Return only valid JSON; no markdown or prose outside JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    if not response.choices:
        raise GraderOutputError("Direct grader returned no choices.")
    finish_reason = str(response.choices[0].finish_reason or "").lower()
    if finish_reason == "length":
        raise GraderOutputError("Direct grader output was truncated: finish_reason=length.")
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise GraderOutputError("Direct grader returned empty output.")
    parsed = parse_llm_json(content)
    status = str(parsed.get("status", "OTHER")).strip().upper()
    if status not in {"MATCH", "MISMATCH", "PARTIAL", "OTHER"}:
        status = "OTHER"
    parsed["status"] = status
    return parsed


REQUIRED_REPORT_COLUMNS = {"Question", "Ground Truth", "New Pipeline Result", "New Status"}
COMPLETED_GRADES = {"MATCH", "PARTIAL", "MISMATCH", "OTHER"}


def execution_status(row: dict[str, Any]) -> str:
    return str(row.get("Execution Status") or row.get("Pipeline Status") or row.get("New Status", "")).strip().upper()


def final_answer_for_grading(row: dict[str, Any]) -> str:
    """V4 must grade the actual final answer; a successful empty answer is valid input."""
    if "New Pipeline Result" not in row:
        raise ValueError("V4 grading requires New Pipeline Result; raw scan rows are not the final answer.")
    value = row["New Pipeline Result"]
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError("PIPELINE_SUCCESS row has an empty New Pipeline Result cell; use [] for an executed empty answer.")
    try:
        rows = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("New Pipeline Result must contain the structured JSON final answer.") from exc
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("New Pipeline Result must be a JSON list of answer rows.")
    return text


def _resume_key(row: dict[str, Any], model: str) -> tuple[str, ...]:
    # Compare the complete graded input. A changed answer, question, truth, status,
    # or model must be graded again, even when the row ID or file position is unchanged.
    return tuple(str(row.get(field, "")) for field in (
        "Sample Row ID", "Question", "Ground Truth", "New Pipeline Result"
    )) + (execution_status(row), model)


def regrade_existing_report(input_csv: str, output_csv: str, client, model: str = LLM_GRADER_MODEL) -> str:
    df = pd.read_csv(input_csv, dtype=str, keep_default_na=False)
    missing = sorted(REQUIRED_REPORT_COLUMNS - set(df.columns))
    if missing:
        raise ValueError("V4 final-answer report is missing required columns: " + ", ".join(missing))
    rows = []
    existing_by_input = {}
    if os.path.exists(output_csv):
        try:
            for existing in pd.read_csv(output_csv, dtype=str, keep_default_na=False).to_dict(orient="records"):
                if existing.get("Grade Status") in COMPLETED_GRADES:
                    existing_by_input[_resume_key(existing, existing.get("Direct LLM Grader Model", ""))] = existing
        except Exception as exc:
            print(f"[WARN] Could not read existing graded report for resume: {exc}")

    output_parent = os.path.dirname(os.path.abspath(output_csv))
    os.makedirs(output_parent, exist_ok=True)

    def save_progress() -> None:
        if not rows:
            return
        temp_file = f"{output_csv}.tmp"
        with open(temp_file, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_file, output_csv)

    authentication_failed = False
    for idx, row in df.iterrows():
        updated = row.to_dict()
        status = execution_status(updated)
        updated.update({
            "Execution Status": status,
            "Grade Status": "",
            "Grade Reason": "",
            "Direct LLM Evidence": "{}",
            "Direct LLM Grading Path": "",
            "Direct LLM Grader Model": model,
        })
        if status != "PIPELINE_SUCCESS":
            updated["Grade Status"] = "SKIPPED_EXECUTION_FAILURE"
            updated["Grade Reason"] = f"Execution status is {status or 'missing'}; no final answer was graded."
            updated["Direct LLM Grading Path"] = "preserved_execution_status"
        else:
            previous = existing_by_input.get(_resume_key(updated, model))
            if previous:
                # Preserve current report metadata while reusing only its unchanged grade.
                for field in ("Grade Status", "Grade Reason", "Direct LLM Evidence", "Direct LLM Grading Path"):
                    updated[field] = previous.get(field, "")
            elif authentication_failed:
                updated["Grade Status"] = "PENDING_GRADING"
                updated["Grade Reason"] = "Not attempted: fix grader credentials and rerun to resume."
                updated["Direct LLM Grading Path"] = "authentication_failure_stop"
            else:
                try:
                    answer = final_answer_for_grading(updated)
                except ValueError as exc:
                    updated["Grade Status"] = "INVALID_PIPELINE_OUTPUT"
                    updated["Grade Reason"] = str(exc)
                    updated["Direct LLM Grading Path"] = "invalid_pipeline_output"
                else:
                    try:
                        result = direct_llm_grade_row(
                            question=updated["Question"],
                            ground_truth=updated["Ground Truth"],
                            final_answer=answer,
                            client=client,
                            model=model,
                        )
                        updated["Grade Status"] = result.get("status", "OTHER")
                        updated["Grade Reason"] = result.get("reason", "")
                        updated["Direct LLM Evidence"] = json.dumps(result.get("evidence", {}), ensure_ascii=False, default=str)
                        updated["Direct LLM Grading Path"] = "direct_llm_semantic_judgment"
                    except Exception as exc:
                        error_status = classify_grader_exception(exc)
                        updated["Grade Status"] = error_status
                        updated["Grade Reason"] = f"Direct LLM grader {error_status}: {exc}"
                        updated["Direct LLM Grading Path"] = "direct_llm_grader_exception"
                        if error_status == "AUTHENTICATION_ERROR":
                            authentication_failed = True
                            updated["Grade Reason"] = (
                                "Grader authentication failed (HTTP 401). Check OPENAI_API_KEY and "
                                "OPENAI_BASE_URL in this terminal and the loaded .env file, then rerun. "
                                "Existing terminal variables take precedence over .env values."
                            )
                            print(f"[ERROR] {updated['Grade Reason']}", flush=True)
        rows.append(updated)
        save_progress()
        print(f"[GRADE] {idx + 1}/{len(df)}: {updated['Grade Status']}", flush=True)
    if authentication_failed:
        raise GraderAuthenticationError(
            f"Grading stopped after an authentication failure. Progress saved to {output_csv}; "
            "correct credentials and rerun the same command to resume."
        )
    return output_csv


V4_BATCH_INPUTS = (
    "v4_latest_success_55.csv",
    "v4_latest_non_success_part1_69.csv",
    "v4_latest_non_success_part2_68.csv",
)


def report_jobs(all_v4: bool, output_dir: str, model: str) -> list[tuple[str, str]]:
    if not all_v4:
        return [(RAW_REPORT_FILE, REPORT_FILE)]
    suffix = "terra" if model == DEFAULT_LLM_GRADER_MODEL else re.sub(r"[^A-Za-z0-9_.-]+", "_", model)
    return [
        (str(Path(output_dir) / name), str(Path(output_dir) / f"graded_{Path(name).stem}_{suffix}.csv"))
        for name in V4_BATCH_INPUTS
    ]


def main(argv=None):
    global OUTPUT_DIR, RAW_REPORT_FILE, REPORT_FILE, LLM_GRADER_MODEL, api_logger
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-v4", action="store_true", help="Grade all three latest V4 reports, ignoring single-file environment settings.")
    parser.add_argument("--output-dir", help="Folder containing the raw and graded CSVs.")
    parser.add_argument("--model", help="Override LLM_GRADER_MODEL.")
    parser.add_argument("--dry-run", action="store_true", help="Validate input files and show destinations without API calls or writes.")
    args = parser.parse_args(argv)
    load_local_env_file()
    OUTPUT_DIR = args.output_dir or os.getenv("PIPELINE_OUTPUT_DIR", os.path.join(os.path.dirname(SCRIPT_DIR), "pipelien_output"))
    RAW_REPORT_FILE = os.getenv("RAW_REPORT_FILE", os.path.join(OUTPUT_DIR, "raw_pipeline_v4.csv"))
    REPORT_FILE = os.getenv("GRADED_REPORT_FILE", os.path.join(OUTPUT_DIR, "graded_pipeline_v4_final_answers.csv"))
    LLM_GRADER_MODEL = args.model or os.getenv("LLM_GRADER_MODEL", DEFAULT_LLM_GRADER_MODEL)
    api_logger = APILogger()
    print("\n" + "=" * 50)
    print(f"INITIALIZING DIRECT {LLM_GRADER_MODEL} LLM GRADER")
    print("=" * 50)
    jobs = report_jobs(args.all_v4, OUTPUT_DIR, LLM_GRADER_MODEL)
    for input_csv, output_csv in jobs:
        if not os.path.isfile(input_csv):
            raise FileNotFoundError(f"Raw pipeline report not found: {input_csv}")
        missing = sorted(REQUIRED_REPORT_COLUMNS - set(pd.read_csv(input_csv, nrows=0).columns))
        if missing:
            raise ValueError(f"{input_csv} is missing required columns: {', '.join(missing)}")
        print(f"[SYSTEM] Raw report: {input_csv}")
        print(f"[SYSTEM] Direct LLM graded report: {output_csv}")
    print(f"[SYSTEM] Direct LLM grader model: {LLM_GRADER_MODEL}")
    if args.dry_run:
        print(f"[DRY RUN] Validated {len(jobs)} report(s). No API calls or files written.")
        return
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    grader_client = build_openai_grader_client()
    try:
        for input_csv, output_csv in jobs:
            print(f"[REPORT] {Path(input_csv).name}", flush=True)
            regrade_existing_report(input_csv, output_csv, grader_client, LLM_GRADER_MODEL)
            print(f"[SUCCESS] Direct LLM graded report saved to {output_csv}")
    except GraderAuthenticationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("\n[STOPPED] Completed rows are saved. Rerun the same command to resume.", flush=True)
        raise SystemExit(130) from None
    finally:
        api_logger.save()


if __name__ == "__main__":
    main()
