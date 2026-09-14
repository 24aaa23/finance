"""Explain operator: formats final pipeline output."""

from ..common import (
    Any,
    Dict,
    LLMClient,
    LOCAL_MODEL,
    api_logger,
    json,
    re,
)
from ..clients import supports_temperature
from ..utils import strip_llm_reasoning_blocks
from .validate import clean_rows_for_final_answer, should_return_structured_json


def semantic_explain_results(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Explain
    Purpose: Takes raw data output and translates it into a polished, human-readable
             financial advisory summary.
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
    if should_return_structured_json(query, raw_data):
        cleaned_data = clean_rows_for_final_answer(raw_data, query)
        return {"final_answer": json.dumps(cleaned_data, ensure_ascii=False)}

    data_sample = raw_data[:50] if isinstance(raw_data, list) else raw_data
    row_count = len(raw_data) if isinstance(raw_data, list) else 1

    prompt = f"""
    The next operator is Explain.
    Translate the data sample into a direct, concise answer to the user's original query.
    Use only the facts present in Data Sample. Do not add caveats such as "discrepancy",
    "not enough information", or "unable to determine" when rows are present. Preserve all
    returned categories, IDs, names, counts, and numeric values.

    Original Query: "{inputs.get('query')}"
    Total Row Count: {row_count}
    Data Sample: {json.dumps(data_sample, ensure_ascii=False)}

    If Data Sample contains one or more rows, you MUST answer from those rows.
    Never return a blank response.

    Answer style rules:
    - Return ONLY the final answer. Do not include reasoning, analysis, hidden thoughts, XML tags, <reasoning>, <think>, markdown, or code fences.
    - Keep the answer short, usually one sentence for one-row results.
    - If many rows are returned, summarize all visible rows compactly.
    - Preserve exact labels, IDs, and numeric strings from Raw Data Results. Do not add commas to numbers and do not reformat IDs.

    Output the final natural language response directly. No JSON formatting.
    """

    api_logger.log_call(inputs.get('query'), "Explain")
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if supports_temperature(model):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)
    answer = strip_llm_reasoning_blocks(response.choices[0].message.content).strip()
    answer = re.sub(r"(?is)<(?:reasoning|think)>.*", "", answer).strip()
    if not answer:
        answer = json.dumps(data_sample, ensure_ascii=False)
    no_data_phrases = [
        "no data", "no results", "not available", "unable to determine",
        "not determinable", "unknown", "nothing was found"
    ]
    if raw_data and any(phrase in answer.lower() for phrase in no_data_phrases):
        answer = json.dumps(data_sample, ensure_ascii=False)
    return {"final_answer": answer}
