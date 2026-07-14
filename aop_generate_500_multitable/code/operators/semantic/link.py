import re
import json
from typing import Dict, Any, List
from code.operators.base import parse_llm_json, repair_sparql_query, build_schema_generation_rules, strip_llm_reasoning_blocks
from code.config import api_logger, LOCAL_MODEL, LLMClient

def semantic_link(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Link
    Purpose: Identifies how two or more graph classes should be connected via Object Properties.
    """
    prompt = f"""
    The next operator is Link.
    Identify the relational paths (Object Properties) between the retrieved classes based on their schema.

    Retrieved Classes: {inputs.get('retrieved_tables')}
    Schema Details: {json.dumps(inputs.get('schema_details', {}), indent=2)}

    Output strictly a JSON object detailing the link conditions.
    Example: {{"joins": [{{"class_1": "Investor", "class_2": "Portfolio", "property": "hasPortfolio"}}]}}
    """

    api_logger.log_call(inputs.get('query'), "Link")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    result = response.choices[0].message.content
    return {"join_conditions": parse_llm_json(result, {"joins": []}, "Link")}

