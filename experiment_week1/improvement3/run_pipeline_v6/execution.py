"""Execute compiled relational specs and preserve failures as structured evidence."""
from __future__ import annotations

import math

from .spec_runtime import compile_spec


def row_schema(rows, declared=None):
    fields = list(declared or [])
    for row in rows:
        if isinstance(row, dict):
            fields.extend(field for field in row if field not in fields)
    return fields


def execution_errors(log):
    return [item for item in log if isinstance(item, dict) and (item.get("error") or item.get("code"))]


def _json_value(value):
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "item"):
        return _json_value(value.item())
    return value


def execute_spec(spec, datasets, registry, query="", dataset_schemas=None):
    """Use exactly the compiler's inputs/order/schema; never guess a fallback table."""
    available = {name: rows for name, rows in datasets.items() if isinstance(rows, list)}
    declared = dataset_schemas or {}
    schemas = {name: row_schema(rows, declared.get(name)) for name, rows in available.items()}
    try:
        compiled = compile_spec(spec, schemas)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return [], [{"stage": "Spec_Execution", "code": "MALFORMED_SPEC", "error": str(exc)}]
    log = []
    if compiled.get("contract_errors"):
        return [], [{"stage": "Spec_Execution", "code": "SPEC_CONTRACT_ERROR", "error": str(error)}
                    for error in compiled["contract_errors"]]
    schemas.update(compiled.get("dataset_schemas", {}))
    for step in compiled.get("execution_steps", []):
        operator = step.get("operator")
        output_id = step.get("output") or step.get("id")
        ids = step.get("inputs", [])
        missing = [name for name in ids if name not in available]
        if missing:
            return [], log + [{"stage": "Spec_Execution", "step": output_id,
                              "code": "MISSING_INPUT_DATASET", "error": str(missing)}]
        selected = [available[name] for name in ids]
        step_inputs = {**step, "query": query, "original_query": query,
                       "strict_spec": True, "strict_aggregation": True,
                       "input_schema": schemas.get(ids[0], []) if ids else [],
                       "branch_schemas": [schemas.get(name, []) for name in ids]}
        try:
            if operator == "Distinct":
                from .relational import _freeze
                keys = step.get("distinct_on") or step_inputs["input_schema"]
                rows, seen = [], set()
                for row in selected[0]:
                    key = tuple(_freeze(row.get(field)) for field in keys)
                    if key not in seen:
                        rows.append(row)
                        seen.add(key)
                result = {"data": rows}
            elif operator == "Combine_Scalars":
                if not selected or not all(len(rows) == 1 and isinstance(rows[0], dict) for rows in selected):
                    raise ValueError("Combine_Scalars requires one row from each declared input.")
                row = {}
                for rows in selected:
                    overlap = row.keys() & rows[0].keys()
                    if overlap:
                        raise ValueError("Scalar measures have duplicate output columns: " + ", ".join(sorted(overlap)))
                    row.update(rows[0])
                result = {"data": [row]}
            else:
                if operator not in registry:
                    raise ValueError(f"Unsupported operator: {operator}")
                if operator in {"Integrate", "Set_Intersect", "Set_Union", "Set_Difference", "Union", "Difference"}:
                    step_inputs["branch_data_lists"] = selected
                    if selected:
                        step_inputs["list_a"] = selected[0]
                    if len(selected) > 1:
                        step_inputs["list_b"] = selected[1]
                else:
                    if len(selected) != 1:
                        raise ValueError(f"{operator} requires exactly one input dataset.")
                    step_inputs["data"] = selected[0]
                result = registry[operator](step_inputs)
            if not isinstance(result, dict):
                raise ValueError("Operator did not return an object.")
            if result.get("error") or result.get("error_message"):
                raise ValueError(str(result.get("error") or result.get("error_message")))
            rows = result.get("data")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Operator must return a list of row objects in data.")
            expected = schemas.get(output_id, [])
            actual = row_schema(rows)
            absent = set(expected) - set(actual) if rows else set()
            if absent:
                raise ValueError("Operator output omitted compiled columns: " + ", ".join(sorted(absent)))
            available[output_id] = _json_value(rows)
            log.append({"id": output_id, "operator": operator, "inputs": ids,
                        "row_count": len(rows), "output_schema": expected})
        except Exception as exc:
            log.append({"stage": "Spec_Execution", "step": output_id, "operator": operator,
                        "code": "OPERATOR_ERROR", "error": str(exc), "exception_type": type(exc).__name__})
            return [], log
    final_id = compiled.get("compiled_output")
    if final_id not in available:
        return [], log + [{"stage": "Spec_Execution", "code": "MISSING_FINAL_DATASET", "error": str(final_id)}]
    data = available[final_id]
    # output_schema is descriptive metadata, not an implicit projection operation.
    # Dropping columns here would disagree with the compiler's downstream schema.
    projection = compiled.get("projection") or []
    if projection:
        data = [{field: row.get(field) for field in projection} for row in data]
    rounding = compiled.get("rounding")
    if rounding is not None:
        if not isinstance(rounding, (int, dict)) or isinstance(rounding, bool):
            return [], log + [{"stage": "Spec_Execution", "code": "INVALID_ROUNDING", "error": "rounding must be an integer, column map, or null."}]
        data = [{field: round(value, rounding.get(field)) if isinstance(rounding, dict) and isinstance(rounding.get(field), int) and isinstance(value, float)
                 else round(value, rounding) if isinstance(rounding, int) and isinstance(value, float)
                 else value for field, value in row.items()} for row in data]
    return _json_value(data), log
