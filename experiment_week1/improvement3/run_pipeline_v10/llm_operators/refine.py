"""Refine operator: repairs failed SPARQL using LLM feedback."""

from ..common import (
    Any,
    Dict,
    api_logger,
    json,
)
from ..clients import build_llm_messages, supports_temperature
from ..utils import repair_sparql_for_query


def semantic_refine(inputs: Dict[str, Any], client: Any, model: str) -> Dict[str, Any]:
    """
    Operator: Refine
    Purpose: Acts as the self-reflection and self-healing mechanism to fix broken
             SPARQL queries based on database execution errors.
    Inputs: 'failed_sparql', 'error_message', 'schema_details', 'logic_feedback'
    Outputs: 'sparql' (Corrected query string)
    """
    schema_details = inputs.get('schema_details') or inputs.get('global_schema', {})
    prompt = f"""
Repair the failed raw SPARQL SELECT without changing its meaning.
The retrieval specification is JSON defining the source class, selected fields,
record identity, optional fields, and filters. Preserve all of these during repair.

Question: {inputs.get('query')}
Retrieval specification: {json.dumps(inputs.get('query_spec', {}).get('retrieval_specs', []))}
Failed SPARQL: {inputs.get('failed_sparql')}
Database error: {inputs.get('error_message')}
Repair feedback: {inputs.get('logic_feedback', '')}
Schema: {json.dumps(schema_details)}

- Use the exact schema class_iri and predicate_iri values. An IRI is a full RDF
  resource identifier. Declare used prefixes or write full <IRI> values.
- Bind the typed subject itself for subject_field, not a property with that name.
- Select every required field using its declared alias. Keep optional bindings
  OPTIONAL; preserve raw duplicates and missing values.
- Preserve every filter's value, operator, AND/OR/NOT scope, and date boundary.
  Keep row-eligibility FILTERs outside OPTIONAL bindings, including !BOUND/BOUND
  tests for missing/present values; moving them inside would retain excluded rows.
  Use numeric/date literals compatible with the RDF field datatype. Do not
  compare dates to strings or change equality to substring matching.
- Fix syntax or invalid schema terms using the supplied evidence. A timeout does
  not authorize dropping a source or condition. Do not answer an easier question.
- Retrieve raw records only: no aggregates, formulas, GROUP BY, ORDER BY, LIMIT,
  DISTINCT, or calculation subqueries. These rules always apply.

Return the corrected SPARQL only, starting with PREFIX or SELECT. No code fences.
"""

    api_logger.log_call(inputs.get('query'), "Refine")
    request = {
        "model": model,
        "messages": build_llm_messages("refine", prompt),
    }
    if supports_temperature(model):
        request["temperature"] = 0.1
    response = client.chat.completions.create(**request)
    result = response.choices[0].message.content.strip()

    #UI-SAFE SPARQL EXTRACTOR
    ##since the output is sometimes in the form of markdown, in order to maintain uniformity
    # we extract only the useful part in a fixed format
    if "```" in result:
        parts = result.split("```")
        if len(parts) >= 3:
            code_block = parts[1]
            if code_block.lower().startswith("sparql"):
                code_block = code_block[6:]
            sparql = code_block.strip()
        else:
            sparql = result.replace("```sparql", "").replace("```SPARQL", "").replace("```", "").strip()
    else:
        sparql = result.strip()

    return {"sparql": repair_sparql_for_query(sparql, inputs.get("query", ""))}
