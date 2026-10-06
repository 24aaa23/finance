"""Retrieve operator: selects relevant RDF classes using an LLM."""

from ..common import (
    Any,
    Dict,
    LLMClient,
    LOCAL_MODEL,
    api_logger,
    json,
)
from ..clients import build_llm_messages
from ..prompt_boundary import index_for_prompt
from ..utils import parse_llm_json
from ..rdf_contracts import class_key


def semantic_retrieve(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Retrieve
    Purpose: Analyzes the user query against a lightweight RDF schema index
             to identify the relevant source tables needed for the query.
    Inputs: 'query', 'table_index'
    Outputs: 'retrieved_tables' (List of table names)

    The reason for using lightweight index is to reduce the number of tokens sent to the LLM.

    """

    table_index = index_for_prompt(inputs.get('table_index', {}))
    prompt = f"""
Select the RDF classes needed to answer the question.
The index lists each RDF class and its available columns.
Include sources needed for conditions, returned values, and connections between
records. A category/label source does not replace the entity that owns that label.

Table index: {json.dumps(table_index)}
Question: {inputs.get('query')}
Resolved question meaning: {json.dumps(inputs.get('query_understanding', {}))}
Preserve resolved field ownership and metric operands. Include their source tables
and any necessary connectors. Do not substitute a related entity's attribute.

Return only a JSON array of exact table names from this index, for example
["exact table name from the index"]. Do not invent names or return an object.
"""

    api_logger.log_call(inputs.get('query'), "Retrieve")
    # The response is collected for the above prompts and input
    request = {
        "model": model,
        "messages": build_llm_messages("retrieve", prompt),
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    #the result is stored after cleaning the response from the LLM and in the form of json object
    result = response.choices[0].message.content
    retrieved_tables = parse_llm_json(result, [], "Retrieve")
    if not isinstance(retrieved_tables, list):
        retrieved_tables = []
    declared = {name: details if isinstance(details, dict) else {} for name, details in table_index.items()}
    retrieved_tables = [class_key(table, declared) for table in retrieved_tables if isinstance(table, str)]
    retrieved_tables = list(dict.fromkeys(table for table in retrieved_tables if table in table_index))
    if not retrieved_tables:
        print("[WARN] Retrieve returned no valid tables; Generate will use the full dynamic schema.")
    return {"retrieved_tables": retrieved_tables}
