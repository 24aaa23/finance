"""Format result rows locally; no result values are sent to a model."""
from ..common import json
from .validate import clean_rows_for_final_answer


def semantic_explain_results(inputs, client=None, model=None):
    if "context" in inputs and not inputs.get("data"):
        return {"final_answer": inputs["context"]}
    data = inputs.get("data", [])
    if isinstance(data, list):
        data = clean_rows_for_final_answer(data, inputs.get("query", ""))
    return {"final_answer": json.dumps(data, ensure_ascii=False)}
