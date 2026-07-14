import re
import json
from typing import Dict, Any, List
from code.operators.base import parse_llm_json, repair_sparql_query, build_schema_generation_rules, strip_llm_reasoning_blocks
from code.config import api_logger, LOCAL_MODEL, LLMClient

def semantic_retrieve(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Retrieve
    Purpose: Analyzes the user query against a lightweight index of the Knowledge Graph
             to identify the relevant ontology classes needed for the query.
    Inputs: 'query', 'table_index'
    Outputs: 'retrieved_tables' (List of class names)

    The reason for using lightweight index is to reduce the number of tokens sent to the LLM.

    """

    table_index = inputs.get('table_index', {})
    prompt = f"""
You are the Retrieve operator. Select relevant ontology class names for the user query.

User Query: {inputs.get('query')}
Available Classes (Index): {json.dumps(table_index, indent=2)}

Return ONLY a JSON array of exact class names from Available Classes.
Do not write Python code.
Do not explain.
Example output: ["InvestorProfile", "PortfolioHolding"]
"""

    api_logger.log_call(inputs.get('query'), "Retrieve")
    # The response is collected for the above prompts and input
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    #the result is stored after cleaning the response from the LLM and in the form of json object
    result = response.choices[0].message.content
    retrieved_tables = parse_llm_json(result, [], "Retrieve")
    if not isinstance(retrieved_tables, list):
        retrieved_tables = []
    retrieved_tables = [table for table in retrieved_tables if table in table_index]
    if not retrieved_tables:
        print("[WARN] Retrieve returned no valid classes; Generate will use the full dynamic schema.")
    return {"retrieved_tables": retrieved_tables}

