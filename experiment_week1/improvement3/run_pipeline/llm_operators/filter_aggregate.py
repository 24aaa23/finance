"""Filter/Aggregate operator."""

from ..common import (
    Any,
    Dict,
    LLMClient,
    LOCAL_MODEL,
    api_logger,
    json,
    pd,
)
from ..clients import build_llm_messages
from ..utils import parse_llm_json, find_column_by_semantic_match


import re


def _canonical_key(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def _find_column(df: pd.DataFrame, col_name: Any) -> Any:
    if not col_name or df.empty:
        return None
    if col_name in df.columns:
        return col_name
    canon = _canonical_key(col_name)
    for col in df.columns:
        if _canonical_key(col) == canon:
            return col
    for col in df.columns:
        col_canon = _canonical_key(col)
        if canon in col_canon or col_canon in canon:
            return col
    return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {col: str(col).strip() for col in df.columns}
    return df.rename(columns=rename_map)


def _coerce_numeric(series):
    return pd.to_numeric(series, errors="coerce")


def _apply_filters(df: pd.DataFrame, filters: list) -> pd.DataFrame:
    filtered = df
    for condition in filters or []:
        if not isinstance(condition, dict):
            continue
        column = condition.get("field") or condition.get("column") or condition.get("target_column")
        raw_col = condition.get("field") or condition.get("column") or condition.get("target_column")
        column = _find_column(filtered, raw_col)
        if not column:
            continue
        operator = str(condition.get("operator") or "=").lower()
        value = condition.get("value")
        if column not in filtered.columns:
            continue

        series = filtered[column]
        if operator in {"=", "eq"}:
            filtered = filtered[series.astype(str).str.lower() == str(value).lower()]
        elif operator in {"contains", "like"}:
            filtered = filtered[series.astype(str).str.lower().str.contains(str(value).lower(), na=False)]
        elif operator in {"not_contains", "not like"}:
            filtered = filtered[~series.astype(str).str.lower().str.contains(str(value).lower(), na=False)]
        elif operator in {">", ">=", "<", "<="}:
            numeric = _coerce_numeric(series)
            numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
            if pd.isna(numeric_value):
                continue
            if operator == ">":
                filtered = filtered[numeric > numeric_value]
            elif operator == ">=":
                filtered = filtered[numeric >= numeric_value]
            elif operator == "<":
                filtered = filtered[numeric < numeric_value]
            elif operator == "<=":
                filtered = filtered[numeric <= numeric_value]
        elif operator in {"in", "not_in"}:
            values = value if isinstance(value, list) else [value]
            lowered = {str(item).lower() for item in values}
            mask = series.astype(str).str.lower().isin(lowered)
            filtered = filtered[~mask if operator == "not_in" else mask]
        elif operator == "between" and isinstance(value, list) and len(value) == 2:
            numeric = _coerce_numeric(series)
            low = pd.to_numeric(pd.Series([value[0]]), errors="coerce").iloc[0]
            high = pd.to_numeric(pd.Series([value[1]]), errors="coerce").iloc[0]
            if not pd.isna(low) and not pd.isna(high):
                filtered = filtered[(numeric >= low) & (numeric <= high)]
    return filtered


def semantic_filter_aggregate(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Filter_Aggregate
    Applies row filters and aggregations after Scan.

    Expected data-mode inputs:
    - data: list[dict]
    - filters: optional list of filter dicts
    - operation: filter|sum|avg|count|min|max
    - group_by: optional list[str]
    - target_column: optional str
    - output_column: optional str
    """
    data = inputs.get("data", [])
    if "data" in inputs:
        df = _normalize_columns(pd.DataFrame(data))
        filters = inputs.get("filters", [])
        operation = str(inputs.get("operation") or "").lower()
        strict_aggregation = bool(inputs.get("strict_aggregation"))
        strict_spec = bool(inputs.get("strict_spec")) or strict_aggregation
        query_text = str(inputs.get("query") or inputs.get("original_query") or "").lower()

        # Infer operation from query if missing or default filter
        if not strict_spec and (not operation or operation in {"filter", "none"}):
            if re.search(r"\b(how many|count of|transaction count|number of)\b", query_text):
                operation = "count"
            elif re.search(r"\b(average|avg)\b", query_text):
                operation = "avg"
            elif re.search(r"\b(total|sum)\b", query_text):
                operation = "sum"
            elif re.search(r"\b(minimum|min)\b", query_text):
                operation = "min"
            elif re.search(r"\b(maximum|max)\b", query_text):
                operation = "max"
            else:
                operation = "filter"

        group_by = inputs.get("group_by", [])
        if isinstance(group_by, str):
            group_by = [group_by]
        raw_group_by = inputs.get("group_by", [])
        if isinstance(raw_group_by, str):
            raw_group_by = [raw_group_by]
        group_by = raw_group_by
        resolved_group_by = []
        for col in group_by:
            matched = col if strict_spec and col in df.columns else None
            if not strict_spec:
                matched = _find_column(df, col) or find_column_by_semantic_match(df.columns, col)
            if matched and matched not in resolved_group_by:
                resolved_group_by.append(matched)
            elif strict_spec:
                return {"data": [], "operator_result": [], "row_count": 0,
                        "error": f"Declared group-by column does not exist: {col}"}
        group_by = resolved_group_by

        # Auto-detect group_by if not specified and query mentions grouped comparison
        if not strict_spec and not group_by and len(df.columns) > 1:
            # 1. Domain-agnostic preposition extraction: "for each X", "in each X", "by X", "per X", "across each X"
            prep_match = re.search(
                r"\b(?:for each|in each|per|grouped by|broken down by|categorized by|by)\s+([a-zA-Z0-9_\s\-]+?)(?:\?|,|\.|\bfor\b|\bwith\b|\bwhere\b|\bacross\b|$)",
                query_text,
                flags=re.I,
            )
            if prep_match:
                group_phrase = prep_match.group(1).strip()
                non_id_cols = [c for c in df.columns if not str(c).lower().endswith("id")]
                matched = find_column_by_semantic_match(non_id_cols, group_phrase)
                if matched and matched not in group_by:
                    group_by.append(matched)

            # 2. OLAP Dimension Heuristic fallback for COUNT:
            # If counting over a table with an ID column and a categorical column, group by the categorical column
            if not group_by and operation == "count":
                non_id_cols = [
                    c for c in df.columns
                    if not str(c).lower().endswith("id")
                    and str(c).lower() not in {"_sort_key", "index"}
                    and not pd.to_numeric(df[c], errors="coerce").notna().all()
                ]
                if non_id_cols:
                    group_by = [non_id_cols[0]]

        if strict_spec:
            for condition in filters or []:
                if not isinstance(condition, dict):
                    return {"data": [], "operator_result": [], "row_count": 0,
                            "error": "Declared filter is not an object."}
                field = condition.get("field") or condition.get("column") or condition.get("target_column")
                if not isinstance(field, str) or field not in df.columns:
                    return {"data": [], "operator_result": [], "row_count": 0,
                            "error": f"Declared filter column does not exist: {field}"}
        df = _apply_filters(df, filters)

        if operation in {"filter", "where"}:
            rows = df.to_dict(orient="records")
            return {"data": rows, "operator_result": rows, "row_count": len(rows)}

        if operation == "count":
            output_column = inputs.get("output_column") or inputs.get("target_column") or "count"
            if group_by:
                result_df = df.groupby(group_by, dropna=False).size().reset_index(name=output_column)
                # Legacy direct operator calls can infer a second metric from the question.
                # A Processing_Spec/Final_Spec call is an explicit contract: one declared
                # measure per step, so it must never add an undeclared column.
                also_sum = not strict_aggregation and re.search(r"\b(total|sum|amount)\b", query_text)
                also_avg = not strict_aggregation and re.search(r"\b(average|avg|mean)\b", query_text)
                if also_sum or also_avg:
                    numeric_candidates = [
                        c for c in df.columns
                        if c not in group_by
                        and not str(c).lower().endswith("id")
                        and str(c).lower() not in {"_sort_key", "index"}
                        and pd.to_numeric(df[c], errors="coerce").notna().any()
                    ]
                    for num_col in numeric_candidates:
                        df[num_col] = _coerce_numeric(df[num_col])
                        agg_fn = "sum" if also_sum else "mean"
                        out_num_name = f"total_{num_col}" if also_sum else f"avg_{num_col}"
                        agg_res = df.groupby(group_by, dropna=False)[num_col].agg(agg_fn).reset_index(name=out_num_name)
                        result_df = pd.merge(result_df, agg_res, on=group_by, how="left")
            else:
                result_df = pd.DataFrame([{output_column: len(df)}])
        else:
            agg_map = {
                "sum": "sum",
                "avg": "mean",
                "average": "mean",
                "min": "min",
                "max": "max",
            }
            if operation not in agg_map:
                return {"data": df.to_dict(orient="records"), "operator_result": df.to_dict(orient="records")}
            agg_func = agg_map[operation]

            # Support multi-metric aggregation
            raw_target = inputs.get("target_column") or inputs.get("column") or inputs.get("target_columns")
            target_columns = []
            if strict_spec and not raw_target:
                return {"data": [], "operator_result": [], "row_count": 0,
                        "error": f"Declared target column is required for {operation}."}
            if isinstance(raw_target, list):
                if strict_spec and any(not isinstance(c, str) or c not in df.columns for c in raw_target):
                    return {"data": [], "operator_result": [], "row_count": 0,
                            "error": "A declared target column does not exist."}
                target_columns = [_find_column(df, c) or find_column_by_semantic_match(df.columns, c) for c in raw_target if _find_column(df, c) or find_column_by_semantic_match(df.columns, c)]
            elif raw_target:
                matched = raw_target if strict_spec and raw_target in df.columns else None
                if not strict_spec:
                    matched = _find_column(df, raw_target) or find_column_by_semantic_match(df.columns, raw_target)
                if matched:
                    target_columns = [matched]

            if not target_columns and not strict_spec:
                # Find all eligible numeric columns in df
                numeric_candidates = [
                    c for c in df.columns
                    if c not in group_by
                    and not str(c).lower().endswith("id")
                    and str(c).lower() not in {"_sort_key", "index"}
                    and pd.to_numeric(df[c], errors="coerce").notna().any()
                ]
                # Filter to columns whose tokens appear in query text if specific metrics were mentioned
                query_matched = [c for c in numeric_candidates if find_column_by_semantic_match([c], query_text)]
                target_columns = query_matched if query_matched else numeric_candidates

            if not target_columns:
                return {
                    "data": [],
                    "operator_result": [],
                    "error": f"No numeric column found for {operation}.",
                }

            for col in target_columns:
                df[col] = _coerce_numeric(df[col])

            if group_by:
                # Grouping columns cannot be in target_columns
                target_columns = [c for c in target_columns if c not in group_by]
                if not target_columns:
                    numeric_candidates = [
                        c for c in df.columns
                        if c not in group_by
                        and not str(c).lower().endswith("id")
                        and str(c).lower() not in {"_sort_key", "index"}
                        and pd.to_numeric(df[c], errors="coerce").notna().any()
                    ]
                    query_matched = [c for c in numeric_candidates if find_column_by_semantic_match([c], query_text)]
                    target_columns = query_matched if query_matched else numeric_candidates

                if not target_columns:
                    result_df = df.groupby(group_by, dropna=False).size().reset_index(name="count")
                else:
                    for col in target_columns:
                        df[col] = _coerce_numeric(df[col])
                    agg_dict = {col: agg_func for col in target_columns}
                    result_df = df.groupby(group_by, dropna=False).agg(agg_dict).reset_index()
                    requested_output = inputs.get("output_column")
                    rename_dict = {
                        col: (requested_output if requested_output and len(target_columns) == 1 else f"{operation}_{col}")
                        for col in target_columns
                    }
                    result_df = result_df.rename(columns=rename_dict)
            else:
                for col in target_columns:
                    df[col] = _coerce_numeric(df[col])
                row_dict = {}
                for col in target_columns:
                    val = getattr(df[col], agg_func)()
                    requested_output = inputs.get("output_column")
                    out_col = requested_output if requested_output and len(target_columns) == 1 else f"{operation}_{col}"
                    row_dict[out_col] = val
                result_df = pd.DataFrame([row_dict])

        # Rename grouped columns in result_df back to requested spec names if provided
        for orig_req, res_col in zip(raw_group_by, group_by):
            if orig_req and res_col and orig_req != res_col and res_col in result_df.columns:
                result_df = result_df.rename(columns={res_col: orig_req})

        rows = result_df.where(pd.notna(result_df), None).to_dict(orient="records")
        return {"data": rows, "operator_result": rows, "row_count": len(rows)}

    prompt = f"""
    The next operator is Filter_Aggregate.
    Identify post-scan filters and aggregations needed for the query. Do not write SPARQL.

    Query: {inputs.get('query')}
    Schema: {json.dumps(inputs.get('schema_details', {}), indent=2)}

    Output strictly a JSON object:
    {{"filters": [], "operation": "filter|sum|avg|count|min|max", "group_by": [], "target_column": null, "output_column": null}}
    """

    api_logger.log_call(inputs.get("query"), "Filter_Aggregate")
    response = client.chat.completions.create(
        model=model,
        messages=build_llm_messages("semantic", prompt),
        temperature=0.0,
    )
    result = response.choices[0].message.content
    return {"logic_components": parse_llm_json(result, {"filters": [], "aggregations": []}, "Filter_Aggregate")}
