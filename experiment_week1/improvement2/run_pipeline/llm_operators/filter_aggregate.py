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
from ..utils import parse_llm_json


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
        operation = str(inputs.get("operation") or "filter").lower()
        group_by = inputs.get("group_by", [])
        if isinstance(group_by, str):
            group_by = [group_by]
        group_by = [col for col in group_by if col in df.columns]
        target_column = inputs.get("target_column") or inputs.get("column")
        output_column = inputs.get("output_column") or (
            f"{operation}_{target_column}" if target_column else f"{operation}_count"
        )

        df = _apply_filters(df, filters)

        if operation in {"filter", "where"}:
            rows = df.to_dict(orient="records")
            return {"data": rows, "operator_result": rows, "row_count": len(rows)}

        if operation == "count":
            if group_by:
                result_df = df.groupby(group_by, dropna=False).size().reset_index(name=output_column)
            else:
                result_df = pd.DataFrame([{output_column: len(df)}])
        else:
            if not target_column or target_column not in df.columns:
                return {
                    "data": [],
                    "operator_result": [],
                    "error": f"Column {target_column} not found for {operation}.",
                }
            df[target_column] = _coerce_numeric(df[target_column])
            agg_map = {
                "sum": "sum",
                "avg": "mean",
                "average": "mean",
                "min": "min",
                "max": "max",
            }
            if operation not in agg_map:
                return {"data": df.to_dict(orient="records"), "operator_result": df.to_dict(orient="records")}
            if group_by:
                result_df = df.groupby(group_by, dropna=False)[target_column].agg(agg_map[operation]).reset_index()
                result_df = result_df.rename(columns={target_column: output_column})
            else:
                result_df = pd.DataFrame([{output_column: getattr(df[target_column], agg_map[operation])()}])

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
