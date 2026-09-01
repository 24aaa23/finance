import datetime
import json
import os
import re
import threading
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict

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
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))), "aop_generate_500_multitable", ".env"),
    ]
    for env_file in env_candidates:
        if not os.path.exists(env_file):
            continue
        with open(env_file, encoding="utf-8-sig") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), value)


load_local_env_file()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIFF_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
OUTPUT_DIR = os.getenv("PIPELINE_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "output"))
DEFAULT_GPT_OSS_MODEL = "openai.gpt-oss-120b-1:0"
GPT_OSS_MODEL = os.getenv("BEDROCK_GPT_OSS_MODEL", DEFAULT_GPT_OSS_MODEL)
DEFAULT_LLM_GRADER_MODEL = GPT_OSS_MODEL
LLM_GRADER_MODEL = os.getenv("LLM_GRADER_MODEL", DEFAULT_LLM_GRADER_MODEL)
DETERMINISTIC_EXPLAIN = os.getenv("DETERMINISTIC_EXPLAIN", "1").strip().lower() not in {"0", "false", "no"}
REPORT_FILE = os.getenv("GRADED_REPORT_FILE", os.path.join(OUTPUT_DIR, "graded_mistral_mistral_large_3_675b_instruct_hybrid1_train_gptoss_grader_check.csv"))
RAW_REPORT_FILE = os.getenv("RAW_REPORT_FILE", os.path.join(OUTPUT_DIR, "raw_pipeline_mistral_mistral_large_3_675b_instruct_hybrid1_train.csv"))


class APILogger:
    def __init__(self):
        self.lock = threading.Lock()
        self.query_logs = {}
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Save directly to the new organized folder
        self.log_file = os.path.join(OUTPUT_DIR, f"api_usage_log_{timestamp}.json")

    def log_call(self, query, function_name):
        with self.lock:
            q_key = query if query else "Unknown_Query"
            if q_key not in self.query_logs:
                self.query_logs[q_key] = {"total_calls": 0, "functions": {}}

            self.query_logs[q_key]["total_calls"] += 1
            self.query_logs[q_key]["functions"][function_name] = self.query_logs[q_key]["functions"].get(function_name, 0) + 1

    def save(self):
        with self.lock:
            with open(self.log_file, "w") as f:
                json.dump(self.query_logs, f, indent=4)

api_logger = APILogger()


def build_gpt_oss_client():
    api_key = (
        os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not api_key:
        raise RuntimeError("AWS_BEDROCK_API_KEY is required for the GPT-OSS 120B Bedrock endpoint.")
    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError("BEDROCK_REGION is required for the GPT-OSS 120B Bedrock endpoint.")
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"
    return LLMClient(api_key=api_key, base_url=base_url)


def build_openai_grader_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for GPT-5.6 Sol deterministic grader helper calls.")
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        return LLMClient(api_key=api_key, base_url=base_url)
    return LLMClient(api_key=api_key)


def parse_llm_json(raw_text: str, default: Any, context: str) -> Any:
    text = (raw_text or "").strip()
    if not text:
        print(f"[WARN] Empty JSON response from {context}; using default.")
        return default

    text = text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    candidates = [text]

    array_start = text.find("[")
    array_end = text.rfind("]")
    if array_start != -1 and array_end > array_start:
        candidates.append(text[array_start:array_end + 1])

    object_start = text.find("{")
    object_end = text.rfind("}")
    if object_start != -1 and object_end > object_start:
        candidates.append(text[object_start:object_end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[start:])
            return parsed
        except json.JSONDecodeError:
            continue

    preview = text[:300].replace("\n", " ")
    print(f"[WARN] Invalid JSON response from {context}; using default. Response preview: {preview}")
    return default





def normalize_for_compare(value: Any) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", str(value).lower()).strip()


def snake_case_key(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return normalize_for_compare(text).replace(" ", "_")


BENCHMARK_KEY_ALIASES = {
    "average": "avg",
    "maximum": "max",
    "minimum": "min",
    "percentage": "pct",
    "identifier": "id",
    "risk_tolerance_group": "risk_tolerance",
    "avg_goal_progress_pct": "avg_goal_progress",
    "goal_progress_pct": "goal_progress",
    "investment_name": "investment_name",
    "investment_type": "investment_type",
    "investor_id": "investor_id",
    "investor_name": "investor_name",
    "holding_id": "holding_id",
    "goal_id": "goal_id",
}


def canonical_benchmark_key(key: Any) -> str:
    normalized_key = snake_case_key(key)
    replacements = {
        "average": "avg",
        "maximum": "max",
        "minimum": "min",
        "percentage": "pct",
    }
    normalized_key = "_".join(
        replacements.get(part, part)
        for part in normalized_key.split("_")
        if part
    )
    return BENCHMARK_KEY_ALIASES.get(normalized_key, normalized_key)


def benchmark_decimal(value: Any):
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def benchmark_decimal_precision(value: Any) -> int:
    if isinstance(value, float):
        text = format(value, "f").rstrip("0").rstrip(".")
    else:
        text = str(value).strip().replace(",", "")
    if "." not in text:
        return 0
    return len(text.split(".", 1)[1])


def benchmark_values_equal(expected_value, actual_value) -> bool:
    expected_decimal = benchmark_decimal(expected_value)
    actual_decimal = benchmark_decimal(actual_value)
    if expected_decimal is not None and actual_decimal is not None:
        precision = benchmark_decimal_precision(expected_value)
        if precision == 0:
            return expected_decimal == actual_decimal
        quantizer = Decimal("1").scaleb(-precision)
        expected_quantized = expected_decimal.quantize(quantizer, rounding=ROUND_HALF_UP)
        actual_quantized = actual_decimal.quantize(quantizer, rounding=ROUND_HALF_UP)
        return actual_quantized == expected_quantized

    return normalize_benchmark_value(actual_value) == normalize_benchmark_value(expected_value)


def detect_ground_truth_format(ground_truth: str) -> str:
    text = str(ground_truth or "").strip()
    if not text:
        return "invalid_json"
    if text[0] in "[{":
        try:
            json.loads(text)
            return "json"
        except Exception:
            return "invalid_json"
    return "text"


def extract_json_candidate(raw_text: str):
    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("empty text")
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.I | re.S)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    starts = [idx for idx in (text.find("["), text.find("{")) if idx >= 0]
    if not starts:
        raise ValueError("no JSON object or array found")
    start = min(starts)
    close_char = "]" if text[start] == "[" else "}"
    end = text.rfind(close_char)
    if end < start:
        raise ValueError("JSON close delimiter not found")
    return json.loads(text[start:end + 1])


def parse_benchmark_json_rows(raw_text: str) -> tuple[bool, list]:
    try:
        parsed = extract_json_candidate(raw_text)
    except Exception:
        return False, []
    if isinstance(parsed, list):
        return True, parsed
    return True, [parsed]


def local_identifier(value: str) -> str:
    text = str(value or "").strip()
    if re.match(r"https?://", text):
        text = re.split(r"[/#]", text.rstrip("/#"))[-1]
    return text


def normalize_benchmark_value(value: Any) -> Any:
    if isinstance(value, str):
        text = local_identifier(value).strip()
        if text.upper() in {"NULL", "NONE", "NAN"}:
            return None
        if re.fullmatch(r"[A-Za-z]+[-_ ]?\d+", text):
            return re.sub(r"[^a-z0-9]+", "", text.lower())
        try:
            return round(float(text.replace(",", "")), 3)
        except ValueError:
            return normalize_for_compare(text)
    if isinstance(value, (int, float)):
        return round(float(value), 3)
    return value


def normalize_benchmark_row(row: Any) -> Any:
    if not isinstance(row, dict):
        return normalize_benchmark_value(row)
    return {canonical_benchmark_key(key): normalize_benchmark_value(value) for key, value in row.items()}


def benchmark_rows_from_text(raw_text: str, limit: int | None = None) -> list:
    ok, rows = parse_benchmark_json_rows(raw_text)
    if not ok:
        return []
    return rows[:limit] if limit is not None else rows


def benchmark_columns_from_rows(rows: list, canonical: bool = True) -> list:
    columns = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            column = canonical_benchmark_key(key) if canonical else str(key)
            if column not in columns:
                columns.append(column)
    return columns


def summarize_ground_truth_columns(rows: list, max_samples: int = 3) -> dict:
    summary = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for column, value in row.items():
            key = canonical_benchmark_key(column)
            info = summary.setdefault(key, {"type": "", "samples": [], "null_count": 0})
            if value is None:
                info["null_count"] += 1
                continue
            if not info["type"]:
                if isinstance(value, bool):
                    info["type"] = "boolean"
                elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                    info["type"] = "number"
                else:
                    info["type"] = "string"
            if len(info["samples"]) < max_samples and value not in info["samples"]:
                info["samples"].append(value)
    for info in summary.values():
        if not info["type"]:
            info["type"] = "null"
    return summary


def verify_grading_contract_columns(question: str, expected_rows: list, contract: dict, available_columns: list) -> dict:
    required_columns = list(dict.fromkeys(contract.get("required_columns", [])))
    identity_columns = list(dict.fromkeys(contract.get("identity_columns", [])))
    question_text = normalize_for_compare(question or "")
    normalized_rows = [normalize_benchmark_row(row) for row in expected_rows]

    required_columns = [column for column in required_columns if column in available_columns]
    identity_columns = [column for column in identity_columns if column in available_columns]

    comparison_mode = str(contract.get("comparison_mode", "row_set")).lower().strip()
    grouped_words = ("for each", " across ", " by ", " per ", "within each", "compare by")
    grouped_question = any(word in f" {question_text} " for word in grouped_words)
    if comparison_mode == "grouped" or grouped_question:
        candidate_identity = [
            column for column in required_columns
            if not column.startswith(("avg_", "sum_", "total_", "count_", "min_", "max_"))
            and not column.endswith(("_count", "_amount", "_value", "_score", "_pct", "_percentage", "_rate"))
        ]
        if not identity_columns and candidate_identity:
            identity_columns = candidate_identity[:1]
        if candidate_identity and comparison_mode == "row_set":
            comparison_mode = "grouped"

    for column in identity_columns:
        if column not in required_columns:
            required_columns.insert(0, column)

    selected = set(required_columns + identity_columns)
    if selected and normalized_rows:
        signatures = []
        collapsed = False
        for row in normalized_rows:
            if not isinstance(row, dict):
                continue
            signature = row_signature({column: row.get(column) for column in sorted(selected)})
            if signature in signatures:
                collapsed = True
                break
            signatures.append(signature)
        if collapsed:
            for column in available_columns:
                if column.endswith("_id"):
                    candidate = set(selected)
                    candidate.add(column)
                    candidate_signatures = []
                    fixes_collapse = True
                    for row in normalized_rows:
                        if not isinstance(row, dict):
                            continue
                        signature = row_signature({item: row.get(item) for item in sorted(candidate)})
                        if signature in candidate_signatures:
                            fixes_collapse = False
                            break
                        candidate_signatures.append(signature)
                    if fixes_collapse:
                        if column not in identity_columns:
                            identity_columns.append(column)
                        if column not in required_columns:
                            required_columns.insert(0, column)
                        break

    if not required_columns:
        required_columns = list(available_columns)
    corrected = dict(contract)
    corrected["required_columns"] = [column for column in required_columns if column in available_columns]
    corrected["identity_columns"] = [column for column in identity_columns if column in available_columns]
    corrected["comparison_mode"] = comparison_mode
    return corrected


def infer_grading_contract(question: str, ground_truth: str, client, model: str) -> dict:
    ok, expected_rows = parse_benchmark_json_rows(ground_truth)
    if not ok:
        return {"required_columns": [], "identity_columns": [], "comparison_mode": "row_set", "order_matters": False, "multiplicity_matters": False}
    normalized_rows = [normalize_benchmark_row(row) for row in expected_rows]
    available_columns = sorted({column for row in normalized_rows if isinstance(row, dict) for column in row.keys()})
    if not available_columns:
        return {"required_columns": [], "identity_columns": [], "comparison_mode": "scalar", "order_matters": False, "multiplicity_matters": False}
    column_info = summarize_ground_truth_columns(expected_rows)
    prompt = f"""
Pick the ground-truth columns needed to check the answer that the question asks to return.

First decide what the question asks to return.
When a question asks which entities are returned, include condition columns only when the question asks to return their values.

The ground-truth columns are the expected answer columns.
Keep columns needed to verify the final answer.
Remove only columns that are clearly filter-only or extra context.
Use exact column names from the Ground-truth columns list. Do not invent names.

Return only:
- required_columns: ground-truth columns that the pipeline answer must contain or match.
- identity_columns: columns used to match rows/entities/groups before comparing values.
- comparison_mode, order_matters, multiplicity_matters.

Important rules:
- Identity columns must also appear in required_columns.
- For "Which investors/holdings/accounts/transactions..." questions, keep the returned entity id/name columns from ground truth.
- Do not include threshold/filter columns unless the question asks to return their values.
- If the question asks "above/below/equal/missing/with/without" using a column, that column is usually filter-only.
- For "for each", "across", "by", "per", or "within each" questions, use the group column as identity_columns.
- If the question asks for count/sum/average/min/max/total/percentage/value, keep that measure column.
- comparison_mode is scalar, row_set, grouped, or ordered.
- Use ordered when the question asks for ranking, top/bottom, highest/lowest, first/last, chronological order, or explicit sequence.
- order_matters is true only for explicitly ordered answers.
- multiplicity_matters is true only when duplicate output rows themselves are separate answers. Aggregate count columns do not mean multiplicity_matters.

Examples:
Question: Which holdings have current_value above 10000000?
Columns: ["holding_id","investor_id","investment_name","current_value"]
Answer: {{"required_columns":["holding_id"],"identity_columns":["holding_id"],"comparison_mode":"row_set","order_matters":false,"multiplicity_matters":false}}

Question: Using the rule that Short-term investors should not hold Private Equity investment_type, which Short-term investors have Private Equity holdings?
Columns: ["investor_id","investor_name","time_horizon"]
Answer: {{"required_columns":["investor_id","investor_name"],"identity_columns":["investor_id"],"comparison_mode":"row_set","order_matters":false,"multiplicity_matters":false}}

Question: For each cash-flow type, what is the transaction count and net amount?
Columns: ["type","transaction_count","net_amount"]
Answer: {{"required_columns":["type","transaction_count","net_amount"],"identity_columns":["type"],"comparison_mode":"grouped","order_matters":false,"multiplicity_matters":false}}

Question: How do average goal_match_pct and average risk_score compare by time_horizon?
Columns: ["time_horizon","avg_goal_match_pct","avg_risk_score"]
Answer: {{"required_columns":["time_horizon","avg_goal_match_pct","avg_risk_score"],"identity_columns":["time_horizon"],"comparison_mode":"grouped","order_matters":false,"multiplicity_matters":false}}



Question: Which investors have total current holding value above 10000000?
Columns: ["investor_id","investor_name","total_current_value"]
Answer: {{"required_columns":["investor_id","investor_name"],"identity_columns":["investor_id"],"comparison_mode":"row_set","order_matters":false,"multiplicity_matters":false}}

Question:
{question}

Ground-truth columns:
{json.dumps(available_columns, ensure_ascii=False)}

Ground-truth column info:
{json.dumps(column_info, ensure_ascii=False, default=str)}

Example rows:
{json.dumps(expected_rows[:3], ensure_ascii=False, default=str)}

Reply as:
{{"required_columns":["answer_column"],"identity_columns":["row_id_column"],"comparison_mode":"row_set","order_matters":false,"multiplicity_matters":false}}
Before replying, verify every returned column name is exactly one of the Ground-truth columns above.
"""
    parsed = None
    try:
        api_logger.log_call(question, "Requirement_Analyzer")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw_content = response.choices[0].message.content
        parsed = parse_llm_json(raw_content, None, "Requirement_Analyzer")
    except Exception as exc:
        parsed = None
    available_set = set(available_columns)
    def valid_columns(field: str) -> list:
        values = parsed.get(field, []) if isinstance(parsed, dict) else []
        if not isinstance(values, list):
            return []
        result = []
        for value in values:
            column = canonical_benchmark_key(value)
            if column in available_set and column not in result:
                result.append(column)
        return result
    required_columns = valid_columns("required_columns")
    identity_columns = valid_columns("identity_columns")
    if not required_columns:
        required_columns = available_columns
    comparison_mode = str(parsed.get("comparison_mode", "row_set") if isinstance(parsed, dict) else "row_set").lower().strip()
    if comparison_mode not in {"scalar", "row_set", "grouped", "ordered"}:
        comparison_mode = "row_set"
    order_matters = bool(parsed.get("order_matters", comparison_mode == "ordered")) if isinstance(parsed, dict) else comparison_mode == "ordered"
    multiplicity_matters = bool(parsed.get("multiplicity_matters", False)) if isinstance(parsed, dict) else False
    contract = {"required_columns": required_columns, "identity_columns": identity_columns, "comparison_mode": comparison_mode, "order_matters": order_matters, "multiplicity_matters": multiplicity_matters}
    corrected = verify_grading_contract_columns(question, expected_rows, contract, available_columns)
    if corrected.get("required_columns") != required_columns or corrected.get("identity_columns") != identity_columns:
        corrected["contract_verification"] = "Restored deterministically necessary columns after LLM selection."
    return corrected


def infer_column_mapping(question: str, grading_contract: dict, ground_truth: str, scan_raw_rows: str, schema_context: dict | None, client, model: str) -> dict:
    expected_rows = benchmark_rows_from_text(ground_truth)
    actual_rows = benchmark_rows_from_text(scan_raw_rows)
    required_columns = grading_contract.get("required_columns", [])
    identity_columns = grading_contract.get("identity_columns", [])
    actual_columns = benchmark_columns_from_rows(actual_rows, canonical=False)
    ground_truth_columns = list(dict.fromkeys(required_columns + identity_columns))
    ground_truth_info = summarize_ground_truth_columns(expected_rows)
    actual_info = summarize_ground_truth_columns(actual_rows)
    prompt = f"""
Map actual pipeline columns to ground-truth columns by reading the question, column names, and sample values below.
Mapping direction is actual pipeline column -> ground-truth column.
Map every actual pipeline column that clearly corresponds to one of the needed ground-truth columns.
Partial mapping is allowed: if some needed ground-truth columns are missing from actual output, still map the columns that are present.
Column names may differ by camelCase, snake_case, abbreviations, suffixes, or wording.
Use sample values to decide whether two columns contain the same kind of data.
If a ground-truth column is generic, such as group_value, map the actual group-by column from the question to it.
Do not grade the answer. Do not compare correctness. Do not transform values.
Return an empty mapping only when no actual column plausibly corresponds to any needed ground-truth column.

Ground-truth columns to match:
{json.dumps(ground_truth_columns, ensure_ascii=False)}

Actual pipeline columns:
{json.dumps(actual_columns, ensure_ascii=False)}

Ground-truth column info:
{json.dumps({column: ground_truth_info.get(column, {}) for column in ground_truth_columns}, ensure_ascii=False, default=str)}

Actual column info:
{json.dumps(actual_info, ensure_ascii=False, default=str)}

Relevant schema context:
{json.dumps(schema_context or {}, ensure_ascii=False, default=str)}

Ground-truth example rows:
{json.dumps(expected_rows[:10], ensure_ascii=False, default=str)}

Actual example rows:
{json.dumps(actual_rows[:10], ensure_ascii=False, default=str)}

Question:
{question}

Reply as:
{{"column_mapping":{{"actual_pipeline_column":"ground_truth_column"}}}}
Before replying, verify every mapping source is exactly one actual pipeline column and every mapping target is exactly one ground-truth column.
"""
    def is_placeholder_mapping(mapping: Any) -> bool:
        return mapping == {"actual_pipeline_column": "ground_truth_column"}

    def extract_column_mapping_json(raw: str, stage: str) -> dict:
        text = str(raw or "")
        without_reasoning = re.sub(r"(?is)<(?:reasoning|think)>.*?</(?:reasoning|think)>", "", text).strip()
        candidates = []

        def collect_json_objects(candidate_text: str):
            decoder = json.JSONDecoder()
            for index, character in enumerate(candidate_text):
                if character != "{":
                    continue
                try:
                    parsed_object, _ = decoder.raw_decode(candidate_text[index:])
                except Exception:
                    continue
                if isinstance(parsed_object, dict) and isinstance(parsed_object.get("column_mapping"), dict):
                    candidates.append(parsed_object)

        collect_json_objects(without_reasoning)
        collect_json_objects(text)
        usable = [
            candidate for candidate in candidates
            if candidate.get("column_mapping") and not is_placeholder_mapping(candidate.get("column_mapping"))
        ]
        if usable:
            return usable[-1]
        if candidates:
            latest = dict(candidates[-1])
            if is_placeholder_mapping(latest.get("column_mapping")):
                latest["column_mapping"] = {}
            return latest
        parsed = parse_llm_json(without_reasoning or text, None, stage)
        if isinstance(parsed, dict) and is_placeholder_mapping(parsed.get("column_mapping")):
            parsed = dict(parsed)
            parsed["column_mapping"] = {}
        return parsed if isinstance(parsed, dict) else {"column_mapping": {}}

    def call_column_mapper(mapper_prompt: str, stage: str) -> tuple[dict | None, str]:
        api_logger.log_call(question, stage)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": mapper_prompt}],
            temperature=0,
        )
        raw = response.choices[0].message.content
        return extract_column_mapping_json(raw, stage), raw

    try:
        parsed, raw_content = call_column_mapper(prompt, "Column_Mapper")
    except Exception as exc:
        return {"column_mapping": {}, "is_valid": False, "llm_attempts": 0, "reason": f"Column mapper failed: {exc}"}
    mapping = parsed.get("column_mapping", {}) if isinstance(parsed, dict) else {}
    if not isinstance(mapping, dict):
        mapping = {}
    if is_placeholder_mapping(mapping):
        mapping = {}
    attempts = 1
    retry_raw_content = ""
    if not mapping:
        retry_prompt = f"""
Your previous column mapping was empty or unusable.
This is likely wrong if any actual pipeline column corresponds to a needed ground-truth column.

Map hybrid1 possible available columns. Partial mapping is allowed.
Do not return an empty mapping unless absolutely no actual column matches any needed ground-truth column.
Use exact column names from the lists below.
Mapping direction is actual pipeline column -> ground-truth column.

Ground-truth columns to match:
{json.dumps(ground_truth_columns, ensure_ascii=False)}

Actual pipeline columns:
{json.dumps(actual_columns, ensure_ascii=False)}

Ground-truth example rows:
{json.dumps(expected_rows[:10], ensure_ascii=False, default=str)}

Actual example rows:
{json.dumps(actual_rows[:10], ensure_ascii=False, default=str)}

Question:
{question}

Previous raw response:
{raw_content}

Reply as:
{{"column_mapping":{{"actual_pipeline_column":"ground_truth_column"}}}}
"""
        try:
            retry_parsed, retry_raw_content = call_column_mapper(retry_prompt, "Column_Mapper_Retry")
            retry_mapping = retry_parsed.get("column_mapping", {}) if isinstance(retry_parsed, dict) else {}
            if is_placeholder_mapping(retry_mapping):
                retry_mapping = {}
            if isinstance(retry_mapping, dict) and retry_mapping:
                parsed = retry_parsed
                mapping = retry_mapping
            attempts = 2
        except Exception:
            attempts = 2
    reason = "Column mapper returned JSON."
    if attempts == 2:
        reason = "Column mapper retried after empty/invalid first mapping."
    return {
        "column_mapping": mapping,
        "is_valid": isinstance(parsed, dict),
        "llm_attempts": attempts,
        "reason": reason,
        "first_raw_response": raw_content,
        "retry_raw_response": retry_raw_content,
    }


def validate_column_mapping(column_mapping: dict, actual_columns: list, ground_truth_columns: list) -> dict:
    actual_exact = set(str(column) for column in actual_columns)
    gt_exact = set(str(column) for column in ground_truth_columns)
    actual_canonical_set = {canonical_benchmark_key(column) for column in actual_columns}
    actual_by_canonical = {}
    gt_by_canonical = {}
    for column in actual_columns:
        actual_by_canonical.setdefault(canonical_benchmark_key(column), str(column))
    for column in ground_truth_columns:
        gt_by_canonical.setdefault(canonical_benchmark_key(column), str(column))
    valid = {}
    used_targets = set()
    for source, target in (column_mapping or {}).items():
        source_text = str(source)
        target_text = str(target)
        resolved_source = source_text if source_text in actual_exact else actual_by_canonical.get(canonical_benchmark_key(source_text))
        resolved_target = target_text if target_text in gt_exact else gt_by_canonical.get(canonical_benchmark_key(target_text))
        if not resolved_source or not resolved_target:
            continue
        canonical_target = canonical_benchmark_key(resolved_target)
        canonical_source = canonical_benchmark_key(resolved_source)
        if canonical_target in actual_canonical_set and canonical_source != canonical_target:
            continue
        if canonical_target in used_targets:
            continue
        valid[resolved_source] = canonical_target
        used_targets.add(canonical_target)
    return valid


def apply_column_mapping(rows: list, column_mapping: dict) -> list:
    mapped_rows = []
    for row in rows:
        if not isinstance(row, dict):
            mapped_rows.append(row)
            continue
        mapped = dict(row)
        for source, target in (column_mapping or {}).items():
            if source in row and target not in mapped:
                mapped[target] = row[source]
        mapped_rows.append(mapped)
    return mapped_rows


def project_row(row: Any, columns: list) -> Any:
    normalized = normalize_benchmark_row(row)
    if not isinstance(normalized, dict):
        return normalized
    return {column: normalized.get(column) for column in columns if column in normalized}


def row_signature(row: Any) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)


def rows_equal_on_columns(expected_row: Any, actual_row: Any, columns: list) -> bool:
    if isinstance(expected_row, dict) and isinstance(actual_row, dict):
        compare_columns = columns or list(expected_row.keys())
        for column in compare_columns:
            if column not in actual_row:
                return False
            if not benchmark_values_equal(expected_row.get(column), actual_row.get(column)):
                return False
        return True
    return benchmark_values_equal(expected_row, actual_row)


def tolerant_unordered_row_counts(expected_rows: list, actual_rows: list, columns: list) -> tuple[int, list, list]:
    unmatched_actual = list(range(len(actual_rows)))
    missing_rows = []
    matched = 0
    for expected_row in expected_rows:
        found_index = None
        for actual_index in unmatched_actual:
            if rows_equal_on_columns(expected_row, actual_rows[actual_index], columns):
                found_index = actual_index
                break
        if found_index is None:
            missing_rows.append(row_signature(expected_row))
        else:
            unmatched_actual.remove(found_index)
            matched += 1
    extra_rows = [row_signature(actual_rows[index]) for index in unmatched_actual]
    return matched, missing_rows, extra_rows


def unique_rows_by_signature(rows: list) -> list:
    unique = {}
    for row in rows:
        unique.setdefault(row_signature(row), row)
    return list(unique.values())


def has_duplicate_projected_rows(rows: list) -> bool:
    seen = set()
    for row in rows:
        signature = row_signature(row)
        if signature in seen:
            return True
        seen.add(signature)
    return False


def build_identity_key(row: dict, identity_columns: list) -> tuple:
    return tuple(normalize_benchmark_value(row.get(column)) for column in identity_columns)


def index_rows_by_identity(rows: list, identity_columns: list) -> tuple[dict, list]:
    indexed = {}
    missing = []
    for row in rows:
        if not isinstance(row, dict):
            missing.extend(column for column in identity_columns if column not in missing)
            continue
        absent = [column for column in identity_columns if column not in row]
        if absent:
            for column in absent:
                if column not in missing:
                    missing.append(column)
            continue
        indexed.setdefault(build_identity_key(row, identity_columns), []).append(row)
    return indexed, missing


def compare_scalar_rows(expected_rows: list, actual_rows: list, required_columns: list) -> tuple[str, list, str]:
    if expected_rows and not actual_rows:
        return "MISMATCH", [{"expected": expected_rows[0], "actual": None}], "Expected data is non-empty, but actual Scan rows are empty."
    if len(expected_rows) != 1 or len(actual_rows) != 1:
        matched, _, _ = tolerant_unordered_row_counts(expected_rows, actual_rows, required_columns)
        return ("PARTIAL" if matched else "MISMATCH"), [], "Scalar comparison could not align one expected row with one actual row."
    expected_row = expected_rows[0]
    actual_row = actual_rows[0]
    wrong = []
    if isinstance(expected_row, dict) and isinstance(actual_row, dict):
        columns = required_columns or list(expected_row.keys())
        for column in columns:
            if column not in actual_row or not benchmark_values_equal(expected_row.get(column), actual_row.get(column)):
                wrong.append({"column": column, "expected": expected_row.get(column), "actual": actual_row.get(column) if isinstance(actual_row, dict) else actual_row})
        return ("MISMATCH" if wrong else "MATCH"), wrong, ("Requested scalar value differs." if wrong else "Requested scalar value matched deterministically.")
    return ("MATCH" if benchmark_values_equal(expected_row, actual_row) else "MISMATCH"), ([] if benchmark_values_equal(expected_row, actual_row) else [{"expected": expected_row, "actual": actual_row}]), "Scalar comparison completed deterministically."


def deterministic_benchmark_status(ground_truth: str, scan_raw_rows: str, grading_contract: dict, column_mapping: dict | None = None) -> dict:
    evidence = {"status": "MISMATCH", "expected_json_valid": False, "actual_json_valid": False, "expected_row_count": 0, "actual_row_count": 0, "required_columns": [], "identity_columns": [], "comparison_mode": "", "order_matters": False, "multiplicity_matters": False, "missing_identity_columns": [], "matched_identity_keys": [], "missing_identity_keys": [], "extra_identity_keys": [], "missing_rows": [], "extra_rows": [], "wrong_required_values": [], "quality_flags": [], "column_mapping_used": column_mapping or {}, "reason": ""}
    expected_ok, expected_raw = parse_benchmark_json_rows(ground_truth)
    actual_ok, actual_raw = parse_benchmark_json_rows(scan_raw_rows)
    evidence["expected_json_valid"] = expected_ok
    evidence["actual_json_valid"] = actual_ok
    if not expected_ok:
        evidence["status"] = "OTHER"
        evidence["reason"] = "Ground truth JSON is invalid."
        return evidence
    if not actual_ok:
        evidence["status"] = "MISMATCH"
        evidence["reason"] = "Ground truth requires structured JSON, but Scan did not return valid JSON."
        return evidence
    evidence["expected_row_count"] = len(expected_raw)
    evidence["actual_row_count"] = len(actual_raw)
    if not expected_raw and not actual_raw:
        evidence["status"] = "MATCH"
        evidence["reason"] = "Both ground truth and Scan output are empty."
        return evidence
    if expected_raw and not actual_raw:
        evidence["status"] = "MISMATCH"
        evidence["reason"] = "Expected data is non-empty, but actual Scan rows are empty."
        return evidence
    required_columns = list(dict.fromkeys((grading_contract or {}).get("required_columns", [])))
    identity_columns = list(dict.fromkeys((grading_contract or {}).get("identity_columns", [])))
    comparison_mode = str((grading_contract or {}).get("comparison_mode", "row_set")).lower().strip()
    if comparison_mode not in {"scalar", "row_set", "grouped", "ordered"}:
        comparison_mode = "row_set"
    order_matters = bool((grading_contract or {}).get("order_matters", comparison_mode == "ordered"))
    multiplicity_matters = bool((grading_contract or {}).get("multiplicity_matters", False))
    evidence.update({"required_columns": required_columns, "identity_columns": identity_columns, "comparison_mode": comparison_mode, "order_matters": order_matters, "multiplicity_matters": multiplicity_matters})
    actual_mapped = apply_column_mapping(actual_raw, column_mapping or {})
    expected_norm = [normalize_benchmark_row(row) for row in expected_raw]
    actual_norm = [normalize_benchmark_row(row) for row in actual_mapped]
    value_columns = [column for column in required_columns if column not in identity_columns]
    compare_columns = list(dict.fromkeys(required_columns + identity_columns))
    expected_projected = [project_row(row, compare_columns) for row in expected_norm]
    actual_projected = [project_row(row, compare_columns) for row in actual_norm]
    if not multiplicity_matters and (has_duplicate_projected_rows(expected_projected) or has_duplicate_projected_rows(actual_projected)):
        evidence["quality_flags"].append("DUPLICATE_ROWS")
    scalar_like = (
        comparison_mode == "scalar"
        or (
            len(expected_projected) == len(actual_projected) == 1
            and not identity_columns
            and len(value_columns or required_columns) <= 1
        )
    )
    if scalar_like:
        status, wrong, reason = compare_scalar_rows(expected_projected, actual_projected, required_columns)
        evidence["status"] = status
        evidence["wrong_required_values"] = wrong
        evidence["reason"] = reason
        return evidence
    if identity_columns:
        expected_by_id, missing_expected_identity = index_rows_by_identity(expected_norm, identity_columns)
        actual_by_id, missing_actual_identity = index_rows_by_identity(actual_norm, identity_columns)
        evidence["missing_identity_columns"] = sorted(set(missing_expected_identity + missing_actual_identity))
        expected_keys = set(expected_by_id)
        actual_keys = set(actual_by_id)
        matched_keys = expected_keys & actual_keys
        evidence["matched_identity_keys"] = [list(key) for key in sorted(matched_keys, key=str)]
        evidence["missing_identity_keys"] = [list(key) for key in sorted(expected_keys - actual_keys, key=str)]
        evidence["extra_identity_keys"] = [list(key) for key in sorted(actual_keys - expected_keys, key=str)]
        wrong_values = []
        matched_rows = 0
        correct_rows = 0
        for key in matched_keys:
            expected_group = expected_by_id[key]
            actual_group = actual_by_id[key]
            pair_count = min(len(expected_group), len(actual_group))
            matched_rows += pair_count
            for index in range(pair_count):
                expected_row = expected_group[index]
                actual_row = actual_group[index]
                row_wrong = False
                for column in value_columns or required_columns:
                    if column in identity_columns:
                        continue
                    if column not in actual_row or not benchmark_values_equal(expected_row.get(column), actual_row.get(column)):
                        row_wrong = True
                        wrong_values.append({"identity": {column: expected_row.get(column) for column in identity_columns}, "column": column, "expected": expected_row.get(column), "actual": actual_row.get(column) if isinstance(actual_row, dict) else None})
                if not row_wrong:
                    correct_rows += 1
            if multiplicity_matters and len(expected_group) != len(actual_group):
                evidence["missing_rows"].extend(row_signature(project_row(row, compare_columns)) for row in expected_group[pair_count:])
                evidence["extra_rows"].extend(row_signature(project_row(row, compare_columns)) for row in actual_group[pair_count:])
        evidence["wrong_required_values"] = wrong_values
        if order_matters and matched_keys == expected_keys == actual_keys:
            expected_sequence = [build_identity_key(row, identity_columns) for row in expected_norm if isinstance(row, dict) and all(column in row for column in identity_columns)]
            actual_sequence = [build_identity_key(row, identity_columns) for row in actual_norm if isinstance(row, dict) and all(column in row for column in identity_columns)]
            if expected_sequence != actual_sequence:
                same_positions = sum(1 for expected_key, actual_key in zip(expected_sequence, actual_sequence) if expected_key == actual_key)
                evidence["status"] = "PARTIAL" if same_positions else "MISMATCH"
                evidence["reason"] = "Required rows are present, but the requested order is wrong."
                return evidence
        if not matched_keys:
            evidence["status"] = "MISMATCH"
            evidence["reason"] = "No required identity values aligned."
        elif evidence["missing_identity_keys"] or evidence["extra_identity_keys"] or evidence["missing_identity_columns"] or wrong_values or evidence["missing_rows"] or evidence["extra_rows"]:
            evidence["status"] = "PARTIAL" if matched_rows or correct_rows else "MISMATCH"
            evidence["reason"] = "Identity alignment found partial overlap, but rows, occurrences, or required values differ."
        else:
            evidence["status"] = "MATCH"
            evidence["reason"] = "All identity-aligned rows and required values matched deterministically."
            if evidence["quality_flags"]:
                evidence["reason"] = "All identity-aligned rows and required values matched deterministically; duplicate rows were ignored."
        return evidence
    if order_matters:
        ordered_exact = (
            len(expected_projected) == len(actual_projected)
            and all(rows_equal_on_columns(expected_row, actual_row, compare_columns) for expected_row, actual_row in zip(expected_projected, actual_projected))
        )
        if ordered_exact:
            evidence["status"] = "MATCH"
            evidence["reason"] = "All ordered projected rows matched deterministically."
            return evidence
        same_positions = sum(1 for expected_row, actual_row in zip(expected_projected, actual_projected) if rows_equal_on_columns(expected_row, actual_row, compare_columns))
        matched_unordered, missing_unordered, extra_unordered = tolerant_unordered_row_counts(expected_projected, actual_projected, compare_columns)
        if not missing_unordered and not extra_unordered and same_positions == 0:
            evidence["status"] = "MISMATCH"
            evidence["reason"] = "Required rows are present, but the explicitly requested order is completely wrong."
        elif same_positions or matched_unordered:
            evidence["status"] = "PARTIAL"
            evidence["reason"] = "Some ordered rows or values match, but the ordered result is incomplete or partly wrong."
        else:
            evidence["status"] = "MISMATCH"
            evidence["reason"] = "Ordered projected rows have no meaningful overlap."
        return evidence
    matched_rows, missing_rows, extra_rows = tolerant_unordered_row_counts(expected_projected, actual_projected, compare_columns)
    evidence["missing_rows"] = sorted(missing_rows)
    evidence["extra_rows"] = sorted(extra_rows)
    if matched_rows == len(expected_projected) == len(actual_projected):
        evidence["status"] = "MATCH"
        evidence["reason"] = "All projected required rows matched deterministically."
        return evidence
    unique_matched, unique_missing, unique_extra = tolerant_unordered_row_counts(
        unique_rows_by_signature(expected_projected),
        unique_rows_by_signature(actual_projected),
        compare_columns,
    )
    if not multiplicity_matters and not unique_missing and not unique_extra:
        evidence["status"] = "MATCH"
        if "DUPLICATE_ROWS" not in evidence["quality_flags"]:
            evidence["quality_flags"].append("DUPLICATE_ROWS")
        evidence["missing_rows"] = []
        evidence["extra_rows"] = []
        evidence["reason"] = "Projected required unique rows matched; harmless duplicate copies were ignored."
    elif matched_rows or unique_matched:
        evidence["status"] = "PARTIAL"
        evidence["reason"] = "Some projected required rows match, but some are missing, extra, or incorrect."
    else:
        evidence["status"] = "MISMATCH"
        evidence["reason"] = "Projected required rows have no meaningful overlap."
    return evidence


def grade_json_result_deterministically(question: str, ground_truth: str, scan_raw_rows: str, client, model: str, schema_context: dict | None = None) -> dict:
    expected_ok, expected_rows = parse_benchmark_json_rows(ground_truth)
    actual_ok, actual_rows = parse_benchmark_json_rows(scan_raw_rows)
    contract = infer_grading_contract(question, ground_truth, client, model)
    mapping_result = {"column_mapping": {}, "is_valid": True, "reason": "All required and identity columns aligned by Python normalization."}
    validated_mapping = {}
    mapping_status = "automatic_column_alignment"
    actual_columns = benchmark_columns_from_rows(actual_rows, canonical=False)
    actual_canonical = {canonical_benchmark_key(column) for column in actual_columns}
    required_or_identity = list(dict.fromkeys(contract.get("required_columns", []) + contract.get("identity_columns", [])))
    unresolved = [column for column in required_or_identity if canonical_benchmark_key(column) not in actual_canonical]
    path = "requirement_llm -> automatic_column_alignment -> deterministic_final"
    if unresolved and actual_columns:
        mapping_result = infer_column_mapping(question, contract, ground_truth, scan_raw_rows, schema_context or {}, client, model)
        allowed_target_columns = list(dict.fromkeys(contract.get("required_columns", []) + contract.get("identity_columns", [])))
        validated_mapping = validate_column_mapping(mapping_result.get("column_mapping", {}), actual_columns, allowed_target_columns)
        mapping_result["validated_column_mapping"] = validated_mapping
        mapping_status = "column_mapper_llm" if validated_mapping else "column_mapper_failed"
        path = "requirement_llm -> column_mapper_llm -> deterministic_final" if validated_mapping else "requirement_llm -> column_mapper_failed -> deterministic_final"
    deterministic = deterministic_benchmark_status(ground_truth, scan_raw_rows, contract, validated_mapping)
    status = deterministic.get("status") if deterministic.get("status") in {"MATCH", "PARTIAL", "MISMATCH"} else "MISMATCH"
    return {"status": status, "reason": deterministic.get("reason", "Deterministic JSON grading result."), "grading_path": path, "grading_contract": contract, "column_mapping": mapping_result, "column_mapping_status": mapping_status, "deterministic_status": status, "deterministic_evidence": deterministic}


def grade_pipeline_result(question: str, ground_truth: str, scan_raw_rows: str, final_output: str, client, model: str, schema_context: dict | None = None) -> dict:
    ground_truth_format = detect_ground_truth_format(ground_truth)
    scan_json_valid, _ = parse_benchmark_json_rows(scan_raw_rows)
    if ground_truth_format == "json" and scan_json_valid:
        return grade_json_result_deterministically(question, ground_truth, scan_raw_rows, client, model, schema_context)
    if ground_truth_format == "json":
        contract = infer_grading_contract(question, ground_truth, client, model)
        return {"status": "MISMATCH", "reason": "Ground truth is valid JSON, but Scan Raw Rows is invalid or empty.", "grading_path": "scan_json_invalid", "grading_contract": contract, "column_mapping": {}, "column_mapping_status": "not_applicable", "deterministic_status": "MISMATCH", "deterministic_evidence": {"expected_json_valid": True, "actual_json_valid": False, "grading_contract_inferred_for_analysis": True}}
    if ground_truth_format == "invalid_json":
        return {"status": "OTHER", "reason": "Ground truth appears to be JSON but is invalid or truncated.", "grading_path": "invalid_ground_truth_json", "grading_contract": {}, "column_mapping": {}, "column_mapping_status": "not_applicable", "deterministic_status": "NOT_APPLICABLE", "deterministic_evidence": {}}
    return {"status": "OTHER", "reason": "Ground truth is not JSON; deterministic JSON grading is not applicable.", "grading_path": "non_json_ground_truth", "grading_contract": {}, "column_mapping": {}, "column_mapping_status": "not_applicable", "deterministic_status": "NOT_APPLICABLE", "deterministic_evidence": {}}


def regrade_existing_report(input_csv: str, output_csv: str, client, model: str = LLM_GRADER_MODEL) -> str:
    df = pd.read_csv(input_csv)
    rows = []
    preserve_statuses = {"CRASH", "SCAN_ERROR", "PRE_SCAN_ERROR", "QUOTA_EXHAUSTED"}
    completed_statuses = preserve_statuses | {"MATCH", "PARTIAL", "MISMATCH", "OTHER"}
    existing_rows = []
    if os.path.exists(output_csv):
        try:
            existing_rows = pd.read_csv(output_csv).to_dict(orient="records")
            print(f"[RESUME] Found existing graded report with {len(existing_rows)} row(s).")
        except Exception as exc:
            print(f"[WARN] Could not read existing graded report for resume: {exc}")
            existing_rows = []

    total_rows = len(df)

    def save_progress() -> None:
        pd.DataFrame(rows).to_csv(output_csv, index=False)

    for idx, row in df.iterrows():
        row_number = idx + 1
        if idx < len(existing_rows):
            existing_row = existing_rows[idx]
            existing_graded_status = str(existing_row.get("New Status", "") or "").strip().upper()
            existing_path = str(existing_row.get("Final Grading Path", "") or "").strip()
            if existing_graded_status in completed_statuses and (existing_path or existing_graded_status in preserve_statuses):
                rows.append(existing_row)
                print(f"[GRADE] {row_number}/{total_rows}: resumed {existing_graded_status}", flush=True)
                continue

        updated = row.to_dict()
        existing_status = str(row.get("New Status", "") or "").strip().upper()
        if existing_status in preserve_statuses:
            updated["Final Grading Path"] = "preserved_execution_status"
            rows.append(updated)
            save_progress()
            print(f"[GRADE] {row_number}/{total_rows}: preserved {existing_status}", flush=True)
            continue

        try:
            result = grade_pipeline_result(str(row.get("Question", "") or ""), str(row.get("Ground Truth", "") or ""), str(row.get("Scan Raw Rows", "") or ""), str(row.get("New Pipeline Result", "") or ""), client, model)
            updated.update({"New Status": result.get("status", "OTHER"), "Comparison / Comments": result.get("reason", ""), "Grading Contract": json.dumps(result.get("grading_contract", {}), ensure_ascii=False, default=str), "Column Mapping": json.dumps(result.get("column_mapping", {}), ensure_ascii=False, default=str), "Column Mapping Status": result.get("column_mapping_status", "not_applicable"), "Deterministic Preliminary Status": result.get("deterministic_status", "NOT_APPLICABLE"), "Deterministic Evidence": json.dumps(result.get("deterministic_evidence", {}), ensure_ascii=False, default=str), "Final Grading Path": result.get("grading_path", "")})
        except Exception as exc:
            updated.update({"New Status": "OTHER", "Comparison / Comments": f"Grader exception: {exc}", "Grading Contract": "{}", "Column Mapping": "{}", "Column Mapping Status": "grader_exception", "Deterministic Preliminary Status": "NOT_APPLICABLE", "Deterministic Evidence": "{}", "Final Grading Path": "grader_exception"})
        rows.append(updated)
        save_progress()
        print(f"[GRADE] {row_number}/{total_rows}: {updated.get('New Status', 'OTHER')}", flush=True)

    save_progress()
    return output_csv



def main():
    print("\n" + "=" * 50)
    print("INITIALIZING SEPARATE GPT-OSS 120B DETERMINISTIC GRADER CHECK")
    print("=" * 50)
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    if not os.path.exists(RAW_REPORT_FILE):
        raise FileNotFoundError(f"Raw pipeline report not found: {RAW_REPORT_FILE}")
    grader_client = build_gpt_oss_client()
    print(f"[SYSTEM] Raw report: {RAW_REPORT_FILE}")
    print(f"[SYSTEM] Graded report: {REPORT_FILE}")
    print(f"[SYSTEM] Grader model: {LLM_GRADER_MODEL}")
    regrade_existing_report(RAW_REPORT_FILE, REPORT_FILE, grader_client, LLM_GRADER_MODEL)
    api_logger.save()
    print(f"[SUCCESS] Graded report saved to {REPORT_FILE}")


if __name__ == "__main__":
    main()
