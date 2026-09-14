"""Deterministic relational operations for explicit specs, without model fallbacks.

Empty inputs are real relations. Joins preserve multiplicity, composite keys and
SQL null inequality; set operations use explicit keys and configurable distinctness.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from .spec_contracts import boolean_flag


def _null(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


def _freeze(value):
    if _null(value):
        return None
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _names(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return list(value)
    raise ValueError("Keys must be a column name or a list of column names.")


def _datasets(inputs):
    datasets = inputs.get("branch_data_lists")
    if datasets is None:
        datasets = [inputs.get("list_a", []), inputs.get("list_b", [])]
    if not isinstance(datasets, list) or len(datasets) < 2:
        raise ValueError("A relational operation requires at least two input datasets.")
    if any(not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows) for rows in datasets):
        raise ValueError("Each dataset must be a list of row objects.")
    supplied_schemas = inputs.get("branch_schemas", [])
    schemas = []
    for i, rows in enumerate(datasets):
        fields = list(supplied_schemas[i]) if i < len(supplied_schemas) else []
        for row in rows:
            fields.extend(field for field in row if field not in fields)
        schemas.append(fields)
    return datasets, schemas


def _require_keys(keys, fields):
    missing = [key for key in keys if fields and key not in fields]
    if missing:
        raise ValueError("Declared join keys are absent from an input: " + ", ".join(missing))


def _key(row, keys, nulls_equal):
    values = tuple(_freeze(row.get(key)) for key in keys)
    return None if not nulls_equal and any(item is None for item in values) else values


def join_column_maps(left_fields, right_fields, left_keys, right_keys, suffixes=("", "_right")):
    """Resolve join column names identically for the compiler and execution.

    Keep unchanged fields first. If a suffix already belongs to an earlier join
    or input field, allocate the next available numbered name without overwriting
    any values (for example subject_iri_right_2).
    """
    if not isinstance(suffixes, (list, tuple)) or len(suffixes) != 2 or not all(isinstance(s, str) for s in suffixes):
        raise ValueError("suffixes must contain two strings.")
    shared_keys = {left for left, right in zip(left_keys, right_keys)
                   if left == right and left in left_fields and right in right_fields}
    overlaps = set(left_fields).intersection(right_fields) - shared_keys
    entries = [("left", field, field + suffixes[0] if field in overlaps else field) for field in left_fields]
    entries += [("right", field, field + suffixes[1] if field in overlaps else field)
                for field in right_fields if field not in shared_keys]
    # Reserve unsuffixed names before assigning generated names. Thus a real
    # input column named label_right remains addressable after joining label.
    reserved = {field for _, field, desired in entries if desired == field}
    used, maps, output_fields = set(), {"left": {}, "right": {}}, []
    for side, field, desired in entries:
        candidate, number = desired, 2
        while candidate in used or (candidate in reserved and candidate != field):
            candidate = f"{desired}_{number}"
            number += 1
        maps[side][field] = candidate
        used.add(candidate)
        output_fields.append(candidate)
    for field in shared_keys:
        maps["right"][field] = maps["left"][field]
    return maps["left"], maps["right"], output_fields


def integrate(inputs):
    """Join all declared branches in order; never drop an empty branch or dedup facts."""
    try:
        datasets, schemas = _datasets(inputs)
        how = str(inputs.get("join_type") or inputs.get("how") or "inner").lower()
        how = {"full": "outer", "full_outer": "outer", "left_outer": "left", "right_outer": "right"}.get(how, how)
        if how not in {"inner", "left", "right", "outer", "cross"}:
            raise ValueError(f"Unsupported join_type: {how}")
        left_keys = _names(inputs.get("left_on") or inputs.get("join_key"))
        right_keys = _names(inputs.get("right_on") or inputs.get("join_key"))
        if how != "cross" and (not left_keys or len(left_keys) != len(right_keys)):
            raise ValueError("Join requires explicit join_key or equal-length left_on/right_on keys.")
        if how == "cross":
            left_keys, right_keys = [], []
        nulls_equal = boolean_flag(inputs.get("nulls_equal", False), "nulls_equal")
        suffixes = inputs.get("suffixes", ["", "_right"])
        if not isinstance(suffixes, (list, tuple)) or len(suffixes) != 2 or not all(isinstance(s, str) for s in suffixes):
            raise ValueError("suffixes must contain two strings.")
        limit = int(inputs.get("max_output_rows", 1_000_000))
        if limit < 1:
            raise ValueError("max_output_rows must be positive.")
        rows, fields = datasets[0], schemas[0]
        for right_rows, right_fields in zip(datasets[1:], schemas[1:]):
            _require_keys(left_keys, fields)
            _require_keys(right_keys, right_fields)
            shared_keys = {a for a, b in zip(left_keys, right_keys) if a == b}
            left_map, right_map, output_fields = join_column_maps(fields, right_fields, left_keys, right_keys, suffixes)

            def merge(left, right):
                output = {name: None for name in output_fields}
                if left is not None:
                    output.update({left_map[f]: None if _null(left.get(f)) else left.get(f) for f in fields})
                if right is not None:
                    for field in right_fields:
                        if field in shared_keys and left is not None:
                            continue
                        value = right.get(field)
                        output[right_map[field]] = None if _null(value) else value
                return output

            index = defaultdict(list)
            for position, right in enumerate(right_rows):
                key = _key(right, right_keys, nulls_equal)
                if key is not None:
                    index[key].append((position, right))
            cardinality = inputs.get("cardinality") or inputs.get("validate")
            if cardinality:
                cardinality = {"1:1": "one_to_one", "1:m": "one_to_many", "m:1": "many_to_one", "m:m": "many_to_many"}.get(cardinality, cardinality)
                if cardinality not in {"one_to_one", "one_to_many", "many_to_one", "many_to_many"}:
                    raise ValueError("Unsupported join cardinality.")
                counts = Counter(key for row in rows if (key := _key(row, left_keys, nulls_equal)) is not None)
                if cardinality in {"one_to_one", "one_to_many"} and any(n > 1 for n in counts.values()):
                    raise ValueError("Left input violates declared unique join keys.")
                if cardinality in {"one_to_one", "many_to_one"} and any(len(items) > 1 for items in index.values()):
                    raise ValueError("Right input violates declared unique join keys.")
            output, matched = [], set()
            for left in rows:
                key = _key(left, left_keys, nulls_equal)
                matches = index.get(key, []) if key is not None else []
                if len(output) + len(matches) > limit:
                    raise ValueError("Join exceeds max_output_rows; no rows were silently discarded.")
                for position, right in matches:
                    output.append(merge(left, right))
                    matched.add(position)
                if not matches and how in {"left", "outer"}:
                    output.append(merge(left, None))
            if how in {"right", "outer"}:
                output.extend(merge(None, right) for pos, right in enumerate(right_rows) if pos not in matched)
            if len(output) > limit:
                raise ValueError("Join exceeds max_output_rows; no rows were silently discarded.")
            rows, fields = output, output_fields
        return {"data": rows, "row_count": len(rows), "output_schema": fields}
    except (ValueError, TypeError, OverflowError) as exc:
        return {"data": [], "error": str(exc)}


def set_operation(inputs, operation):
    """Keyed set operations retain a representative source row in source order."""
    try:
        datasets, schemas = _datasets(inputs)
        keys = _names(inputs.get("join_key") or inputs.get("key") or inputs.get("join_keys"))
        left_keys = _names(inputs.get("left_on"))
        right_keys = _names(inputs.get("right_on"))
        if left_keys or right_keys:
            if len(datasets) != 2 or not left_keys or len(left_keys) != len(right_keys):
                raise ValueError("Set left_on/right_on requires two inputs and equal-length key lists.")
            keys = left_keys
        is_union = operation in {"Set_Union", "Union"}
        if not keys:
            if not is_union:
                raise ValueError("Intersection and difference require explicit join keys.")
            keys = list(dict.fromkeys(field for fields in schemas for field in fields))
        else:
            for index, fields in enumerate(schemas):
                _require_keys(right_keys if index == 1 and right_keys else keys, fields)
        nulls_equal = boolean_flag(inputs.get("nulls_equal", True), "nulls_equal")
        indexed = [{_key(row, right_keys if index == 1 and right_keys else keys, nulls_equal) for row in rows}
                   for index, rows in enumerate(datasets)]
        if not nulls_equal:
            indexed = [values - {None} for values in indexed]
        if operation == "Set_Intersect":
            wanted = set.intersection(*indexed)
            candidates = [(row, keys) for row in datasets[0]]
        elif operation in {"Set_Difference", "Difference"}:
            wanted = indexed[0] - set.union(*indexed[1:])
            candidates = [(row, keys) for row in datasets[0]]
        elif is_union:
            wanted = set.union(*indexed)
            candidates = [(row, right_keys if index == 1 and right_keys else keys)
                          for index, rows in enumerate(datasets) for row in rows]
        else:
            raise ValueError(f"Unknown set operator: {operation}")
        union_all = is_union and (boolean_flag(inputs.get("all", False), "all") or
                                 not boolean_flag(inputs.get("distinct", True), "distinct"))
        keep_duplicates = union_all or (not is_union and not boolean_flag(inputs.get("distinct", True), "distinct"))
        result, seen = [], set()
        for row, candidate_keys in candidates:
            key = _key(row, candidate_keys, nulls_equal)
            # SQL NOT EXISTS with '=' retains a null-key left row: it cannot
            # match a right row. Explicit nulls_equal:true retains set semantics.
            unmatched_null = operation in {"Set_Difference", "Difference"} and not nulls_equal and key is None
            if (key in wanted or union_all or unmatched_null) and (keep_duplicates or key not in seen):
                result.append(dict(row))
                seen.add(key)
        fields = list(dict.fromkeys(field for schema in schemas for field in schema)) if is_union else schemas[0]
        result = [{field: row.get(field) for field in fields} for row in result]
        return {"data": result, "row_count": len(result), "output_schema": fields}
    except (ValueError, TypeError) as exc:
        return {"data": [], "error": str(exc)}
