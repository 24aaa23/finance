"""Shared normalization and contract checks for spec-driven execution.

These functions are deliberately schema-driven: they never inspect domain table names or
question keywords to choose a field.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


LIST_FIELDS = {
    "inputs", "group_by", "join_key", "projection", "entity_grain",
    "fields", "optional_fields", "entity_key", "output_schema",
}


def flatten_identifiers(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in flatten_identifiers(child)]
    return []


def normalize_spec(spec: Any) -> dict:
    """Return a JSON-safe spec with every identifier-list flattened once."""
    if not isinstance(spec, dict):
        return {}
    normalized = deepcopy(spec)

    def walk(value: Any) -> Any:
        if isinstance(value, list):
            return [walk(item) for item in value]
        if not isinstance(value, dict):
            return value
        for key, item in list(value.items()):
            if key == "input":
                # ``input`` identifies one predecessor in the usual case. Preserve that
                # scalar contract while still repairing malformed nested one-item arrays.
                identifiers = flatten_identifiers(item)
                value[key] = identifiers[0] if len(identifiers) == 1 else identifiers
            elif key in LIST_FIELDS:
                value[key] = flatten_identifiers(item)
            elif key == "final_measures" and isinstance(item, list):
                value[key] = [walk(measure) for measure in item if isinstance(measure, dict)]
            else:
                value[key] = walk(item)
        return value

    return walk(normalized)


def schema_columns(schema: dict, class_name: Any) -> set[str]:
    details = schema.get(str(class_name), {}) if isinstance(schema, dict) else {}
    columns = details.get("columns", []) if isinstance(details, dict) else []
    return {
        str(column.get("name")) if isinstance(column, dict) else str(column)
        for column in columns
        if (isinstance(column, dict) and column.get("name")) or isinstance(column, str)
    }


def _canonical(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _is_relation_label_alias(field: str, columns: set[str]) -> bool:
    """Permit a standard human-label alias only when its object relation exists."""
    canonical = _canonical(field)
    if not canonical.endswith("label"):
        return False
    base = canonical[:-5]
    return any(_canonical(column).removeprefix("has") == base for column in columns)


def validate_query_spec_contract(spec: Any, schema: dict) -> list[str]:
    spec = normalize_spec(spec)
    retrieval_specs = spec.get("retrieval_specs", [])
    if len(retrieval_specs) != 1 or not isinstance(retrieval_specs[0], dict):
        return ["Query_Spec must contain exactly one retrieval_spec."]
    retrieval = retrieval_specs[0]
    class_name = retrieval.get("class")
    if not class_name or str(class_name) not in schema:
        return [f"Query_Spec source class is not schema-valid: {class_name}"]
    columns = schema_columns(schema, class_name)
    errors = []
    selected = flatten_identifiers(retrieval.get("fields"))
    for key in ("entity_key", "optional_fields"):
        for field in flatten_identifiers(retrieval.get(key)):
            if field not in selected:
                errors.append(f"Query_Spec {key} field is not selected: {field}")
    for field in selected:
        if field not in columns and not _is_relation_label_alias(field, columns):
            errors.append(f"Query_Spec field is not on {class_name}: {field}")
    for filter_spec in retrieval.get("filters", []):
        if isinstance(filter_spec, dict) and str(filter_spec.get("field") or "") not in columns:
            errors.append(f"Query_Spec filter field is not on {class_name}: {filter_spec.get('field')}")
    # The legacy Query_Spec serializer always emits an informational
    # ``merge_plan`` object (normally ``{"required": false, ...}``).  That
    # metadata is harmless; only a requested merge is computation.
    forbidden = ("operator_plan", "final_measures", "final_steps")
    has_computation = any(spec.get(key) for key in forbidden)
    merge_plan = spec.get("merge_plan")
    if isinstance(merge_plan, dict):
        has_computation = has_computation or bool(merge_plan.get("required"))
    elif merge_plan:
        has_computation = True
    if has_computation:
        errors.append("Query_Spec contains computation instructions; retrieval contracts may only fetch raw fields.")
    return errors


def validate_step_contract(step: dict, available_fields: set[str], available_datasets: set[str]) -> list[str]:
    errors = []
    inputs = flatten_identifiers(step.get("inputs", step.get("input", "raw")))
    for input_id in inputs:
        if input_id not in {"raw", "previous"} and input_id not in available_datasets:
            errors.append(f"step input dataset does not exist: {input_id}")
    for key in ("group_by", "join_key"):
        for field in flatten_identifiers(step.get(key)):
            if field not in available_fields:
                errors.append(f"{key} field does not exist: {field}")
    for key in ("target_column", "column", "input_column", "left_column", "right_column"):
        field = step.get(key)
        if isinstance(field, str) and field and field not in available_fields:
            errors.append(f"{key} field does not exist: {field}")
    return errors
