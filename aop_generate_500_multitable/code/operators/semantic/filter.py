import re
import json
from typing import Dict, Any, List
from code.operators.base import parse_llm_json, repair_sparql_query, build_schema_generation_rules, strip_llm_reasoning_blocks
from code.config import api_logger, LOCAL_MODEL, LLMClient

def semantic_filter_aggregate(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Filter & Aggregate
    Purpose: Extracts specific WHERE conditions and aggregation functions (AVG, SUM) from the query.
    Expected inputs: 'query', 'schema_details'.
    """
    prompt = f"""
    The next operator is Filter and Aggregate.
    Identify the WHERE clause conditions and aggregations needed for the query.

    Query: {inputs.get('query')}
    Schema: {json.dumps(inputs.get('schema_details', {}), indent=2)}

    Output strictly a JSON object: {{"filters": ["condition 1"], "aggregations": ["aggregation 1"]}}
    """

    api_logger.log_call(inputs.get('query'), "Filter_Aggregate")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    result = response.choices[0].message.content
    return {"logic_components": parse_llm_json(result, {"filters": [], "aggregations": []}, "Filter_Aggregate")}

