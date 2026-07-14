import re
import json
from typing import Dict, Any, List
from code.operators.base import parse_llm_json, repair_sparql_query, build_schema_generation_rules, strip_llm_reasoning_blocks
from code.config import api_logger, LOCAL_MODEL, LLMClient

def semantic_extract_entities(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Extract
    Purpose: Extracts specific financial entities (e.g., Investor IDs, Sectors, Asset Classes)
             from natural language to use as exact WHERE clause filters.
    Expected inputs: 'query'
    """
    prompt = f"""
    The next operator is Extract.
    Extract all financial entities, IDs, and categorical filters from the query.

    User Query: "{inputs.get('query')}"

    Output strictly a JSON object mapping entity types to their values.
    Example: {{"investor_ids": ["INV001"], "sectors": ["Technology"], "time_horizons": []}}
    """

    api_logger.log_call(inputs.get('query'), "Extract")
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
    )
    result = response.choices[0].message.content
    return {"extracted_entities": parse_llm_json(result, {}, "Extract")}

