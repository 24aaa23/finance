"""Integrate operator."""

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


def semantic_integrate(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Integrate
    Merges parallel branch outputs. Uses deterministic row merging when branch
    data and a join_key are available; otherwise falls back to LLM synthesis.
    """
    list_a = inputs.get("list_a", [])
    list_b = inputs.get("list_b", [])
    join_key = inputs.get("join_key")
    how = str(inputs.get("join_type") or inputs.get("how") or "inner").lower()

    if join_key and ("list_a" in inputs or "list_b" in inputs):
        if not list_a or not list_b:
            return {"data": [], "integrated_data": [], "row_count": 0}
        df_a = pd.DataFrame(list_a)
        df_b = pd.DataFrame(list_b)
        if join_key in df_a.columns and join_key in df_b.columns:
            if how not in {"inner", "left", "right", "outer"}:
                how = "inner"
            merged_df = pd.merge(df_a, df_b, on=join_key, how=how, suffixes=("_left", "_right"))
            rows = merged_df.where(pd.notna(merged_df), None).to_dict(orient="records")
            return {"data": rows, "integrated_data": rows, "row_count": len(rows)}

    prompt = f"""
    The next operator is Integrate.
    You are receiving data from multiple parallel execution branches. Your task is to synthesize
    this information to answer the original user query.

    User Query: "{inputs.get('query')}"

    Branch 1 Data: {json.dumps(inputs.get('branch_1_output', {}))}
    Branch 2 Data: {json.dumps(inputs.get('branch_2_output', {}))}

    Cross-reference the data from both branches and output the final, integrated answer.
    """

    api_logger.log_call(inputs.get("query"), "Integrate")
    response = client.chat.completions.create(
        model=model,
        messages=build_llm_messages("semantic", prompt),
        temperature=0.2,
    )
    integrated_result = response.choices[0].message.content.strip()
    return {"integrated_result": integrated_result, "data": [{"answer": integrated_result}]}
