"""Order_By operator."""

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


def _find_column(df: pd.DataFrame, col_name: Any) -> Any:
    if not col_name or df.empty:
        return None
    if col_name in df.columns:
        return col_name
    canon = re.sub(r"[^a-z0-9]+", "", str(col_name).lower())
    for col in df.columns:
        if re.sub(r"[^a-z0-9]+", "", str(col).lower()) == canon:
            return col
    for col in df.columns:
        col_canon = re.sub(r"[^a-z0-9]+", "", str(col).lower())
        if canon in col_canon or col_canon in canon:
            return col
    return None


def semantic_order_by(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Order_By
    Sorts post-scan/operator rows.

    Expected data-mode inputs:
    - data: list[dict]
    - column/order_by: sort column
    - direction: ASC|DESC
    - limit: optional int
    """
    data = inputs.get("data", [])
    if "data" in inputs:
        if not data:
            return {"data": [], "operator_result": [], "row_count": 0}
        df = pd.DataFrame(data)
        column = inputs.get("column") or inputs.get("order_by") or inputs.get("target_column")
        direction = str(inputs.get("direction") or "").upper()
        limit = inputs.get("limit")
        strict_spec = bool(inputs.get("strict_spec"))
        query_text = str(inputs.get("query") or inputs.get("original_query") or "").lower()

        # Infer limit from query if not specified
        if not strict_spec and (limit is None or str(limit).strip() in {"", "none", "null"}):
            num_match = re.search(r"\b(?:top|first|highest|greatest|lowest|best|worst)\s+(\d+)\b", query_text)
            if num_match:
                limit = int(num_match.group(1))
            elif re.search(r"\b(five|5)\b", query_text):
                limit = 5
            elif re.search(r"\b(three|3)\b", query_text):
                limit = 3
            elif re.search(r"\b(ten|10)\b", query_text):
                limit = 10

        # Infer direction from query if not specified
        if not strict_spec and not direction:
            if re.search(r"\b(lowest|least|bottom|smallest|minimum|worst)\b", query_text):
                direction = "ASC"
            else:
                direction = "DESC"

        # A spec is a contract: final ordering must use its exact declared
        # output field.  Fuzzy/semantic lookup remains available only for the
        # legacy natural-language operator mode.
        sort_col = column if strict_spec and column in df.columns else None
        if not strict_spec:
            sort_col = _find_column(df, column)
        if not strict_spec and not sort_col and column:
            sort_col = find_column_by_semantic_match(df.columns, column)

        if not sort_col and not strict_spec:
            # Domain-agnostic resolution: find the numeric non-ID column that best matches the query
            numeric_cols = [
                c for c in df.columns
                if not str(c).lower().endswith("id")
                and str(c).lower() not in {"_sort_key", "index"}
                and pd.to_numeric(df[c], errors="coerce").notna().any()
            ]
            if numeric_cols:
                sort_col = find_column_by_semantic_match(numeric_cols, query_text)
                if not sort_col:
                    sort_col = numeric_cols[0]

        if not sort_col:
            try:
                if limit is not None and str(limit).strip() != "":
                    df = df.head(int(limit))
            except (TypeError, ValueError):
                pass
            rows = df.where(pd.notna(df), None).to_dict(orient="records")
            return {
                "data": rows,
                "operator_result": rows,
                "row_count": len(rows),
                "error": f"Sort column {column} not found in data.",
            }

        sort_series = pd.to_numeric(df[sort_col], errors="coerce")
        if sort_series.notna().any():
            df["_sort_key"] = sort_series
            effective_sort_col = "_sort_key"
        else:
            effective_sort_col = sort_col

        ascending = direction == "ASC"
        stable_columns = [effective_sort_col]
        if len(df.columns) > 1:
            stable_columns.extend([col for col in df.columns if col != "_sort_key" and col != column][:1])
            stable_columns.extend([col for col in df.columns if col != "_sort_key" and col != sort_col][:1])
        ascending_flags = [ascending] + [True] * (len(stable_columns) - 1)
        df = df.sort_values(stable_columns, ascending=ascending_flags, kind="mergesort")

        if "_sort_key" in df.columns:
            df = df.drop(columns=["_sort_key"])
        try:
            if limit is not None and str(limit).strip() != "":
                df = df.head(int(limit))
        except (TypeError, ValueError):
            pass

        rows = df.where(pd.notna(df), None).to_dict(orient="records")
        return {"data": rows, "operator_result": rows, "row_count": len(rows)}

    prompt = f"""
    The next operator is Order_By.
    Translate the qualitative sorting request in the query into a post-scan sort instruction.
    Do not write SPARQL.

    User Query: "{inputs.get('query')}"
    Schema Details: {json.dumps(inputs.get('schema_details', {}))}

    Output strictly a JSON object. Example: {{"column": "annual_return_pct", "direction": "DESC", "limit": 5}}
    """

    api_logger.log_call(inputs.get("query"), "Order_By")
    response = client.chat.completions.create(
        model=model,
        messages=build_llm_messages("semantic", prompt),
        temperature=0.0,
    )
    result = response.choices[0].message.content
    return {"sorting_logic": parse_llm_json(result, {"column": None, "direction": "DESC", "limit": None}, "Order_By")}
