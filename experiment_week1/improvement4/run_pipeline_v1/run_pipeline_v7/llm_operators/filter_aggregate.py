"""Explicit row predicates and relational aggregates; no question-based guessing."""

import re
from typing import Any, Dict

import pandas as pd


def _find_column(df: pd.DataFrame, name: Any, strict: bool = False) -> Any:
    if not isinstance(name, str) or not name:
        return None
    if name in df.columns:
        return name
    if not strict:
        canonical = re.sub(r"[^a-z0-9]+", "", name.lower())
        matches = [c for c in df.columns if re.sub(r"[^a-z0-9]+", "", str(c).lower()) == canonical]
        if len(matches) == 1:
            return matches[0]
    return None


def _numeric(series: pd.Series) -> pd.Series:
    converted = pd.to_numeric(series, errors="coerce")
    if (series.notna() & converted.isna()).any():
        raise ValueError(f"Non-numeric value in numeric column: {series.name}")
    return converted


def _records(df: pd.DataFrame) -> list:
    return df.astype(object).where(pd.notna(df), None).to_dict("records")


def _comparison_values(series, value, condition, ordered=False):
    """Keep category literals exact; coerce numbers/dates only when specified."""
    data_type = str(condition.get("data_type") or condition.get("value_type") or condition.get("type") or "").lower()
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    numeric = data_type in {"number", "numeric", "integer", "float"}
    numeric = numeric or (isinstance(value, (int, float)) and not isinstance(value, bool))
    numeric = numeric or (pd.api.types.is_numeric_dtype(series) and not isinstance(value, bool) and pd.notna(numeric_value))
    # Ordered comparisons against numeric literals represented as JSON strings
    # still use numeric order. Equality on string categories stays exact.
    numeric = numeric or (ordered and pd.notna(numeric_value) and data_type not in {"string", "text", "date", "datetime"})
    if numeric:
        if pd.isna(numeric_value):
            raise ValueError("Numeric filter requires a numeric value.")
        return _numeric(series), numeric_value
    if data_type in {"date", "datetime"}:
        converted = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
        if (series.notna() & converted.isna()).any():
            raise ValueError("Invalid date in filter column.")
        return converted, pd.to_datetime(value, errors="raise", utc=True)
    if isinstance(value, bool):
        return series, value
    text = series.astype("string")
    case_sensitive = condition.get("case_sensitive", True)
    if not isinstance(case_sensitive, bool):
        raise ValueError("case_sensitive must be a boolean.")
    return (text, str(value)) if case_sensitive else (text.str.casefold(), str(value).casefold())


def _filter_mask(df: pd.DataFrame, condition: dict, strict: bool) -> pd.Series:
    if not isinstance(condition, dict):
        raise ValueError("Each filter must be an object.")
    for boolean in ("any", "all", "not"):
        if boolean in condition:
            children = condition[boolean]
            if boolean == "not":
                if not isinstance(children, dict):
                    raise ValueError("not requires a predicate object.")
                return ~_filter_mask(df, children, strict).astype("boolean")
            if not isinstance(children, list) or not children:
                raise ValueError(boolean + " requires a nonempty predicate list.")
            combined = pd.Series(boolean == "all", index=df.index, dtype="boolean")
            for child in children:
                mask = _filter_mask(df, child, strict).astype("boolean")
                combined = combined & mask if boolean == "all" else combined | mask
            return combined
    raw = condition.get("field") or condition.get("column") or condition.get("target_column")
    column = _find_column(df, raw, strict)
    if column is None:
        raise ValueError(f"Declared filter column does not exist: {raw}")
    operator = str(condition.get("operator") or "=").strip().lower().replace(" ", "_")
    operator = {"eq": "=", "==": "=", "ne": "!=", "<>": "!=", "gt": ">", "gte": ">=",
                "ge": ">=", "lt": "<", "lte": "<=", "le": "<=", "isnull": "is_null",
                "notnull": "is_not_null", "not_contains": "not_contains"}.get(operator, operator)
    series = df[column]
    value = condition.get("value")
    if operator in {"is_null", "is_not_null"}:
        return series.isna() if operator == "is_null" else series.notna()
    if operator not in {"=", "!=", ">", ">=", "<", "<=", "contains", "not_contains", "like", "not_like", "in", "not_in", "between"}:
        raise ValueError(f"Unsupported filter operator: {operator}")
    if "value" not in condition:
        raise ValueError(f"Filter {operator} requires a value.")
    if value is None:
        # SQL WHERE comparisons to NULL are unknown; use is_null explicitly.
        return pd.Series(pd.NA, index=df.index, dtype="boolean")
    if operator in {"in", "not_in"}:
        if not isinstance(value, list):
            raise ValueError(f"{operator} requires a list of values.")
        mask = pd.Series(False, index=df.index)
        has_null = any(item is None for item in value)
        for item in value:
            if item is not None:
                left, right = _comparison_values(series, item, condition)
                mask |= left.eq(right).fillna(False)
        if operator == "not_in":
            # NOT IN (..., NULL) cannot be true under SQL three-valued logic.
            return (~mask.astype("boolean")).mask(~series.notna() | (has_null & ~mask), pd.NA)
        return mask.astype("boolean").mask(~series.notna() | (has_null & ~mask), pd.NA)
    if operator == "between":
        if not isinstance(value, list) or len(value) != 2 or any(item is None for item in value):
            raise ValueError("between requires two non-null endpoints.")
        lower, low = _comparison_values(series, value[0], condition, ordered=True)
        upper, high = _comparison_values(series, value[1], condition, ordered=True)
        return (lower.ge(low) & upper.le(high)).astype("boolean").mask(series.isna(), pd.NA)
    if operator in {"contains", "not_contains", "like", "not_like"}:
        left, right = _comparison_values(series, str(value), {**condition, "data_type": "string"})
        if operator in {"like", "not_like"}:
            # SQL LIKE wildcards: percent is any string, underscore is one char.
            pattern = "".join(".*" if char == "%" else "." if char == "_" else re.escape(char) for char in str(right))
            mask = left.str.fullmatch(pattern, na=False)
        else:
            mask = left.str.contains(str(right), regex=False, na=False)
        return (~mask if operator.startswith("not_") else mask).astype("boolean").mask(series.isna(), pd.NA)
    left, right = _comparison_values(series, value, condition, ordered=operator in {">", ">=", "<", "<="})
    operation = {"=": "eq", "!=": "ne", ">": "gt", ">=": "ge", "<": "lt", "<=": "le"}[operator]
    return getattr(left, operation)(right).astype("boolean").mask(series.isna(), pd.NA)


def _apply_filters(df: pd.DataFrame, filters: list, strict: bool = False) -> pd.DataFrame:
    if not isinstance(filters, list):
        raise ValueError("filters must be a list of predicate objects.")
    mask = pd.Series(True, index=df.index, dtype="boolean")
    # Validate every predicate against the input relation, including ones after
    # a predicate that matches zero rows. Invalid filters are never skipped.
    for condition in filters:
        mask &= _filter_mask(df, condition, strict)
    return df.loc[mask.fillna(False)].copy()


def _aggregate_value(series: pd.Series, operation: str, distinct: bool):
    if operation in {"count", "count_distinct", "nunique"}:
        return int(series.nunique(dropna=True) if distinct or operation != "count" else series.count())
    if operation in {"sum", "avg", "average", "mean"}:
        series = _numeric(series)
    elif operation in {"min", "max"}:
        converted = pd.to_numeric(series, errors="coerce")
        if converted.notna().sum() == series.notna().sum():
            series = converted
    series = series.dropna()
    if distinct:
        series = series.drop_duplicates()
    if series.empty:
        return None
    value = series.sum(min_count=1) if operation == "sum" else getattr(series, {"avg": "mean", "average": "mean"}.get(operation, operation))()
    return None if pd.isna(value) else value.item() if hasattr(value, "item") else value


def semantic_filter_aggregate(inputs: Dict[str, Any], client: Any = None, model: str | None = None) -> Dict[str, Any]:
    """Execute exact filters and aggregates with SQL-like null/count semantics.

    count with no target (or '*') counts rows; with a target it counts non-nulls.
    count_distinct/nunique or distinct:true excludes duplicate bound values.
    Filters default to case-sensitive literal comparison; contains is literal,
    like uses SQL %/_ patterns. Missing fields and unknown operations fail.
    """
    if "data" in inputs:
        try:
            df = pd.DataFrame(inputs.get("data", []))
            strict = bool(inputs.get("strict_spec") or inputs.get("strict_aggregation"))
            operation = str(inputs.get("operation") or "filter").lower()
            allowed = {"filter", "where", "sum", "avg", "average", "mean", "count", "count_rows", "count_distinct", "nunique", "min", "max"}
            if operation not in allowed:
                raise ValueError(f"Unsupported aggregation operation: {operation}")
            filters = inputs.get("filters", [])
            if not isinstance(filters, list):
                raise ValueError("filters must be a list of predicate objects.")
            groups = inputs.get("group_by") or []
            if isinstance(groups, str):
                groups = [groups]
            if not isinstance(groups, list) or any(not isinstance(c, str) or not c for c in groups):
                raise ValueError("group_by must contain column names.")
            if len(groups) != len(set(groups)):
                raise ValueError("group_by contains duplicate columns.")
            target = inputs.get("target_column") or inputs.get("column") or inputs.get("input_column") or inputs.get("target_columns")
            targets = target if isinstance(target, list) else [target]
            if df.empty and not len(df.columns):
                schema = inputs.get("input_schema")
                if schema is None:
                    # A standalone empty list has no physical schema. Its declared
                    # fields provide the schema; the spec interpreter validates lineage.
                    schema = list(groups) + [c for c in targets if isinstance(c, str) and c != "*"]
                    schema += [c.get("field") or c.get("column") or c.get("target_column") for c in filters if isinstance(c, dict)]
                    schema = list(dict.fromkeys(c for c in schema if isinstance(c, str) and c))
                df = pd.DataFrame(columns=schema)
            resolved_groups = []
            for group in groups:
                found = _find_column(df, group, strict)
                if found is None:
                    raise ValueError(f"Declared group-by column does not exist: {group}")
                resolved_groups.append(found)
            df = _apply_filters(df, filters, strict)
            if operation in {"filter", "where"}:
                rows = _records(df)
                return {"data": rows, "operator_result": rows, "row_count": len(rows)}

            distinct = inputs.get("distinct", False)
            if not isinstance(distinct, bool):
                raise ValueError("distinct must be a boolean.")
            row_count = operation == "count_rows" or (operation == "count" and target in (None, "*"))
            # count_rows explicitly means COUNT(*), even when a model also names
            # the record ID as input_column. COUNT(column) retains its separate
            # non-null semantics; a distinct flag is still contradictory here.
            if row_count and distinct:
                raise ValueError("Row count takes no distinct flag; use count_distinct with a column.")
            if not row_count and (not targets or any(not isinstance(c, str) or not c or c == "*" for c in targets)):
                raise ValueError(f"Declared target column is required for {operation}.")
            requested_output = inputs.get("output_column")
            if requested_output is not None and (not isinstance(requested_output, str) or not requested_output):
                raise ValueError("output_column must be a nonempty string.")
            if len(targets) > 1 and requested_output:
                raise ValueError("One output_column cannot name several target aggregates; declare separate measures.")
            resolved_targets = []
            outputs = []
            for name in ([None] if row_count else targets):
                resolved = _find_column(df, name, strict) if name is not None else None
                if name is not None and resolved is None:
                    raise ValueError(f"Declared target column does not exist: {name}")
                output = requested_output or ("count" if row_count else f"{operation}_{name}")
                if output in groups or output in outputs:
                    raise ValueError(f"Aggregate output collides with another output field: {output}")
                resolved_targets.append(resolved)
                outputs.append(output)

            rows = []
            partitions = df.groupby(resolved_groups, dropna=False, sort=False, observed=True) if groups else [((), df)]
            for key, part in partitions:
                key = key if isinstance(key, tuple) else (key,)
                row = {field: None if pd.isna(value) else value for field, value in zip(groups, key)}
                for resolved, output in zip(resolved_targets, outputs):
                    row[output] = len(part) if row_count else _aggregate_value(part[resolved], operation, distinct)
                rows.append(row)
            return {"data": rows, "operator_result": rows, "row_count": len(rows)}
        except Exception as exc:
            return {"data": [], "operator_result": [], "row_count": 0,
                    "error": str(exc), "code": "FILTER_AGGREGATE_ERROR"}

    from ..common import LOCAL_MODEL, api_logger, json
    from ..clients import build_llm_messages
    from ..utils import parse_llm_json

    prompt = f"""
The next operator is Filter_Aggregate. Declare exact post-scan filters and aggregates.
Do not write SPARQL. Preserve categorical literals, all predicates, and requested grouping.
Query: {inputs.get('query')}
Schema: {json.dumps(inputs.get('schema_details', {}), indent=2)}
count + target null/'*' counts rows; count + a column counts non-null values;
count_distinct counts distinct non-null values. Never invent grouping or another metric.
Output JSON: {{"filters": [], "operation": "filter|sum|avg|count|count_distinct|min|max", "group_by": [], "target_column": null, "output_column": null}}
"""
    api_logger.log_call(inputs.get("query"), "Filter_Aggregate")
    effective_model = model or LOCAL_MODEL
    response = client.chat.completions.create(
        model=effective_model, messages=build_llm_messages("semantic", prompt),
        **({} if effective_model.lower().startswith("gpt-5") else {"temperature": 0.0}),
    )
    return {"logic_components": parse_llm_json(response.choices[0].message.content,
                                              {"filters": [], "aggregations": []}, "Filter_Aggregate")}
