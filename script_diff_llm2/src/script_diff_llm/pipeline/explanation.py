import json
import re
from typing import Any, Callable

from openai import OpenAI as LLMClient

from script_diff_llm.pipeline.kg_pipeline import strip_llm_reasoning_blocks


def normalize_value_for_final_answer(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_value_for_final_answer(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value_for_final_answer(item) for item in value]
    if isinstance(value, str) and value.strip().upper() in {"NULL", "NONE"}:
        return None
    return value


def is_list_query(query: str) -> bool:
    q = str(query or "").lower()
    return any(marker in q for marker in ["which", "show", "list", "identify", "find"])


def is_count_query(query: str) -> bool:
    q = str(query or "").lower()
    return any(marker in q for marker in [
        "count",
        "how many",
        "number of",
        "total number",
        "frequency",
    ])


def clean_rows_for_final_answer(raw_data: list, query: str) -> list:
    del query
    cleaned = []
    for row in raw_data:
        cleaned.append(normalize_value_for_final_answer(row))
    return cleaned


def should_return_structured_json(query: str, raw_data: Any, deterministic_explain: bool) -> bool:
    if not deterministic_explain or not isinstance(raw_data, list):
        return False
    if len(raw_data) == 0:
        return False

    if all(isinstance(row, dict) for row in raw_data):
        return True

    row_count = len(raw_data)
    list_output = is_list_query(query)
    table_output = row_count > 1
    return list_output or table_output


def semantic_explain_results(
    inputs: dict[str, Any],
    client: LLMClient,
    model: str,
    *,
    deterministic_explain: bool,
    log_call_fn: Callable[[Any, str], None],
    supports_temperature_fn: Callable[[str], bool],
) -> dict[str, Any]:
    if "context" in inputs and not inputs.get("data"):
        return {"final_answer": inputs.get("context")}

    raw_data = inputs.get("data", [])
    query = inputs.get("query", "")
    if raw_data == []:
        return {"final_answer": "[]"}
    if should_return_structured_json(query, raw_data, deterministic_explain):
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

    log_call_fn(inputs.get("query"), "Explain")
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if supports_temperature_fn(model):
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
