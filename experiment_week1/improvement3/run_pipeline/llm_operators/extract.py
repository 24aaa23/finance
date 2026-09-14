"""Extract operator."""

from ..common import (
    Any,
    Dict,
    LLMClient,
    LOCAL_MODEL,
    api_logger,
)
from ..clients import build_llm_messages
from ..utils import parse_llm_json


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
        model=model, messages=build_llm_messages("semantic", prompt), temperature=0.0
    )
    result = response.choices[0].message.content
    return {"extracted_entities": parse_llm_json(result, {}, "Extract")}
