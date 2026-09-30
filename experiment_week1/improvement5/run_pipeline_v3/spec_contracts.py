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
    "fields", "optional_fields", "entity_key", "output_schema", "final_group_by",
    "left_on", "right_on", "distinct_on", "output_columns",
}

_STEP_OPERATORS = {
    re.sub(r"[^a-z0-9]", "", name.lower()): name for name in (
        "Integrate", "Set_Intersect", "Set_Union", "Set_Difference", "Union",
        "Difference", "Combine_Scalars", "Filter_Aggregate", "Math_Compute",
        "Date_Extract", "Bucket", "Order_By", "Distinct", "Copy",
    )
}
_AGGREGATE_NAMES = {"sum", "avg", "average", "mean", "count", "count_rows", "count_distinct", "nunique", "min", "max"}


def boolean_flag(value: Any, name: str) -> bool:
    """Accept actual booleans and their explicit JSON-text spellings only."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError(f"{name} must be a boolean (true or false).")


def _identifier_list(value: Any) -> list[str]:
    """Normalize exact identifier declarations without dropping malformed items."""
    if value is None:
        return []
    if isinstance(value, bool):
        raise ValueError("a boolean is not a field or dataset identifier")
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _identifier_list(child)]
    if isinstance(value, dict) and len(value) == 1:
        key, identifier = next(iter(value.items()))
        if key in {"column", "field", "name", "id", "dataset"} and isinstance(identifier, str) and identifier.strip():
            return [identifier.strip()]
    raise ValueError("expected names or single-field objects such as {'column': 'field_name'}")


def _normalize_step(step: Any, errors: list[str]) -> Any:
    """Accept documented JSON spelling variants without inferring a query plan.

    This only visits operation declarations, never filter predicates whose
    ``operator`` has a different meaning (for example ``>=``).
    """
    if not isinstance(step, dict):
        return step
    step = deepcopy(step)

    def alias(target: str, *alternatives: str, identifiers: bool = False) -> None:
        for source in alternatives:
            if source not in step:
                continue
            value = step.pop(source)
            if target not in step:
                step[target] = value
            elif (flatten_identifiers(step[target]) if identifiers else step[target]) != (flatten_identifiers(value) if identifiers else value):
                errors.append(f"Conflicting step fields: {target} and {source}.")

    def operator_name(value: Any) -> str | None:
        return _STEP_OPERATORS.get(re.sub(r"[^a-z0-9]", "", str(value or "").lower()))

    if "operator" in step:
        step["operator"] = operator_name(step["operator"]) or step["operator"]
    elif operator_name(step.get("type")):
        step["operator"] = operator_name(step.pop("type"))
    elif operator_name(step.get("operation")):
        step["operator"] = operator_name(step.pop("operation"))
    elif str(step.get("operation", "")).lower() in _AGGREGATE_NAMES | {"filter", "where"}:
        step["operator"] = "Filter_Aggregate"

    alias("id", "step_id", identifiers=True)
    alias("input", "input_dataset", "input_branch", "input_source", identifiers=True)
    alias("inputs", "input_datasets", identifiers=True)
    alias("output", "output_dataset", "output_branch", identifiers=True)
    alias("left", "left_branch", "left_source", "left_dataset", identifiers=True)
    alias("right", "right_branch", "right_source", "right_dataset", identifiers=True)
    if "left" in step or "right" in step:
        pair = flatten_identifiers(step.pop("left", None)) + flatten_identifiers(step.pop("right", None))
        if "inputs" not in step:
            step["inputs"] = pair
        elif flatten_identifiers(step["inputs"]) != pair:
            errors.append("Conflicting step fields: inputs and left/right datasets.")
    if "input" in step and "inputs" in step:
        if flatten_identifiers(step["input"]) != flatten_identifiers(step["inputs"]):
            errors.append("Conflicting step fields: input and inputs.")
        step.pop("input")
    alias("join_key", "on", identifiers=True)
    # An explicit equality is a pair of names, not a column literally containing '='.
    keys = flatten_identifiers(step.get("join_key"))
    pairs = [re.fullmatch(r"\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*", key) for key in keys]
    if keys and all(pairs) and not step.get("left_on") and not step.get("right_on"):
        step["left_on"] = [pair.group(1) for pair in pairs]
        step["right_on"] = [pair.group(2) for pair in pairs]
        step.pop("join_key")
    alias("left_on", "left_key", identifiers=True)
    alias("right_on", "right_key", identifiers=True)
    if step.get("operator") == "Integrate" and str(step.get("type", "")).lower() in {"inner", "left", "right", "outer", "cross"}:
        alias("join_type", "type")
    if step.get("operator") == "Integrate":
        join_type = str(step.get("join_type") or step.get("how") or "inner").lower().replace(" ", "_")
        step["join_type"] = {"left_outer": "left", "right_outer": "right", "full_outer": "outer", "full": "outer"}.get(join_type, join_type)
        left, right = flatten_identifiers(step.get("left_on")), flatten_identifiers(step.get("right_on"))
        if len(flatten_identifiers(step.get("inputs"))) > 2 and left and left == right:
            if step.get("join_key") and flatten_identifiers(step["join_key"]) != left:
                errors.append("Conflicting step fields: join_key and left_on/right_on.")
            else:
                step["join_key"] = left
                step.pop("left_on")
                step.pop("right_on")
    if step.get("operator") == "Math_Compute" and isinstance(step.get("expressions"), list) and len(step["expressions"]) == 1:
        expression = step["expressions"][0]
        if isinstance(expression, dict):
            for key, value in expression.items():
                if key in step and step[key] != value:
                    errors.append(f"Conflicting step field and expressions entry: {key}.")
                else:
                    step[key] = value
            step.pop("expressions")
    alias("filters", "filter")
    if isinstance(step.get("filters"), dict):
        step["filters"] = [step["filters"]]
    alias("aggregations", "aggregates")
    # Seen in actual model plans: operation describes the step kind, while agg
    # or agg_operation supplies its exact calculation. Do not guess a function.
    if str(step.get("operation", "")).lower() in {"aggregate", "aggregation"}:
        explicit = [step[key] for key in ("agg", "agg_operation", "aggregation_function", "aggregation", "function") if key in step]
        if explicit:
            step.pop("operation")
    alias("operation", "agg", "agg_operation", "aggregation_function")
    alias("operation", "aggregation", "function")
    if "operation" in step and isinstance(step["operation"], str):
        step["operation"] = step["operation"].lower()
    if not step.get("operator") and step.get("operation") in _AGGREGATE_NAMES:
        step["operator"] = "Filter_Aggregate"
    if step.get("operator") == "Filter_Aggregate" and not step.get("operation") and not step.get("aggregations") and "filters" in step:
        step["operation"] = "filter"
    if (step.get("operator") == "Filter_Aggregate" and step.get("operation") in {"filter", "where"}
            and step.get("aggregations") == []):
        step.pop("aggregations")
    if isinstance(step.get("aggregations"), list):
        step["aggregations"] = [_normalize_step(item, errors) for item in step["aggregations"]]
    boolean_fields = {"distinct", "nulls_equal", "preserve_null_groups"}
    if step.get("operator") in {"Set_Union", "Union"}:
        boolean_fields.add("all")
    for field in boolean_fields:
        if field in step:
            try:
                step[field] = boolean_flag(step[field], field)
            except ValueError as exc:
                errors.append(str(exc))
    return step


def flatten_identifiers(value: Any) -> list[str]:
    try:
        return _identifier_list(value)
    except ValueError:
        return []


def normalize_spec(spec: Any) -> dict:
    """Return a JSON-safe spec with every identifier-list flattened once."""
    if not isinstance(spec, dict):
        return {}
    normalized = deepcopy(spec)
    errors = list(normalized.get("normalization_errors") or [])
    for key in ("steps", "merge_steps", "pre_steps", "final_measures", "final_steps"):
        if isinstance(normalized.get(key), list):
            normalized[key] = [_normalize_step(step, errors) for step in normalized[key]]
    for field in ("distinct", "preserve_null_groups"):
        if field in normalized:
            try:
                normalized[field] = boolean_flag(normalized[field], field)
            except ValueError as exc:
                errors.append(str(exc))

    def walk(value: Any) -> Any:
        if isinstance(value, list):
            return [walk(item) for item in value]
        if not isinstance(value, dict):
            return value
        for key, item in list(value.items()):
            if key == "input" or key in LIST_FIELDS:
                try:
                    identifiers = _identifier_list(item)
                except ValueError as exc:
                    errors.append(f"Invalid {key}: {exc}.")
                    identifiers = []
            if key == "input":
                # ``input`` identifies one predecessor in the usual case. Preserve that
                # scalar contract while still repairing malformed nested one-item arrays.
                value[key] = identifiers[0] if len(identifiers) == 1 else identifiers
            elif key in LIST_FIELDS:
                value[key] = identifiers
            else:
                value[key] = walk(item)
        return value

    normalized = walk(normalized)
    if errors:
        normalized["normalization_errors"] = list(dict.fromkeys(errors))
    return normalized


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
    if not selected:
        errors.append("Query_Spec requires at least one selected field.")
    if not flatten_identifiers(retrieval.get("entity_key")):
        errors.append("Query_Spec requires an explicit source entity_key to preserve observation identity.")
    for key in ("entity_key", "optional_fields"):
        for field in flatten_identifiers(retrieval.get(key)):
            if field not in selected:
                errors.append(f"Query_Spec {key} field is not selected: {field}")
    for field in selected:
        if field not in columns and not _is_relation_label_alias(field, columns):
            errors.append(f"Query_Spec field is not on {class_name}: {field}")
    filters = retrieval.get("filters", [])
    if not isinstance(filters, list):
        errors.append("Query_Spec filters must be a list.")
        filters = []
    def check_filter(filter_spec):
        if not isinstance(filter_spec, dict):
            errors.append("Query_Spec filter must be an object.")
            return
        for key in ("all", "any", "not", "conditions", "filters"):
            if key in filter_spec:
                children = [filter_spec[key]] if key == "not" else filter_spec[key]
                if not isinstance(children, list) or not children:
                    errors.append("Logical filters require nonempty predicates.")
                else:
                    for child in children:
                        check_filter(child)
                return
        if str(filter_spec.get("field") or "") not in columns:
            errors.append(f"Query_Spec filter field is not on {class_name}: {filter_spec.get('field')}")
    for filter_spec in filters:
        check_filter(filter_spec)
    if not errors:
        from .raw_query import render_raw_query
        try:
            render_raw_query(retrieval, schema)
        except (ValueError, TypeError) as exc:
            errors.append("Invalid raw retrieval: " + str(exc))
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
