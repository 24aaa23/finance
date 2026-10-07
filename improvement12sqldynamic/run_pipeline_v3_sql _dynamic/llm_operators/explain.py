"""Explain operator: formats final pipeline output."""

from ..common import (
    Any,
    Dict,
    LLMClient,
    LOCAL_MODEL,
    json,
)
from .validate import clean_rows_for_final_answer


def semantic_explain_results(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Explain
    Purpose: Serialize computed output locally, preserving values and NULLs.
    Inputs: 'query', 'data'
    Outputs: 'final_answer' (String)
    """

    # --- FIX: Instant Bypass for Short-Circuits ---
    if "context" in inputs and not inputs.get("data"):
        return {"final_answer": inputs.get("context")}
    # ----------------------------------------------
    raw_data = inputs.get('data', [])
    query = inputs.get("query", "")
    if raw_data == []:
        return {"final_answer": "[]"}
    # Formatting never sends result values to a model, including legacy opt-outs.
    cleaned_data = clean_rows_for_final_answer(raw_data, query) if isinstance(raw_data, list) else raw_data
    return {"final_answer": json.dumps(cleaned_data, ensure_ascii=False)}
