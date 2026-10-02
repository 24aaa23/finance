"""Generate the same raw retrieval contract as a SQLite SELECT."""
from ..common import Any, Dict, api_logger, json
from ..clients import build_llm_messages
from ..raw_sql import render_raw_sql


def extract_sql(text: str) -> str:
    """Remove only a surrounding code fence; never rewrite query semantics."""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
    return text


def semantic_generate_sparql(inputs: Dict[str, Any], client: Any, model: str) -> Dict[str, Any]:
    # Keep the public function and `sparql` payload key so DAG/report contracts
    # remain unchanged. Their contents are SQL in this package.
    schema = inputs.get("global_schema", {})
    retrieval = inputs.get("retrieval_spec") or {}
    if not retrieval:
        retrievals = inputs.get("query_spec", {}).get("retrieval_specs", [])
        if len(retrievals) == 1 and isinstance(retrievals[0], dict):
            retrieval = retrievals[0]
    rendered = render_raw_sql(retrieval, schema)
    if rendered is not None:
        return {"sparql": rendered, "generation_method": "retrieval_contract"}

    prompt = f"""
Write one raw SQLite SELECT from the retrieval specification below.
The class key names a physical SQL table. Select every declared field using
its exact column name. Later Python operators calculate the final answer.

Original question: {inputs.get('original_query', inputs.get('query'))}
Retrieval specification: {json.dumps(retrieval)}
Schema: {json.dumps(schema)}
Previous query, if repairing: {inputs.get('sparql', '')}
Repair feedback: {inputs.get('logic_feedback', '')}

Use only the specified table and real columns, quoted with double quotes.
Preserve duplicates, native values and NULLs. optional_fields are nullable
columns; selecting them must not impose IS NOT NULL. Preserve all filters,
literal values, AND/OR/NOT scope and date boundaries. Use IS NULL/IS NOT NULL
for missing/present values. No joins, aggregates, formulas, GROUP BY, ORDER BY,
LIMIT, DISTINCT or calculation subqueries. Return SQL only, without fences.
"""
    api_logger.log_call(inputs.get("query"), "Generate")
    request = {"model": model, "messages": build_llm_messages("generate", prompt)}
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)
    return {"sparql": extract_sql(response.choices[0].message.content)}
