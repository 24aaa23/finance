"""Retrieve operator: selects relevant KG classes/tables using an LLM."""

from ..common import (
    Any,
    Dict,
    LLMClient,
    LOCAL_MODEL,
    api_logger,
    json,
)
from ..clients import build_llm_messages
from ..utils import parse_llm_json


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
Select the schema classes needed to answer the question.
A class is a type of record. The index lists each class and its available fields.
Include sources needed for conditions, returned values, and connections between
records. A category/label source does not replace the entity that owns that label.

Question: {inputs.get('query')}
Class index: {json.dumps(table_index)}

Return only a JSON array of exact class names from this index, for example
["exact class name from the index"]. Do not invent names or return an object.
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
    retrieved_tables = [table for table in retrieved_tables if table in table_index]
    if not retrieved_tables:
        print("[WARN] Retrieve returned no valid classes; Generate will use the full dynamic schema.")
    return {"retrieved_tables": retrieved_tables}
