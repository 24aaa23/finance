import re
import json
from typing import Dict, Any, List
from code.operators.base import parse_llm_json, repair_sparql_query, build_schema_generation_rules, strip_llm_reasoning_blocks
from code.config import api_logger, LOCAL_MODEL, LLMClient

def semantic_order_by(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Semantic OrderBy
    Purpose: Translates qualitative sorting requests (e.g., "best performing", "safest")
             into physical column sorts and directions.
    Expected inputs: 'query', 'schema_details'
    """
    prompt = f"""
    The next operator is Semantic OrderBy.
    Translate the qualitative sorting request in the query into physical columns and directions.

    User Query: "{inputs.get('query')}"
    Schema Details: {json.dumps(inputs.get('schema_details', {}))}

    Output strictly a JSON object. Example: {{"order_by": "annual_return_pct", "direction": "DESC", "limit": 5}}
    """

    api_logger.log_call(inputs.get('query'), "Order_By")
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
    )
    result = response.choices[0].message.content
    return {"sorting_logic": parse_llm_json(result, {"order_by": None, "direction": "DESC", "limit": None}, "Order_By")}

