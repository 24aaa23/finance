"""Check result structure; optionally review answer meaning without gating execution."""

import os

from ..common import (
    Any,
    DETERMINISTIC_EXPLAIN,
    Dict,
    LOCAL_MODEL,
    api_logger,
    json,
    re,
)
from ..clients import build_llm_messages, supports_temperature
from ..business_context import business_context_prompt
from ..utils import parse_llm_json


def empty_answer_can_be_valid(query: str, query_spec: Dict[str, Any]) -> bool:
    """Compatibility hint only; emptiness still requires successful execution evidence."""
    return isinstance(query_spec, dict) and query_spec.get("allow_empty_result") is True


def _norm_group_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "", str(value or "").replace("-", "_").lower())


def query_spec_requires_null_group_guard(query_spec: Dict[str, Any]) -> bool:
    return isinstance(query_spec, dict) and query_spec.get("preserve_null_groups") is True and bool(query_spec.get("group_by"))


def sparql_has_null_group_guard(sparql: str) -> bool:
    text = str(sparql or "").lower()
    return "optional" in text


def normalize_value_for_final_answer(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_value_for_final_answer(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value_for_final_answer(item) for item in value]
    # Actual nulls stay null. A literal category named "NONE" or "NULL" must not
    # be reinterpreted without an explicit source conversion policy.
    return value


def is_list_query(query: str) -> bool:
    q = str(query or "").lower()
    return any(marker in q for marker in ["which", "show", "list", "identify", "find"])


def is_count_query(query: str) -> bool:
    q = str(query or "").lower()
    return any(marker in q for marker in [
        "count",
        "how many",
        "number of",
        "total number",
        "frequency",
    ])


def clean_rows_for_final_answer(raw_data: list, query: str) -> list:
    cleaned = []
    for row in raw_data:
        cleaned.append(normalize_value_for_final_answer(row))
    return cleaned


def should_return_structured_json(query: str, raw_data: Any) -> bool:
    if not DETERMINISTIC_EXPLAIN or not isinstance(raw_data, list):
        return False
    if len(raw_data) == 0:
        return False

    if all(isinstance(row, dict) for row in raw_data):
        return True

    row_count = len(raw_data)
    list_output = is_list_query(query)
    table_output = row_count > 1
    return list_output or table_output


def _execution_errors(inputs: Dict[str, Any]) -> list[str]:
    """Read execution metadata, never mistake a data column named 'error' for failure."""
    errors = []
    for key in ("error", "error_message", "execution_errors"):
        value = inputs.get(key)
        if value:
            errors.extend(str(item) for item in value) if isinstance(value, list) else errors.append(str(value))
    for key in ("final_execution", "processing_execution", "operator_execution"):
        for entry in inputs.get(key, []) if isinstance(inputs.get(key, []), list) else []:
            if not isinstance(entry, dict):
                continue
            reason = entry.get("error") or entry.get("error_message")
            if reason or entry.get("status") in {"error", "failed"}:
                errors.append(f"{entry.get('operator', key)}: {reason or 'execution failed'}")
    return list(dict.fromkeys(errors))


def _validation_failure(data: Any, reason: str, repair_stage: str = "Final_Spec") -> Dict[str, Any]:
    return {"validation": {"is_valid": False, "reason": reason, "repair_stage": repair_stage}, "data": data}


def semantic_validate(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    data = inputs.get("data", [])
    errors = _execution_errors(inputs)
    final_spec = inputs.get("final_spec") or {}
    errors.extend(str(error) for error in final_spec.get("contract_errors", []))
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        errors.append("Final data must be a list of structured rows.")
    if not errors:
        projection = final_spec.get("projection", [])
        projection = [projection] if isinstance(projection, str) else projection
        missing = sorted({field for field in projection for row in data if field not in row})
        if missing:
            errors.append("Final data lacks declared projection fields: " + ", ".join(missing))
    if errors:
        return {"validation": {"is_valid": False, "status": "execution_error",
                "reason": "; ".join(errors), "repair_stage": "Execution"}, "data": data}

    enabled = inputs.get("semantic_review", os.getenv("FINAL_SEMANTIC_REVIEW", "0"))
    enabled = enabled is True or str(enabled).strip().lower() in {"1", "true", "yes"}
    if not enabled:
        return {"validation": {"is_valid": None, "status": "not_requested",
                "reason": "Execution checks passed. Answer correctness has not been reviewed; use the separate grader."}, "data": data}

    return {"validation": {"is_valid": None, "status": "disabled_by_prompt_policy",
            "reason": "Execution checks passed. Model review of result rows is disabled by the schema-only prompt policy."}, "data": data}
