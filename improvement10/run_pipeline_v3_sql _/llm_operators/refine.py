"""Refine failed SQLite retrievals using the existing LLM repair step."""
from ..common import Any, Dict, api_logger, json
from ..clients import build_llm_messages, supports_temperature
from .generate import extract_sql
from ..knowledge import planning_schema


def semantic_refine(inputs: Dict[str, Any], client: Any, model: str) -> Dict[str, Any]:
    schema = planning_schema(inputs.get("schema_details") or inputs.get("global_schema", {}))
    prompt = f"""
Repair the failed raw SQLite SELECT without changing its meaning.
The retrieval specification defines one physical table (under the class key),
selected columns, record keys, nullable fields, and filters. Preserve all of them.

Question: {inputs.get('query')}
Retrieval specification: {json.dumps(inputs.get('query_spec', {}).get('retrieval_specs', []))}
Failed SQL: {inputs.get('failed_sparql')}
Database error: {inputs.get('error_message')}
Repair feedback: {inputs.get('logic_feedback', '')}
Schema: {json.dumps(schema)}

Use only exact table and column names from the schema. Quote identifiers with
double quotes. Select every required field with its declared name. Preserve
raw duplicates and NULLs; optional fields must not become IS NOT NULL filters.
Preserve every filter's value, operator, AND/OR/NOT scope, and date boundary.
Use IS NULL/IS NOT NULL and SQLite-compatible numeric/date comparisons.
Fix syntax or invalid identifiers using supplied evidence. A timeout does not
authorize dropping fields or conditions. No joins, aggregates, formulas,
GROUP BY, ORDER BY, LIMIT, DISTINCT or calculation subqueries. Later Python
operators still do all computation. Return corrected SQL only, without fences.
"""
    api_logger.log_call(inputs.get("query"), "Refine")
    request = {"model": model, "messages": build_llm_messages("refine", prompt)}
    if supports_temperature(model):
        request["temperature"] = 0.1
    response = client.chat.completions.create(**request)
    return {"sparql": extract_sql(response.choices[0].message.content)}
