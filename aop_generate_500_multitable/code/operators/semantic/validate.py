import re
import json
from typing import Dict, Any, List
from code.operators.base import parse_llm_json, repair_sparql_query, build_schema_generation_rules, strip_llm_reasoning_blocks
from code.config import api_logger, LOCAL_MODEL, LLMClient

def semantic_validate(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    print(f"\n[DEBUG] --- Executing semantic_validate ---")
    data = inputs.get('data', [])
    print(f"[DEBUG] Validating {len(data)} rows for query.")
    if not data:
        val_dict = {"is_valid": False, "reason": "Data Results are empty. Query failed to retrieve necessary facts."}
        print(f"[DEBUG] Output Validation Result: {val_dict}")
        return {"validation": val_dict, "data": data}

    # Extract the column names (keys) from the first row of data to help the LLM verify fields
    returned_fields = list(data[0].keys()) if data and isinstance(data, list) else []

    # Cap the data sample at 10 rows to prevent blowing up the LLM context window during validation
    data_sample = data[:10] if isinstance(data, list) else data
    generated_sparql = inputs.get("sparql", "")

    prompt = f"""
    The next operator is Validate.
    Assess if the following data results successfully answer the user's original query.
    Use the generated SPARQL as part of the evidence. Do not judge only by row count.

    User Query: "{inputs.get('query')}"
    Generated SPARQL:
    {generated_sparql}
    Returned Column Names: {returned_fields}
    Data Results (Sample): {json.dumps(data_sample, indent=2)}

    CRITICAL RULE 1 (EMPTY DATA): If the Data Results are empty (e.g., [] or None), you MUST output "is_valid": false. Empty data means the query failed to retrieve the necessary facts.

    CRITICAL RULE 2 (SCHEMA & FIELD MATCH - FIX E-02): Beyond checking if data is non-empty, you MUST verify:
    1. Do the returned column names logically match what the query asked for? (e.g., if asking for "sector and allocation", both fields MUST be present).
    2. If the query asked for a specific investor/entity filter, does the data reflect only that entity? Or did it return data for everyone?
    3. If the query asked for an aggregation (MAX/MIN/SUM/AVG/COUNT), did the SPARQL and returned fields reflect the requested aggregate, or did it return raw unaggregated rows?
    4. If the query asks for a top/bottom, highest/lowest, maximum/minimum, largest/smallest, best/worst, or ranking-style result, inspect the SPARQL ranking logic.

    CRITICAL RULE 3 (RANKED AGGREGATION): For superlative or ranking questions, a single returned row can be fully valid when the SPARQL intentionally reduces the result:
    - GROUP BY plus an aggregate expression plus ORDER BY plus LIMIT 1 is a valid way to return one top or bottom group.
    - ORDER BY ASC with LIMIT 1 supports lowest/minimum/smallest/bottom questions.
    - ORDER BY DESC with LIMIT 1 supports highest/maximum/largest/top questions.
    - Do NOT require all groups to be returned when ORDER BY and LIMIT already select the final ranked answer.

    If ANY of these logic checks fail, you MUST output "is_valid": false and provide specific, detailed feedback in the "reason" field about which columns/aggregations are wrong.

    Output strictly a JSON object: {{"is_valid": true/false, "reason": "why"}}
    """

    api_logger.log_call(inputs.get('query'), "Validate")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )

    result = response.choices[0].message.content
    val_dict = parse_llm_json(
        result,
        {
            "is_valid": bool(data),
            "reason": "Validator did not return valid JSON; using row-presence fallback.",
        },
        "Validate",
    )
    if not isinstance(val_dict, dict):
        val_dict = {
            "is_valid": bool(data),
            "reason": "Validator returned a non-object response; using row-presence fallback.",
        }

    print(f"[DEBUG] Output Validation Result: {val_dict}")
    return {"validation": val_dict, "data": data}

