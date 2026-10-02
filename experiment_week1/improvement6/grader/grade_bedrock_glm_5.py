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

# Configure before pandas/NumPy imports, including eight independent graders.
for _thread_setting in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                        "NUMEXPR_NUM_THREADS", "NUMEXPR_MAX_THREADS", "BLIS_NUM_THREADS"):
    os.environ[_thread_setting] = "1"

import pandas as pd
from openai import OpenAI as LLMClient


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
            os.environ[key.strip()] = value


load_local_env_file()
_csv_field_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_csv_field_limit)
        break
    except OverflowError:
        _csv_field_limit //= 10

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_ROOT = os.path.join(SCRIPT_DIR, "pipelien_output_sql_gpt_oss_grader")
OUTPUT_ROOT = os.path.join(SCRIPT_DIR, "pipelien_output_sql_glm_5")
OUTPUT_DIR = OUTPUT_ROOT
DEFAULT_LLM_GRADER_MODEL = "zai.glm-5"
LLM_GRADER_MODEL = os.getenv("LLM_GRADER_MODEL", DEFAULT_LLM_GRADER_MODEL)
GRADER_MODEL_TAG = re.sub(r"[^A-Za-z0-9_.-]+", "_", LLM_GRADER_MODEL)
RAW_REPORT_FILE = ""  # Selected per question type in main().
REPORT_FILE = ""  # Selected per question type in main().


class APILogger:
    def __init__(self):
        self.lock = threading.Lock()
        self.query_logs = {}
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(OUTPUT_DIR, f"api_usage_log_bedrock_{GRADER_MODEL_TAG}_{timestamp}.json")

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


def classify_grader_exception(exc: Exception) -> str:
    """Convert grader/API failures into explicit, non-semantic CSV statuses."""
    error_text = str(exc).lower()
    error_code = str(getattr(exc, "code", "") or "").lower()
    combined = f"{error_code} {error_text}"

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
    # Keep the original SDK/call interface; authenticate only to Bedrock.
    api_key = (
        os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        or os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not api_key:
        raise RuntimeError("A Bedrock API key is required for this grader.")
    region = (os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION")
              or os.getenv("AWS_DEFAULT_REGION") or "us-east-1")
    base_url = f"https://bedrock-mantle.{region}.api.aws/v1"
    return LLMClient(api_key=api_key, base_url=base_url)


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


def direct_llm_grade_row(question: str, ground_truth: str, scan_raw_rows: str, client, model: str) -> dict[str, Any]:
    prompt = f"""
You are a strict but fair evaluator for a finance knowledge-graph QA benchmark.

You will receive:
1. The user question.
2. The SQL-derived ground truth JSON.
3. The pipeline answer JSON.

Your task:
Decide whether the pipeline answer correctly answer the user question, using the ground truth as the reference.

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
- Empty results: If ground truth is empty and the question expects no matching records, an empty pipeline answer can be MATCH. If ground truth is non-empty and pipeline answer is empty, it is usually MISMATCH.
- Extra rows: Extra incorrect rows should reduce the grade. If the correct answer is present but extra wrong rows are included, use PARTIAL unless the extras do not affect the requested answer.
- Field-name differences: Do not require identical field names when the meaning and values clearly correspond.
- Numeric formatting: Treat numeric strings and numbers as equivalent when values are materially the same.
- Numeric tolerance: If the ground truth contains numeric value X, treat the scan value as correct when it is between X - 1.5 and X + 1.5, unless the question explicitly requires exact precision.
- Column resolution: Do not require identical column names. Resolve meaning semantically from the question, ground truth fields, and scan fields. For example, investor id, investor profile, group labels, percentages, averages, totals, and counts may use different aliases if the required meaning is present.

Label definitions:
MATCH:
Use MATCH when the pipeline answer completely answer what the question asks. The answer must have the required rows/entities, values, filters, grouping, aggregation, and ranking/order when applicable. All values required by the question must be semantically equal to the ground truth values. Missing unused ground-truth fields or extra harmless columns are okay.

PARTIAL:
Use PARTIAL when the pipeline answer answer part of the question correctly, but some required information is missing, incomplete, extra, or wrong. Examples: some correct rows but missing others, correct grouping but one metric wrong/missing, correct entities but wrong aggregation, correct top results but wrong order, correct values for some but not all groups, or correct answer plus extra wrong rows.

MISMATCH:
Use MISMATCH when the pipeline answer do not answer the question, are mostly wrong, use wrong filters/entities, use wrong aggregation/ranking, return empty when the ground truth has required results, have required values that conflict with the ground truth, or are unrelated to the ground truth.

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

Pipeline Answer:
{truncate_for_prompt(scan_raw_rows)}
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


def regrade_existing_report(input_csv: str, output_csv: str, client, model: str = LLM_GRADER_MODEL) -> str:
    df = pd.read_csv(input_csv)
    result_column = "New Pipeline Result" if "New Pipeline Result" in df.columns else "Scan Raw Rows"
    required_columns = {"Question", "Ground Truth", result_column}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(f"Grader input is missing required columns: {sorted(missing_columns)}")
    rows = []
    preserve_statuses = {"CRASH", "SCAN_ERROR", "PRE_SCAN_ERROR", "QUOTA_EXHAUSTED"}
    completed_statuses = preserve_statuses | {"MATCH", "PARTIAL", "MISMATCH", "OTHER"}
    existing_rows = []

    if os.path.exists(output_csv):
        try:
            existing_rows = pd.read_csv(output_csv).to_dict(orient="records")
            print(f"[RESUME] Found existing direct LLM graded report with {len(existing_rows)} row(s).")
        except Exception as exc:
            print(f"[WARN] Could not read existing direct LLM graded report for resume: {exc}")

    total_rows = len(df)

    def save_progress() -> None:
        if not rows:
            return
        fieldnames = list(rows[0].keys())
        temp_file = f"{output_csv}.tmp"
        with open(temp_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_file, output_csv)

    for idx, row in df.iterrows():
        row_number = idx + 1
        if idx < len(existing_rows):
            existing_row = existing_rows[idx]
            existing_status = str(existing_row.get("New Status", "") or "").strip().upper()
            existing_path = str(existing_row.get("Direct LLM Grading Path", "") or "").strip()
            if (
                existing_status in completed_statuses
                and (existing_path or existing_status in preserve_statuses)
                and existing_path != "direct_llm_grader_exception"
            ):
                rows.append(existing_row)
                print(f"[GRADE] {row_number}/{total_rows}: resumed {existing_status}", flush=True)
                continue

        updated = row.to_dict()
        execution_status = str(row.get("New Status", "") or "").strip().upper()
        if execution_status in preserve_statuses:
            updated["Direct LLM Grading Path"] = "preserved_execution_status"
            updated["Direct LLM Grader Model"] = model
            rows.append(updated)
            save_progress()
            print(f"[GRADE] {row_number}/{total_rows}: preserved {execution_status}", flush=True)
            continue

        try:
            result = direct_llm_grade_row(
                question=str(row.get("Question", "") or ""),
                ground_truth=str(row.get("Ground Truth", "") or ""),
                scan_raw_rows=str(row.get(result_column, "") or ""),
                client=client,
                model=model,
            )
            updated["New Status"] = result.get("status", "OTHER")
            updated["Comparison / Comments"] = result.get("reason", "")
            updated["Direct LLM Evidence"] = json.dumps(result.get("evidence", {}), ensure_ascii=False, default=str)
            updated["Direct LLM Grading Path"] = "direct_llm_semantic_judgment"
            updated["Direct LLM Grader Model"] = model
        except Exception as exc:
            error_status = classify_grader_exception(exc)
            updated["New Status"] = error_status
            updated["Comparison / Comments"] = f"Direct LLM grader {error_status}: {exc}"
            updated["Direct LLM Evidence"] = "{}"
            updated["Direct LLM Grading Path"] = "direct_llm_grader_exception"
            updated["Direct LLM Grader Model"] = model

        rows.append(updated)
        save_progress()
        print(f"[GRADE] {row_number}/{total_rows}: {updated.get('New Status', 'OTHER')}", flush=True)

    save_progress()
    return output_csv


def main(argv=None):
    import argparse

    global OUTPUT_DIR, RAW_REPORT_FILE, REPORT_FILE, api_logger
    types = ("benchmark", "at_risk_critical", "batch_status", "enrichment_context",
             "multi_step_comparative", "reference_compliance", "scoring_quantitative",
             "temporal_transaction")
    parser = argparse.ArgumentParser(description="Grade the saved SQL reports with this Bedrock model.")
    parser.add_argument("--type", choices=types, action="append", dest="types",
                        help="Grade one type; repeat for several. Default: all eight sequentially.")
    parser.add_argument("--dry-run", action="store_true", help="Check inputs and destinations without API calls or writes.")
    args = parser.parse_args(argv)
    if LLM_GRADER_MODEL != DEFAULT_LLM_GRADER_MODEL:
        parser.error("Unset LLM_GRADER_MODEL and use the script for the intended model.")
    jobs = []
    for name in dict.fromkeys(args.types or types):
        raw = Path(INPUT_ROOT) / name / "raw_pipeline_v9.csv"
        folder = Path(OUTPUT_ROOT) / name
        output = folder / f"graded_bedrock_{GRADER_MODEL_TAG}.csv"
        if not raw.is_file():
            raise FileNotFoundError(f"Raw pipeline report not found: {raw}")
        with raw.open(encoding="utf-8-sig", newline="") as handle:
            columns = set(csv.DictReader(handle).fieldnames or [])
        if not {"Question", "Ground Truth"}.issubset(columns) or not ({"New Pipeline Result", "Scan Raw Rows"} & columns):
            raise ValueError(f"Raw report lacks question, ground truth or pipeline answer: {raw}")
        jobs.append((raw, folder, output))
        print(f"[INPUT] {raw}\n[OUTPUT] {output}")
    print(f"[MODEL] {LLM_GRADER_MODEL}")
    if args.dry_run:
        print(f"[DRY RUN] Validated {len(jobs)} reports. No API calls or writes.")
        return
    grader_client = build_openai_grader_client()
    for raw, folder, output in jobs:
        folder.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR, RAW_REPORT_FILE, REPORT_FILE = str(folder), str(raw), str(output)
        api_logger = APILogger()
        try:
            regrade_existing_report(RAW_REPORT_FILE, REPORT_FILE, grader_client, LLM_GRADER_MODEL)
        finally:
            api_logger.save()
        print(f"[SUCCESS] Direct LLM graded report saved to {REPORT_FILE}")


if __name__ == "__main__":
    main()
