import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import csv
import datetime
import hashlib
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
OUTPUT_DIR = os.getenv("PIPELINE_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "outputs", "full_run"))
DEFAULT_LLM_GRADER_MODEL = "gpt-5-mini"
LLM_GRADER_MODEL = os.getenv("LLM_GRADER_MODEL", DEFAULT_LLM_GRADER_MODEL)
RAW_REPORT_FILE = os.getenv("RAW_REPORT_FILE", os.path.join(OUTPUT_DIR, "raw_pipeline.csv"))
REPORT_FILE = os.getenv("GRADED_REPORT_FILE", os.path.join(OUTPUT_DIR, "graded_gpt_5_mini.csv"))
NULL_POLICY_VERSION = "mc_diverse_extra_null_groups_v1"
SEMANTIC_GRADES = {"MATCH", "PARTIAL", "MISMATCH", "OTHER"}
NULL_REVIEW_CHECKS = (
    "null_groups_not_required", "named_groups_complete", "named_metrics_correct",
    "ordering_correct", "no_population_or_denominator_effect",
)


def is_mc_diverse(row: dict[str, Any], input_csv: str) -> bool:
    category = str(row.get("Category", "")).strip().casefold()
    if category:
        return category in {"multi-step comparative (diverse)", "mc_diverse"}
    return bool(re.match(r"^mc_diverse(?:_|\.|$)", Path(input_csv).name, re.IGNORECASE))


def null_group_candidate(question: str, ground_truth: str, answer: str) -> dict[str, Any] | None:
    """Find extra JSON-null labels; never remove rows or change any metric."""
    if len(question) > 8000 or len(ground_truth) > 60000 or len(answer) > 60000:
        return None
    # Overall-population calculations and explicit unknown groups need strict review.
    if re.search(r"\boverall\b|\bglobal\b|\bacross all investors\b", question, re.IGNORECASE):
        return None
    if re.search(r"\b(null|unknown|missing|unclassified|uncategorized)\s+(group|label|categor|segment)", question, re.IGNORECASE):
        return None
    try:
        reference, actual = json.loads(ground_truth), json.loads(answer)
    except (ValueError, TypeError):
        return None
    if any(not isinstance(rows, list) or not rows or any(not isinstance(r, dict) for r in rows)
           for rows in (reference, actual)):
        return None
    # A winning NULL group must not be excused as an extra row in a top-result answer.
    if re.search(r"\b(top|bottom)\b|\bwhich\b.*\b(highest|lowest|largest|smallest|greatest)\b", question, re.IGNORECASE):
        return None
    aliases = {"groupvalue", "group", "grouplabel", "risk", "risktolerance", "timehorizon",
               "segment", "segmentlabel", "category", "profilecategory", "sectorfocus", "rdfslabel"}

    def group_field(rows):
        fields = {key for r in rows for key in r
                  if re.sub(r"[^a-z0-9]", "", key.lower()) in aliases}
        if len(fields) != 1:
            return None
        field = next(iter(fields))
        return field if all(field in r for r in rows) else None

    ref_field, answer_field = group_field(reference), group_field(actual)
    if ref_field is None or answer_field is None:
        return None
    expected = [r[ref_field] for r in reference]
    if any(not isinstance(value, str) or not value.strip() for value in expected):
        return None
    null_indices = [i for i, r in enumerate(actual) if r[answer_field] is None]
    named = [r[answer_field] for r in actual if r[answer_field] is not None]
    if not null_indices or any(not isinstance(value, str) for value in named):
        return None
    if sorted(expected) != sorted(named):
        return None
    return {"group_field": answer_field, "row_indices": null_indices}


def grading_input_key(row: dict[str, Any], answer_column: str, model: str) -> str:
    fields = ("Sample Row ID", "Question", "Ground Truth", answer_column, "Category", "Source CSV",
              "New Status", "Direct LLM Grader Model", "Comparison / Comments", "Direct LLM Evidence",
              "Original Grade", "Original Grade Reason", "Original Grade Evidence")
    content = [str(row.get(field, "")) for field in fields] + [model]
    return hashlib.sha256(json.dumps(content, ensure_ascii=True).encode("utf-8")).hexdigest()


class APILogger:
    def __init__(self, output_dir=None):
        self.lock = threading.Lock()
        self.query_logs = {}
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(output_dir or OUTPUT_DIR, f"api_usage_log_direct_llm_grader_{timestamp}.json")

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
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for direct LLM grader calls.")
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


def direct_llm_grade_row(question: str, ground_truth: str, scan_raw_rows: str, client, model: str,
                         null_review: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = f"""
You are a strict but fair evaluator for a finance knowledge-graph QA benchmark.

You will receive:
1. The user question.
2. The SQL-derived ground truth JSON.
3. The pipeline scan raw rows JSON.

Your task:
Decide whether the pipeline scan raw rows correctly answer the user question, using the ground truth as the reference.

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
- Empty results: If ground truth is empty and the question expects no matching records, an empty scan result can be MATCH. If ground truth is non-empty and scan result is empty, it is usually MISMATCH.
- Extra rows: Extra incorrect rows should reduce the grade. If the correct answer is present but extra wrong rows are included, use PARTIAL unless the extras do not affect the requested answer.
- Field-name differences: Do not require identical field names when the meaning and values clearly correspond.
- Numeric formatting: Treat numeric strings and numbers as equivalent when values are materially the same.
- Numeric tolerance: If the ground truth contains numeric value X, treat the scan value as correct when it is between X - 1.5 and X + 1.5, unless the question explicitly requires exact precision.
- Column resolution: Do not require identical column names. Resolve meaning semantically from the question, ground truth fields, and scan fields. For example, investor id, investor profile, group labels, percentages, averages, totals, and counts may use different aliases if the required meaning is present.

Label definitions:
MATCH:
Use MATCH when the scan raw rows completely answer what the question asks. The answer must have the required rows/entities, values, filters, grouping, aggregation, and ranking/order when applicable. All values required by the question must be semantically equal to the ground truth values. Missing unused ground-truth fields or extra harmless columns are okay.

PARTIAL:
Use PARTIAL when the scan raw rows answer part of the question correctly, but some required information is missing, incomplete, extra, or wrong. Examples: some correct rows but missing others, correct grouping but one metric wrong/missing, correct entities but wrong aggregation, correct top results but wrong order, correct values for some but not all groups, or correct answer plus extra wrong rows.

MISMATCH:
Use MISMATCH when the scan raw rows do not answer the question, are mostly wrong, use wrong filters/entities, use wrong aggregation/ranking, return empty when the ground truth has required results, have required values that conflict with the ground truth, or are unrelated to the ground truth.

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

Pipeline Scan Raw Rows:
{truncate_for_prompt(scan_raw_rows)}
""".strip()
    prompt = prompt.replace("scan raw rows", "final answer rows").replace(
        "Pipeline Scan Raw Rows:", "Pipeline Final Answer Rows:"
    ).replace("empty scan result", "empty final result").replace("scan result is empty", "final result is empty").replace(
        "scan value", "answer value"
    ).replace("scan fields", "answer fields")

    if null_review is not None:
        prompt += f"""

MC_diverse extra unnamed-group policy ({NULL_POLICY_VERSION}):
Review the COMPLETE, UNMODIFIED answer above. Candidate extra rows and the original
strict verdict are recorded here: {json.dumps(null_review, ensure_ascii=True)}
The only permitted relaxation is to disregard extra rows whose grouping LABEL is
JSON null, when unnamed groups are neither requested nor included in the reference.
A null metric on a named group is NOT a null label. Never convert null to zero or
reinterpret strings such as "NULL", "None", "Unknown" or "" as JSON null.
All required named groups must still appear exactly once, with the correct metrics
and relative ordering. An extra null winner cannot replace the required highest,
lowest or top-k group. Never repair, sort, recompute or fill in an answer.
Preserve penalties for wrong metrics, missing groups, wrong ratios, altered overall
averages, changed denominators, wrong populations, or incomplete comparisons.
An original numeric/metric error cannot be excused under this label-only policy.
Counts/denominators must match exactly; for this adjustment, allow only the rounding
precision shown in the reference for numeric metrics (for example 0.005 for a value
shown to two decimal places), not the general absolute 1.5 tolerance above.
If uncertain about any condition, do not approve the adjustment.
Return the usual status/reason/evidence plus a "null_policy_checks" object with
these literal boolean fields: {json.dumps(list(NULL_REVIEW_CHECKS))}.
Set each field true only after checking it. MATCH is permitted only if all are true
and extra unnamed rows are the only remaining issue. Otherwise retain the original
strict status and explain the unresolved issue.
"""

    api_logger.log_call(question, "Null_Group_Review" if null_review is not None else "Direct_LLM_Grade")
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


def original_grade(row: dict[str, Any], model: str) -> dict[str, Any] | None:
    """Reuse a strict grade only from a graded input, never from a raw success row."""
    if row.get("Direct LLM Grader Model") != model:
        return None
    original = row.get("Original Grade")
    status = original or row.get("New Status")
    if status not in SEMANTIC_GRADES or row.get("Direct LLM Grading Path") not in {
        "direct_llm_semantic_judgment", "direct_llm_null_group_review"
    }:
        return None
    try:
        evidence = json.loads(row.get("Original Grade Evidence" if original else "Direct LLM Evidence") or "{}")
    except (ValueError, TypeError):
        return None
    return {"status": status,
            "reason": row.get("Original Grade Reason" if original else "Comparison / Comments", ""),
            "evidence": evidence}


def regrade_existing_report(input_csv: str, output_csv: str, client, model: str = LLM_GRADER_MODEL,
                            workers: int = 1, retry_nonmatch: bool = False,
                            only_pipeline_success: bool = False) -> str:
    if workers < 1:
        raise ValueError("Grader workers must be positive.")
    if Path(input_csv).resolve() == Path(output_csv).resolve():
        raise ValueError("Use a separate output file to preserve the original report.")
    df = pd.read_csv(input_csv, dtype=str, keep_default_na=False)
    answer_column = "New Pipeline Result" if "New Pipeline Result" in df.columns else "Scan Raw Rows"
    required_columns = {"Question", "Ground Truth", answer_column}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"Input report is missing required columns: {sorted(missing_columns)}")
    if only_pipeline_success:
        if 'New Status' not in df.columns:
            raise ValueError('Success-only grading requires New Status from the raw pipeline report.')
        successful = df['New Status'].str.strip().str.upper().eq('PIPELINE_SUCCESS')
        print(f'[INPUT] Grade {int(successful.sum())} PIPELINE_SUCCESS rows; '
              f'exclude {int((~successful).sum())} other execution statuses.', flush=True)
        df = df.loc[successful].reset_index(drop=True)
    results = {}
    preserve_statuses = {"CRASH", "SCAN_ERROR", "PRE_SCAN_ERROR", "QUOTA_EXHAUSTED",
                         "PIPELINE_FAILURE", "TRANSIENT_ERROR", "QUERY_UNDERSTANDING_ERROR",
                         "DECOMPOSITION_ERROR", "QUERY_SPEC_ERROR", "PROCESSING_SPEC_ERROR",
                         "FINAL_SPEC_ERROR", "EXECUTION_ERROR"}
    completed_statuses = preserve_statuses | SEMANTIC_GRADES
    existing_by_input = {}

    if os.path.exists(output_csv):
        try:
            existing_rows = pd.read_csv(output_csv, dtype=str, keep_default_na=False).to_dict(orient="records")
            for existing in existing_rows:
                if existing.get("Grading Input Key"):
                    existing_by_input[(existing["Grading Input Key"], existing.get("Grading Policy"))] = existing
            print(f"[RESUME] Found existing direct LLM graded report with {len(existing_rows)} row(s).")
        except Exception as exc:
            if retry_nonmatch:
                raise ValueError('Cannot read existing grades safely for retry; report left unchanged.') from exc
            print(f"[WARN] Could not read existing direct LLM graded report for resume: {exc}")

    total_rows = len(df)
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    if retry_nonmatch and os.path.exists(output_csv):
        import shutil
        import time
        backup = f'{output_csv}.backup_{time.time_ns()}.csv'
        shutil.copy2(output_csv, backup)
        print(f'[BACKUP] {backup}', flush=True)
        # Keep prior grades checkpointed until their replacements finish. A
        # stop/quota failure must not discard grades awaiting their retry.
        for index, row in enumerate(df.to_dict(orient='records')):
            policy = NULL_POLICY_VERSION if is_mc_diverse(row, input_csv) else 'strict_v1'
            previous = existing_by_input.get((grading_input_key(row, answer_column, model), policy))
            if previous:
                results[index] = previous
        print('[RETRY] Regrade MISMATCH/PARTIAL and grader errors; reuse unchanged MATCH grades. '
              'New or changed answers are graded normally. Unresolved pipeline errors remain errors.', flush=True)
    print(f"[SYSTEM] Grader workers: {workers}; questions: {total_rows}; answer column: {answer_column}", flush=True)

    def save_progress() -> None:
        rows = [results[index] for index in sorted(results)]
        if not rows and not only_pipeline_success:
            return
        fieldnames = list(dict.fromkeys(field for row in rows for field in row)) if rows else list(df.columns)
        temp_file = f"{output_csv}.tmp"
        with open(temp_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_file, output_csv)

    def grade(row):
        updated = dict(row)
        policy = NULL_POLICY_VERSION if is_mc_diverse(updated, input_csv) else "strict_v1"
        input_key = grading_input_key(updated, answer_column, model)
        existing_row = existing_by_input.get((input_key, policy))
        if existing_row:
            existing_status = str(existing_row.get("New Status", "") or "").strip().upper()
            existing_path = str(existing_row.get("Direct LLM Grading Path", "") or "").strip()
            if (
                existing_status in completed_statuses
                and (not retry_nonmatch or existing_status == 'MATCH' or existing_status in preserve_statuses)
                and (existing_path or existing_status in preserve_statuses)
                and existing_path != "direct_llm_grader_exception"
                and existing_row.get("Null Policy Status") != "review_error"
            ):
                return existing_row

        baseline = None if retry_nonmatch else original_grade(updated, model) or original_grade(existing_row or {}, model)
        updated.update({
            "Original Grade": baseline["status"] if baseline else "",
            "Original Grade Reason": baseline["reason"] if baseline else "",
            "Original Grade Evidence": json.dumps(baseline["evidence"]) if baseline else "{}",
            "Grading Policy": policy,
            "Grading Input Key": input_key,
            "Null Policy Status": "not_applicable",
            "Null Policy Reason": "",
            "Null Policy Evidence": "{}",
            "Direct LLM Evidence": "{}",
            "Direct LLM Grading Path": "",
            "Direct LLM Grader Model": model,
        })
        execution_status = str(row.get("New Status", "") or "").strip().upper()
        if execution_status in preserve_statuses:
            updated["Direct LLM Grading Path"] = "preserved_execution_status"
            updated["Direct LLM Grader Model"] = model
            return updated

        try:
            result = baseline or direct_llm_grade_row(
                question=str(row.get("Question", "") or ""),
                ground_truth=str(row.get("Ground Truth", "") or ""),
                scan_raw_rows=str(row.get(answer_column, "") or ""),
                client=client,
                model=model,
            )
            updated["New Status"] = result.get("status", "OTHER")
            updated["Comparison / Comments"] = result.get("reason", "")
            updated["Direct LLM Evidence"] = json.dumps(result.get("evidence", {}), ensure_ascii=False, default=str)
            updated["Direct LLM Grading Path"] = "direct_llm_semantic_judgment"
            updated["Direct LLM Grader Model"] = model
            updated["Original Grade"] = result.get("status", "OTHER")
            updated["Original Grade Reason"] = result.get("reason", "")
            updated["Original Grade Evidence"] = updated["Direct LLM Evidence"]
            candidate = null_group_candidate(row["Question"], row["Ground Truth"], row[answer_column]) if policy == NULL_POLICY_VERSION else None
            if candidate and result.get("status") in {"PARTIAL", "MISMATCH"}:
                try:
                    review = direct_llm_grade_row(
                        question=row["Question"], ground_truth=row["Ground Truth"],
                        scan_raw_rows=row[answer_column], client=client, model=model,
                        null_review={**candidate, "original_grade": result},
                    )
                    checks = review.get("null_policy_checks", {})
                    approved = (review.get("status") == "MATCH" and isinstance(checks, dict)
                                and all(checks.get(key) is True for key in NULL_REVIEW_CHECKS))
                    updated["Null Policy Status"] = "adjusted" if approved else "retained"
                    updated["Null Policy Reason"] = review.get("reason", "No adjustment approved.")
                    if not approved and review.get("status") == "MATCH":
                        updated["Null Policy Reason"] += " Original grade retained because required review checks were not all true."
                    updated["Null Policy Evidence"] = json.dumps({"candidate": candidate, "review": review}, ensure_ascii=False)
                    if approved:
                        updated["New Status"] = "MATCH"
                        updated["Comparison / Comments"] = "Extra unnamed group(s) ignored after review. " + review.get("reason", "")
                        updated["Direct LLM Evidence"] = json.dumps(review.get("evidence", {}), ensure_ascii=False)
                        updated["Direct LLM Grading Path"] = "direct_llm_null_group_review"
                except Exception as exc:
                    updated["Null Policy Status"] = "review_error"
                    updated["Null Policy Reason"] = f"Original grade retained; {classify_grader_exception(exc)}: {exc}"
        except Exception as exc:
            error_status = classify_grader_exception(exc)
            updated["New Status"] = error_status
            updated["Comparison / Comments"] = f"Direct LLM grader {error_status}: {exc}"
            updated["Direct LLM Evidence"] = "{}"
            updated["Direct LLM Grading Path"] = "direct_llm_grader_exception"
            updated["Direct LLM Grader Model"] = model

        return updated

    stopped = False
    completed_this_run = 0
    pending = iter(enumerate(df.to_dict(orient="records")))
    # Each worker grades one question. Only this coordinator writes checkpoints,
    # in input order, so completed non-prefix rows can safely resume by input key.
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="grader") as pool:
        active = {}

        def submit_next():
            item = next(pending, None)
            if item is not None:
                index, row = item
                active[pool.submit(grade, row)] = index

        for _ in range(workers):
            submit_next()
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                index = active.pop(future)
                updated = future.result()
                results[index] = updated
                completed_this_run += 1
                if (updated.get("Direct LLM Grading Path") == "direct_llm_grader_exception"
                        and updated.get("New Status") in {"MODEL_NOT_FOUND", "QUOTA_EXHAUSTED"}):
                    stopped = True
                save_progress()
                print(f"[GRADE] {completed_this_run}/{total_rows}: {updated.get('New Status', 'OTHER')} "
                      f"(input row {index + 1})", flush=True)
            if not stopped:
                for _ in done:
                    submit_next()

    save_progress()
    if stopped:
        raise RuntimeError("Grading stopped after a model-access or quota error. Completed rows are saved; "
                           "resolve the error and rerun the same command to resume.")
    return output_csv


def main(argv=None):
    global api_logger
    parser = argparse.ArgumentParser(description="Grade pipeline answers and resume saved grades.")
    parser.add_argument("--input", type=Path, default=Path(RAW_REPORT_FILE))
    parser.add_argument("--output", type=Path, default=Path(REPORT_FILE))
    parser.add_argument("--model", default=LLM_GRADER_MODEL)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument('--retry-nonmatch', action='store_true',
                        help='Regrade MISMATCH/PARTIAL and grader errors; retain unchanged MATCH grades.')
    parser.add_argument('--only-pipeline-success', action='store_true',
                        help='Only include PIPELINE_SUCCESS rows from the raw input in the graded output.')
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive.")
    input_csv, output_csv = str(args.input.resolve()), str(args.output.resolve())
    if args.input.resolve() == args.output.resolve():
        parser.error("--input and --output must be different files.")
    if not args.input.is_file():
        parser.error(f"Raw pipeline report not found: {input_csv}")
    print("\n" + "=" * 50)
    print(f"INITIALIZING DIRECT {args.model} LLM GRADER")
    print("=" * 50)
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    api_logger = APILogger(os.path.dirname(output_csv))

    grader_client = build_openai_grader_client()
    print(f"[SYSTEM] Raw report: {input_csv}")
    print(f"[SYSTEM] Direct LLM graded report: {output_csv}")
    print(f"[SYSTEM] Direct LLM grader model: {args.model}")
    try:
        regrade_existing_report(input_csv, output_csv, grader_client, args.model,
                                workers=args.workers, retry_nonmatch=args.retry_nonmatch,
                                only_pipeline_success=args.only_pipeline_success)
    finally:
        api_logger.save()
    print(f"[SUCCESS] Direct LLM graded report saved to {output_csv}")


if __name__ == "__main__":
    main()
