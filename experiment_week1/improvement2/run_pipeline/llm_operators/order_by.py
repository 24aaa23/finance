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
from ..utils import parse_llm_json


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
        direction = str(inputs.get("direction") or "DESC").upper()
        limit = inputs.get("limit")

        if column not in df.columns:
            return {
                "data": data,
                "operator_result": data,
                "error": f"Sort column {column} not found in data.",
            }

        sort_series = pd.to_numeric(df[column], errors="coerce")
        if sort_series.notna().any():
            df["_sort_key"] = sort_series
            sort_column = "_sort_key"
        else:
            sort_column = column

        ascending = direction == "ASC"
        stable_columns = [sort_column]
        if len(df.columns) > 1:
            stable_columns.extend([col for col in df.columns if col != "_sort_key" and col != column][:1])
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
