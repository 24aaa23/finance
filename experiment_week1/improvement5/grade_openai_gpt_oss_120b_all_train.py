import datetime
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any, Dict

import pandas as pd
from openai import OpenAI as LLMClient


def load_local_env_file() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_env_file = os.path.join(script_dir, ".env")
    env_candidates = [
        local_env_file,
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
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if env_file == local_env_file and key in {"OPENAI_API_KEY", "OPENAI_BASE_URL"}:
                    os.environ[key] = value
                else:
                    os.environ.setdefault(key, value)


load_local_env_file()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIFF_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
OUTPUT_DIR = os.getenv("PIPELINE_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "output"))
DEFAULT_GPT_OSS_MODEL = "openai.gpt-oss-120b-1:0"
GPT_OSS_MODEL = os.getenv("BEDROCK_GPT_OSS_MODEL", DEFAULT_GPT_OSS_MODEL)
DEFAULT_LLM_GRADER_MODEL = "gpt-5.6-sol"
LLM_GRADER_MODEL = os.getenv("LLM_GRADER_MODEL", DEFAULT_LLM_GRADER_MODEL)
DETERMINISTIC_EXPLAIN = os.getenv("DETERMINISTIC_EXPLAIN", "1").strip().lower() not in {"0", "false", "no"}
REPORT_FILE = os.getenv("GRADED_REPORT_FILE", os.path.join(OUTPUT_DIR, "graded_openai_gpt_oss_120b_all_train.csv"))
RAW_REPORT_FILE = os.getenv("RAW_REPORT_FILE", os.path.join(OUTPUT_DIR, "raw_pipeline_openai_gpt_oss_120b_all_train.csv"))
GRADER_POLICY_VERSION = "deterministic-v2-validated-helpers"
with open(__file__, "rb") as _grader_source:
    GRADER_CODE_SHA256 = hashlib.sha256(_grader_source.read()).hexdigest()


@contextmanager
def atomic_output(path: str):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".grader-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


@contextmanager
def report_lock(path: str):
    lock_path = os.path.abspath(path) + ".lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(
            f"Report is locked: {lock_path}. Stop its other grader first. "
            "If a previous process was forcibly terminated, remove its stale lock only after confirming it stopped."
        ) from None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid()}, handle)
        yield
    finally:
        os.remove(lock_path)


class APILogger:
    def __init__(self):
        self.lock = threading.Lock()
        self.query_logs = {}
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.log_file = os.path.join(OUTPUT_DIR, f"api_usage_log_{timestamp}_{os.getpid()}_{uuid.uuid4().hex[:8]}.json")

    def log_call(self, query, function_name):
        with self.lock:
            q_key = query if query else "Unknown_Query"
            if q_key not in self.query_logs:
                self.query_logs[q_key] = {"total_calls": 0, "functions": {}}

            self.query_logs[q_key]["total_calls"] += 1
            self.query_logs[q_key]["functions"][function_name] = self.query_logs[q_key]["functions"].get(function_name, 0) + 1

    def save(self):
        with self.lock:
            with atomic_output(self.log_file) as f:
                json.dump(self.query_logs, f, indent=4)

api_logger = APILogger()


class GraderAPIError(RuntimeError):
    def __init__(self, stage: str, cause: Exception):
        self.stage = stage
        status_code = getattr(cause, "status_code", None)
        self.authentication_failed = status_code in {401, 403} or type(cause).__name__ in {
            "AuthenticationError", "PermissionDeniedError"
        }
        # Do not put credential-bearing API exception bodies into reports.
        detail = f"HTTP {status_code}" if status_code is not None else type(cause).__name__
        super().__init__(f"{stage} failed ({detail}); no answer grade was assigned.")


class GraderOutputError(RuntimeError):
    pass


def call_grader_helper(question: str, stage: str, prompt: str, client, model: str) -> str:
    api_logger.log_call(question, stage)
    request = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if supports_temperature(model):
        request["temperature"] = 0.0
    try:
        response = client.chat.completions.create(**request)
    except Exception as exc:
        raise GraderAPIError(stage, exc) from None
    if not response.choices or response.choices[0].finish_reason in {"length", "content_filter"}:
        raise GraderOutputError(f"{stage} returned no complete answer.")
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise GraderOutputError(f"{stage} returned empty output.")
    return content


SECRET_PLACEHOLDER_PREFIXES = (
    "your_", "your-", "yourkey", "changeme", "change_me", "replace_me",
    "replaceme", "placeholder", "todo", "xxx", "<",
)


def is_placeholder_secret(value: Any) -> bool:
    """True when an env var holds a template stand-in rather than a credential.

    A placeholder is truthy, so it sails through a plain `if not api_key` check
    and then fails on every single API call. That turns a missing credential
    into a silently degraded run instead of a stopped one, so it is worth
    catching before any work starts.
    """
    text = str(value or "").strip().strip('"').strip("'").lower()
    if not text:
        return True
    return text.startswith(SECRET_PLACEHOLDER_PREFIXES) or text in {"none", "null"}


def require_secret(env_names: list, purpose: str) -> str:
    """Return the first real credential among env_names, or say exactly what to fix."""
    placeholders = []
    for name in env_names:
        value = os.getenv(name)
        if value is None:
            continue
        if is_placeholder_secret(value):
            placeholders.append(name)
            continue
        return value
    if placeholders:
        raise RuntimeError(
            f"{' and '.join(placeholders)} is set to a placeholder, not a real credential. "
            f"{purpose} Put a real value in your .env or export it before running the grader. "
            "Refusing to start: a placeholder key would fail every API call and silently "
            "downgrade grading rather than stopping it."
        )
    raise RuntimeError(
        f"None of {env_names} is set. {purpose}"
    )


def build_gpt_oss_client():
    api_key = require_secret(
        ["AWS_BEDROCK_API_KEY", "AWS_Bedrock_API_gpt_oss_120b", "BEDROCK_API_KEY"],
        "AWS_BEDROCK_API_KEY is required for the GPT-OSS 120B Bedrock endpoint.",
    )
    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError("BEDROCK_REGION is required for the GPT-OSS 120B Bedrock endpoint.")
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"
    return LLMClient(api_key=api_key, base_url=base_url)


def build_openai_grader_client():
    api_key = require_secret(
        ["OPENAI_API_KEY"],
        f"OPENAI_API_KEY is required for the {LLM_GRADER_MODEL} deterministic grader helper calls "
        "(requirement analysis and column mapping); it is separate from the Bedrock key the pipeline uses.",
    )
    base_url = os.getenv("OPENAI_BASE_URL")
    # Ask for uncompressed responses. The bundled httpx2 brotli decoder calls
    # Decompressor.process(data, output_buffer_limit=...), a keyword the
    # installed brotli 1.0.9 does not accept, so every brotli-compressed reply
    # dies in decoding and surfaces as a misleading APIConnectionError. Bedrock
    # does not negotiate brotli, which is why only this client is affected.
    # Remove once brotli >= 1.1.0 is installed.
    client_kwargs = {"api_key": api_key, "default_headers": {"Accept-Encoding": "identity"}}
    if base_url:
        client_kwargs["base_url"] = base_url
    return LLMClient(**client_kwargs)


def supports_temperature(model: str) -> bool:
    return not str(model or "").lower().startswith("gpt-5")


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
    "avg_goal_progress_pct": "avg_progress_pct",
    "avg_goal_progress": "avg_progress_pct",
    "goal_progress_pct": "goal_progress",
    "investment_name": "investment_name",
    "investment_type": "investment_type",
    "investor_id": "investor_id",
    "investor_name": "investor_name",
    "holding_id": "holding_id",
    "goal_id": "goal_id",
    "cash_flow_type": "type",
    "cashflow_type": "type",
    "cash_flow_source": "source",
    "goal_match_pct_band": "goal_match_band",
    "avg_goal_match": "avg_goal_match_pct",
    "avg_volatility": "avg_volatility_pct",
    "avg_diversification": "avg_diversification_score",
    "avg_liquidity": "avg_liquidity_score",
    "total_goal_shortfall": "total_shortfall",
    "total_rebalancing_amount": "total_rebalance_amount",
    "rebalancing_amount_total": "total_rebalance_amount",
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


def is_metric_like_column(column: str) -> bool:
    column = canonical_benchmark_key(column)
    metric_prefixes = (
        "avg_",
        "total_",
        "count",
        "sum_",
        "min_",
        "max_",
        "net_",
        "rank",
    )
    metric_exact = {
        "current_value",
        "amount",
        "shortfall",
        "risk_score",
        "liquidity_score",
        "diversification_score",
        "goal_match_pct",
        "returns_pct",
        "allocation_pct",
        "holding_gain",
        "transaction_count",
        "net_amount",
    }
    return column.startswith(metric_prefixes) or column in metric_exact


MEASURE_UNIT_SUFFIXES = ("pct", "score", "amount", "value", "sum", "total", "count", "ratio", "num")

MEASURE_WORD_VARIANTS = {
    "rebalancing": "rebalance",
    "cashflow": "cash_flow",
    "goal_progress": "progress",
    "holding_gain": "gain",
    "transactions": "transaction",
    "investors": "investor",
    "holdings": "holding",
    "goals": "goal",
}


def benchmark_key_stem(column: str) -> str:
    """Collapse harmless naming variance so equivalent metric columns compare equal.

    Pipeline aliases and benchmark aliases routinely differ only by a trailing
    unit word or a gerund - `avg_scenario_change_pct` vs `avg_scenario_change`,
    `avg_rebalancing_amount` vs `avg_rebalance_amount`. Those are the same
    measure, so alignment should not depend on the LLM column mapper being
    reachable to notice it.
    """
    key = canonical_benchmark_key(column)
    for source, target in MEASURE_WORD_VARIANTS.items():
        key = key.replace(source, target)
    parts = [part for part in key.split("_") if part]
    while len(parts) > 2 and parts[-1] in MEASURE_UNIT_SUFFIXES:
        parts.pop()
    return "_".join(parts)


def infer_heuristic_column_mapping(contract: dict, actual_columns: list) -> dict[str, str]:
    required_or_identity = list(dict.fromkeys(contract.get("required_columns", []) + contract.get("identity_columns", [])))
    actual_by_canonical: dict[str, list[str]] = {}
    for column in actual_columns:
        actual_by_canonical.setdefault(canonical_benchmark_key(column), []).append(str(column))

    heuristic_mapping: dict[str, str] = {}
    for target in required_or_identity:
        canonical_target = canonical_benchmark_key(target)
        if canonical_target in actual_by_canonical:
            continue

        if canonical_target == "group_value":
            candidates = [
                column for column in actual_columns
                if not is_metric_like_column(column)
                and not canonical_benchmark_key(column).endswith("_id")
            ]
            if len(candidates) == 1:
                heuristic_mapping[str(candidates[0])] = str(target)
            continue

        alias_candidates = {
            "allocation_record_count": {"record_count"},
            "negative_holding_count": {"holding_count"},
            "type": {"cash_flow_type"},
            "source": {"cash_flow_source"},
            "goal_match_band": {"goal_match_pct_band"},
            "avg_progress_pct": {"avg_goal_progress", "avg_goal_progress_pct"},
            "avg_goal_match_pct": {"avg_goal_match"},
            "avg_volatility_pct": {"avg_volatility"},
            "avg_diversification_score": {"avg_diversification"},
            "avg_liquidity_score": {"avg_liquidity"},
            "total_shortfall": {"total_goal_shortfall"},
            "total_rebalance_amount": {"total_rebalancing_amount", "rebalancing_amount_total"},
        }.get(canonical_target, set())

        resolved = [
            source
            for alias in alias_candidates
            for source in actual_by_canonical.get(alias, [])
        ]
        if len(resolved) == 1 and resolved[0] not in heuristic_mapping and canonical_benchmark_key(resolved[0]) not in {
            canonical_benchmark_key(other) for other in required_or_identity if other != target
        }:
            heuristic_mapping[str(resolved[0])] = str(target)
            continue

        # Fall back to stem equality, but only when exactly one actual column
        # matches and it is not already claimed by another target. A stem tie is
        # left unresolved rather than guessed.
        target_stem = benchmark_key_stem(target)
        claimed = set(heuristic_mapping)
        stem_matches = [
            str(column) for column in actual_columns
            if str(column) not in claimed
            and canonical_benchmark_key(column) not in
            {canonical_benchmark_key(other) for other in required_or_identity if other != target}
            and benchmark_key_stem(column) == target_stem
        ]
        if len(stem_matches) == 1:
            heuristic_mapping[stem_matches[0]] = str(target)

    return heuristic_mapping


def benchmark_decimal(value: Any):
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = Decimal(text.replace(",", ""))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def benchmark_decimal_precision(value: Any) -> int:
    number = benchmark_decimal(value)
    return max(0, -number.as_tuple().exponent) if number is not None else 0


def benchmark_values_equal(expected_value, actual_value) -> bool:
    if isinstance(expected_value, bool) or isinstance(actual_value, bool):
        return type(expected_value) is type(actual_value) and expected_value == actual_value
    expected_decimal = benchmark_decimal(expected_value)
    actual_decimal = benchmark_decimal(actual_value)
    if expected_decimal is not None and actual_decimal is not None:
        precision = benchmark_decimal_precision(expected_value)
        if precision == 0 or expected_decimal == expected_decimal.to_integral_value():
            return expected_decimal == actual_decimal
        quantizer = Decimal("1").scaleb(-precision)
        with localcontext() as context:
            context.prec = max(28, expected_decimal.adjusted() + precision + 2, actual_decimal.adjusted() + precision + 2)
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


def unwrap_benchmark_payload(parsed: Any) -> tuple[list, dict]:
    metadata = {
        "wrapped_rows": False,
        "truncated": False,
        "included_rows": None,
        "total_rows": None,
        "wrapper_keys": [],
    }
    if isinstance(parsed, list):
        return parsed, metadata
    if isinstance(parsed, dict):
        if isinstance(parsed.get("rows"), list):
            metadata["wrapped_rows"] = True
            metadata["wrapper_keys"] = sorted(parsed.keys())
            metadata["included_rows"] = parsed.get("_included_rows")
            metadata["total_rows"] = parsed.get("_total_rows")
            try:
                included = int(parsed.get("_included_rows"))
                total = int(parsed.get("_total_rows"))
                metadata["truncated"] = included < total
            except Exception:
                metadata["truncated"] = False
            return parsed["rows"], metadata
        if isinstance(parsed.get("data"), list):
            metadata["wrapped_rows"] = True
            metadata["wrapper_keys"] = sorted(parsed.keys())
            return parsed["data"], metadata
        return [parsed], metadata
    return [parsed], metadata


def parse_benchmark_json_payload(raw_text: str) -> tuple[bool, list, dict]:
    try:
        parsed = extract_json_candidate(raw_text)
    except Exception:
        return False, [], {
            "wrapped_rows": False,
            "truncated": False,
            "included_rows": None,
            "total_rows": None,
            "wrapper_keys": [],
        }
    rows, metadata = unwrap_benchmark_payload(parsed)
    return True, rows, metadata


def parse_benchmark_json_rows(raw_text: str) -> tuple[bool, list]:
    ok, rows, _ = parse_benchmark_json_payload(raw_text)
    return ok, rows


def local_identifier(value: str) -> str:
    text = str(value or "").strip()
    if re.match(r"https?://", text):
        text = re.split(r"[/#]", text.rstrip("/#"))[-1]
    return text


def normalize_benchmark_value(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(normalize_benchmark_value(item) for item in value)
    if isinstance(value, dict):
        return tuple(
            (
                canonical_benchmark_key(key),
                normalize_benchmark_value(nested_value),
            )
            for key, nested_value in sorted(value.items(), key=lambda item: str(item[0]))
        )
    if isinstance(value, str):
        text = local_identifier(value).strip()
        if re.fullmatch(r"[A-Za-z]+[-_ ]?\d+", text):
            return re.sub(r"[^a-z0-9]+", "", text.lower())
        number = benchmark_decimal(text)
        if number is not None:
            return number
        return normalize_for_compare(text)
    return value


def normalize_benchmark_row(row: Any) -> Any:
    if not isinstance(row, dict):
        return normalize_benchmark_value(row)
    return {canonical_benchmark_key(key): normalize_benchmark_value(value) for key, value in row.items()}


def benchmark_rows_from_text(raw_text: str, limit: int | None = None) -> list:
    ok, rows, _ = parse_benchmark_json_payload(raw_text)
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
    if not isinstance(contract, dict):
        raise GraderOutputError("Requirement analyzer did not return a JSON object.")
    corrected = dict(contract)
    for field in ("required_columns", "identity_columns"):
        values = contract.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise GraderOutputError(f"Requirement analyzer returned invalid {field}.")
        columns = list(dict.fromkeys(canonical_benchmark_key(value) for value in values))
        if set(columns) - set(available_columns):
            raise GraderOutputError(f"Requirement analyzer invented columns in {field}.")
        corrected[field] = columns
    if available_columns and not corrected["required_columns"]:
        raise GraderOutputError("Requirement analyzer selected no required answer columns.")
    if set(corrected["identity_columns"]) - set(corrected["required_columns"]):
        raise GraderOutputError("Identity columns must also be required answer columns.")
    if contract.get("comparison_mode") not in {"scalar", "row_set", "grouped", "ordered"}:
        raise GraderOutputError("Requirement analyzer returned an invalid comparison mode.")
    if contract["comparison_mode"] == "grouped" and not corrected["identity_columns"]:
        raise GraderOutputError("Grouped comparison requires explicit group identity columns.")
    for field in ("order_matters", "multiplicity_matters"):
        if type(contract.get(field)) is not bool:
            raise GraderOutputError(f"Requirement analyzer returned a non-boolean {field}.")
    if contract["comparison_mode"] == "ordered" and not contract["order_matters"]:
        raise GraderOutputError("Ordered comparison must enable order_matters.")
    return corrected


def infer_grading_contract(question: str, ground_truth: str, client, model: str) -> dict:
    ok, expected_rows, _ = parse_benchmark_json_payload(ground_truth)
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
- When an entity ID alone unambiguously answers "which entities", require that ID, not an additional name or descriptive attribute unless the question explicitly requests it.
- Do not include threshold/filter columns unless the question asks to return their values.
- If the question asks "above/below/equal/missing/with/without" using a column, that column is usually filter-only.
- For "for each", "across", "by", "per", or "within each" questions, use the group column as identity_columns.
- For multiple grouping dimensions, include the complete grouping tuple in identity_columns.
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
Answer: {{"required_columns":["investor_id"],"identity_columns":["investor_id"],"comparison_mode":"row_set","order_matters":false,"multiplicity_matters":false}}

Question: For each cash-flow type, what is the transaction count and net amount?
Columns: ["type","transaction_count","net_amount"]
Answer: {{"required_columns":["type","transaction_count","net_amount"],"identity_columns":["type"],"comparison_mode":"grouped","order_matters":false,"multiplicity_matters":false}}

Question: How do average goal_match_pct and average risk_score compare by time_horizon?
Columns: ["time_horizon","avg_goal_match_pct","avg_risk_score"]
Answer: {{"required_columns":["time_horizon","avg_goal_match_pct","avg_risk_score"],"identity_columns":["time_horizon"],"comparison_mode":"grouped","order_matters":false,"multiplicity_matters":false}}



Question: Which investors have total current holding value above 10000000?
Columns: ["investor_id","investor_name","total_current_value"]
Answer: {{"required_columns":["investor_id"],"identity_columns":["investor_id"],"comparison_mode":"row_set","order_matters":false,"multiplicity_matters":false}}

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
    raw_content = call_grader_helper(question, "Requirement_Analyzer", prompt, client, model)
    parsed = parse_llm_json(raw_content, None, "Requirement_Analyzer")
    return verify_grading_contract_columns(question, expected_rows, parsed, available_columns)


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
            return dict(candidates[-1])
        parsed = parse_llm_json(without_reasoning or text, None, stage)
        return parsed if isinstance(parsed, dict) else None

    def call_column_mapper(mapper_prompt: str, stage: str) -> tuple[dict | None, str]:
        raw = call_grader_helper(question, stage, mapper_prompt, client, model)
        return extract_column_mapping_json(raw, stage), raw

    parsed, raw_content = call_column_mapper(prompt, "Column_Mapper")
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

Map all possible available columns. Partial mapping is allowed.
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
        parsed, retry_raw_content = call_column_mapper(retry_prompt, "Column_Mapper_Retry")
        mapping = parsed.get("column_mapping") if isinstance(parsed, dict) else None
        attempts = 2
    if not isinstance(parsed, dict) or not isinstance(parsed.get("column_mapping"), dict) or is_placeholder_mapping(mapping):
        raise GraderOutputError("Column mapper returned no valid mapping object.")
    validate_column_mapping(mapping, actual_columns, ground_truth_columns)
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
    if not isinstance(column_mapping, dict) or any(
        not isinstance(source, str) or not isinstance(target, str) for source, target in column_mapping.items()
    ):
        raise GraderOutputError("Column mapping must contain string column names only.")
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
            raise GraderOutputError("Column mapper referenced a nonexistent source or target column.")
        canonical_target = canonical_benchmark_key(resolved_target)
        canonical_source = canonical_benchmark_key(resolved_source)
        if canonical_target in actual_canonical_set and canonical_source != canonical_target:
            raise GraderOutputError("Column mapping would replace an already present answer column.")
        if canonical_target in used_targets:
            raise GraderOutputError("Multiple answer columns were mapped to the same reference column.")
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
    expected_ok, expected_raw, expected_meta = parse_benchmark_json_payload(ground_truth)
    actual_ok, actual_raw, _ = parse_benchmark_json_payload(scan_raw_rows)
    evidence["expected_json_valid"] = expected_ok
    evidence["actual_json_valid"] = actual_ok
    if not expected_ok:
        evidence["status"] = "OTHER"
        evidence["reason"] = "Ground truth JSON is invalid."
        return evidence
    if expected_meta.get("truncated"):
        evidence["status"] = "OTHER"
        evidence["reason"] = (
            "Ground truth JSON is a truncated wrapper payload; deterministic grading is not reliable."
        )
        evidence["quality_flags"].append("TRUNCATED_GROUND_TRUTH")
        evidence["expected_row_count"] = len(expected_raw)
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
    expected_ok, expected_rows, expected_meta = parse_benchmark_json_payload(ground_truth)
    actual_ok, actual_rows, _ = parse_benchmark_json_payload(scan_raw_rows)
    if expected_ok and expected_meta.get("truncated"):
        return {
            "status": "OTHER",
            "reason": "Ground truth is a truncated wrapper payload; deterministic grading is not reliable.",
            "grading_path": "truncated_ground_truth_wrapper",
            "grading_contract": {},
            "column_mapping": {},
            "column_mapping_status": "not_applicable",
            "deterministic_status": "NOT_APPLICABLE",
            "deterministic_evidence": {
                "expected_json_valid": True,
                "actual_json_valid": actual_ok,
                "truncated_ground_truth": True,
                "expected_row_count": len(expected_rows),
                "included_rows": expected_meta.get("included_rows"),
                "total_rows": expected_meta.get("total_rows"),
            },
        }
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
        heuristic_mapping = infer_heuristic_column_mapping(contract, actual_columns)
        validated_mapping = validate_column_mapping(heuristic_mapping, actual_columns, required_or_identity)
        resolved_targets = {canonical_benchmark_key(target) for target in validated_mapping.values()}
        remaining = [column for column in unresolved if canonical_benchmark_key(column) not in resolved_targets]
        if validated_mapping and not remaining:
            mapping_result = {
                "column_mapping": heuristic_mapping,
                "validated_column_mapping": validated_mapping,
                "is_valid": True,
                "llm_attempts": 0,
                "reason": "Heuristic column alignment resolved missing required or identity columns.",
            }
            mapping_status = "heuristic_column_alignment"
            path = "requirement_llm -> heuristic_column_alignment -> deterministic_final"
            unresolved = []
    if unresolved and actual_columns:
        mapping_result = infer_column_mapping(question, contract, ground_truth, scan_raw_rows, schema_context or {}, client, model)
        allowed_target_columns = list(dict.fromkeys(contract.get("required_columns", []) + contract.get("identity_columns", [])))
        helper_mapping = validate_column_mapping(mapping_result.get("column_mapping", {}), actual_columns, allowed_target_columns)
        for source, target in helper_mapping.items():
            if source in validated_mapping and validated_mapping[source] != target:
                raise GraderOutputError("Helper mapping conflicts with a verified column alias.")
        validated_mapping = validate_column_mapping({**validated_mapping, **helper_mapping}, actual_columns, allowed_target_columns)
        mapping_result["validated_column_mapping"] = validated_mapping
        mapping_status = "column_mapper_llm" if validated_mapping else "column_mapping_unresolved"
        path = f"requirement_llm -> {mapping_status} -> deterministic_final"
    deterministic = deterministic_benchmark_status(ground_truth, scan_raw_rows, contract, validated_mapping)
    status = deterministic.get("status") if deterministic.get("status") in {"MATCH", "PARTIAL", "MISMATCH"} else "MISMATCH"
    return {"status": status, "reason": deterministic.get("reason", "Deterministic JSON grading result."), "grading_path": path, "grading_contract": contract, "column_mapping": mapping_result, "column_mapping_status": mapping_status, "deterministic_status": status, "deterministic_evidence": deterministic}


def grade_pipeline_result(question: str, ground_truth: str, scan_raw_rows: str, final_output: str, client, model: str, schema_context: dict | None = None) -> dict:
    ground_truth_format = detect_ground_truth_format(ground_truth)
    scan_json_valid, _, _ = parse_benchmark_json_payload(scan_raw_rows)
    ground_truth_ok, _, ground_truth_meta = parse_benchmark_json_payload(ground_truth)
    if ground_truth_ok and ground_truth_meta.get("truncated"):
        return {
            "status": "OTHER",
            "reason": "Ground truth is a truncated wrapper payload; deterministic grading is not reliable.",
            "grading_path": "truncated_ground_truth_wrapper",
            "grading_contract": {},
            "column_mapping": {},
            "column_mapping_status": "not_applicable",
            "deterministic_status": "NOT_APPLICABLE",
            "deterministic_evidence": {
                "expected_json_valid": True,
                "actual_json_valid": scan_json_valid,
                "truncated_ground_truth": True,
                "included_rows": ground_truth_meta.get("included_rows"),
                "total_rows": ground_truth_meta.get("total_rows"),
            },
        }
    if ground_truth_format == "json" and scan_json_valid:
        return grade_json_result_deterministically(question, ground_truth, scan_raw_rows, client, model, schema_context)
    if ground_truth_format == "json":
        contract = infer_grading_contract(question, ground_truth, client, model)
        return {"status": "MISMATCH", "reason": "Ground truth is valid JSON, but Scan Raw Rows is invalid or empty.", "grading_path": "scan_json_invalid", "grading_contract": contract, "column_mapping": {}, "column_mapping_status": "not_applicable", "deterministic_status": "MISMATCH", "deterministic_evidence": {"expected_json_valid": True, "actual_json_valid": False, "grading_contract_inferred_for_analysis": True}}
    if ground_truth_format == "invalid_json":
        return {"status": "OTHER", "reason": "Ground truth appears to be JSON but is invalid or truncated.", "grading_path": "invalid_ground_truth_json", "grading_contract": {}, "column_mapping": {}, "column_mapping_status": "not_applicable", "deterministic_status": "NOT_APPLICABLE", "deterministic_evidence": {}}
    return {"status": "OTHER", "reason": "Ground truth is not JSON; deterministic JSON grading is not applicable.", "grading_path": "non_json_ground_truth", "grading_contract": {}, "column_mapping": {}, "column_mapping_status": "not_applicable", "deterministic_status": "NOT_APPLICABLE", "deterministic_evidence": {}}


def grading_fingerprint(row: dict, answer_column: str, model: str, endpoint: str) -> str:
    payload = {
        "question_id": row["Sample Row ID"], "question": row["Question"],
        "ground_truth": row["Ground Truth"], "answer": row[answer_column],
        "execution_status": row.get("New Status", ""), "answer_column": answer_column,
        "model": model, "endpoint": endpoint, "policy": GRADER_POLICY_VERSION,
        "code": GRADER_CODE_SHA256,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def regrade_existing_report(input_csv: str, output_csv: str, client, model: str = LLM_GRADER_MODEL) -> str:
    if os.path.normcase(os.path.realpath(input_csv)) == os.path.normcase(os.path.realpath(output_csv)):
        raise ValueError("Input and graded output must be different files.")
    with report_lock(output_csv):
        return _regrade_existing_report(input_csv, output_csv, client, model)


def _regrade_existing_report(input_csv: str, output_csv: str, client, model: str) -> str:
    df = pd.read_csv(input_csv, dtype=str, keep_default_na=False)
    answer_column = "New Pipeline Result" if "New Pipeline Result" in df.columns else "Scan Raw Rows"
    missing_columns = {"Sample Row ID", "Question", "Ground Truth", answer_column} - set(df.columns)
    if missing_columns:
        raise ValueError(f"Input report is missing required columns: {sorted(missing_columns)}")
    if df["Sample Row ID"].str.strip().eq("").any() or df["Sample Row ID"].duplicated().any():
        raise ValueError("Input report must have nonempty, unique Sample Row ID values.")
    source_rows = df.to_dict(orient="records")
    endpoint = str(getattr(client, "base_url", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")))
    fingerprints = {row["Sample Row ID"]: grading_fingerprint(row, answer_column, model, endpoint) for row in source_rows}
    preserve_statuses = {"CRASH", "SCAN_ERROR", "PRE_SCAN_ERROR", "QUOTA_EXHAUSTED", "TRANSIENT_ERROR", "QUERY_SPEC_ERROR", "FINAL_SPEC_ERROR"}
    completed_statuses = preserve_statuses | {"MATCH", "PARTIAL", "MISMATCH", "OTHER"}
    rows_by_id = {}
    if os.path.exists(output_csv):
        existing_df = pd.read_csv(output_csv, dtype=str, keep_default_na=False)
        if "Sample Row ID" in existing_df.columns:
            if existing_df["Sample Row ID"].duplicated().any():
                raise ValueError("Existing graded report contains duplicate Sample Row ID values; use a fresh output file.")
            for row in existing_df.to_dict(orient="records"):
                row_id = row["Sample Row ID"]
                if (row_id in fingerprints and row.get("Grading Input Hash") == fingerprints[row_id]
                        and row.get("New Status") in completed_statuses
                        and row.get("Final Grading Path") not in {None, "", "grader_exception"}):
                    rows_by_id[row_id] = row
        print(f"[RESUME] Reusing {len(rows_by_id)} verified rows; stale, unversioned, or failed grades will be retried.")

    def save_progress() -> None:
        saved = [rows_by_id[row["Sample Row ID"]] for row in source_rows if row["Sample Row ID"] in rows_by_id]
        with atomic_output(output_csv) as handle:
            pd.DataFrame(saved, columns=None if saved else list(df.columns)).to_csv(handle, index=False)

    for row_number, row in enumerate(source_rows, 1):
        row_id = row["Sample Row ID"]
        if row_id in rows_by_id:
            print(f"[GRADE] {row_number}/{len(source_rows)}: resumed {rows_by_id[row_id]['New Status']}", flush=True)
            continue
        updated = dict(row)
        updated.update({"Grading Input Hash": fingerprints[row_id], "Grader Policy Version": GRADER_POLICY_VERSION,
                        "Grader Code SHA256": GRADER_CODE_SHA256, "Grader Model": model})
        stop_error = None
        execution_status = row.get("New Status", "").strip().upper()
        if execution_status in preserve_statuses:
            updated["New Status"] = execution_status
            updated["Final Grading Path"] = "preserved_execution_status"
        else:
            try:
                result = grade_pipeline_result(row["Question"], row["Ground Truth"], row[answer_column], row.get("New Pipeline Result", ""), client, model)
                updated.update({"New Status": result.get("status", "OTHER"), "Comparison / Comments": result.get("reason", ""), "Grading Contract": json.dumps(result.get("grading_contract", {}), ensure_ascii=False, default=str), "Column Mapping": json.dumps(result.get("column_mapping", {}), ensure_ascii=False, default=str), "Column Mapping Status": result.get("column_mapping_status", "not_applicable"), "Deterministic Preliminary Status": result.get("deterministic_status", "NOT_APPLICABLE"), "Deterministic Evidence": json.dumps(result.get("deterministic_evidence", {}), ensure_ascii=False, default=str), "Final Grading Path": result.get("grading_path", "")})
            except Exception as exc:
                if isinstance(exc, GraderAPIError):
                    error_status = "GRADER_AUTH_ERROR" if exc.authentication_failed else "GRADER_API_ERROR"
                    if exc.authentication_failed:
                        stop_error = exc
                else:
                    error_status = "GRADER_OUTPUT_ERROR" if isinstance(exc, GraderOutputError) else "GRADER_ERROR"
                reason = str(exc) if isinstance(exc, (GraderAPIError, GraderOutputError)) else f"Internal grader failure: {type(exc).__name__}"
                updated.update({"New Status": error_status, "Comparison / Comments": reason, "Grading Contract": "{}", "Column Mapping": "{}", "Column Mapping Status": "grader_exception", "Deterministic Preliminary Status": "NOT_APPLICABLE", "Deterministic Evidence": "{}", "Final Grading Path": "grader_exception"})
        rows_by_id[row_id] = updated
        save_progress()
        print(f"[GRADE] {row_number}/{len(source_rows)}: {updated['New Status']}", flush=True)
        if stop_error is not None:
            raise RuntimeError(f"{stop_error} Run stopped; progress saved to {output_csv}. Fix credentials/access before resuming.") from None

    save_progress()
    return output_csv



def main():
    print("\n" + "=" * 50)
    print("INITIALIZING SEPARATE GPT-5.6 SOL DETERMINISTIC GRADER")
    print("=" * 50)
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    if not os.path.exists(RAW_REPORT_FILE):
        raise FileNotFoundError(f"Raw pipeline report not found: {RAW_REPORT_FILE}")
    grader_client = build_openai_grader_client()
    print(f"[SYSTEM] Raw report: {RAW_REPORT_FILE}")
    print(f"[SYSTEM] Graded report: {REPORT_FILE}")
    print(f"[SYSTEM] Grader model: {LLM_GRADER_MODEL}")
    try:
        regrade_existing_report(RAW_REPORT_FILE, REPORT_FILE, grader_client, LLM_GRADER_MODEL)
    finally:
        api_logger.save()
    print(f"[SUCCESS] Graded report saved to {REPORT_FILE}")


if __name__ == "__main__":
    main()
