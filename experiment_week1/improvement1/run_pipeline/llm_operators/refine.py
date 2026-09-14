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
    The next operator is Refine.
    Analyze the SPARQL error and provide a corrected raw SPARQL query.

    User Query: {inputs.get('query')}
    Query Spec: {json.dumps(inputs.get('query_spec', {}), indent=2)}
    Failed SPARQL: {inputs.get('failed_sparql')}
    Database Error: {inputs.get('error_message')}
    Logic Feedback: {inputs.get('logic_feedback', 'None')}
    Schema Details: {json.dumps(schema_details, indent=2)}

    CRITICAL RULE 1: Include these exact prefixes:
    PREFIX wm: <https://wealth.example.org/ontology/>
    PREFIX kg: <https://wealth.example.org/kg/>
    PREFIX wmmeta: <https://wealth.example.org/metadata/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX schema1: <http://schema.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    CRITICAL RULE 2: If the error involves aggregation/math, remember you MUST cast strings to numbers: e.g., SUM(xsd:decimal(?value)) and ensure there is a GROUP BY. Never put aggregate functions like SUM, AVG, COUNT, MIN, or MAX inside BIND or OPTIONAL blocks; aggregate in SELECT instead.

    CRITICAL RULE 3: Use only classes, predicates, and resources visible in Schema Details or explicitly listed in Logic Feedback. Do not invent replacement names.

    CRITICAL RULE 4: If Logic Feedback contains unknown_terms and suggestions, replace invalid terms with the closest valid schema term only when it fits the user's question. Otherwise rewrite the graph pattern using valid schema relationships.

    QUERY SPEC REFINEMENT RULES:
    - The corrected SPARQL must still satisfy the Query_Spec.
    - Do not fix syntax by changing the meaning of the query.
    - Do not remove required measures from query_spec["measures"].
    - Do not remove required group_by fields.
    - If query_spec has formula-based measures, preserve the formula.
    - If the previous error was a timeout, rewrite the query structurally using subqueries or pre-aggregation.
    - If the previous error was unknown RDF terms, replace only invalid terms with valid schema-grounded terms.
    - The corrected query must be suitable for Pre_Scan_Validate before Scan.

    JOIN SAFETY RULES:
    - Use cardinality_hints from Schema Details when joining classes through literal properties.
    - Do not create a flat join between two classes through a literal property when both sides show many_per_value behavior for the joined values.
    - A many_per_value to many_per_value flat join can multiply rows, distort SUM/AVG results, and time out.
    - If such a join is truly needed, first aggregate each class separately in subqueries, then join the smaller grouped results.
    - If no direct relationship or safe cardinality exists, answer from the most relevant class instead of forcing a join.
    - Timeout feedback means the query plan is too large; rewrite the graph pattern structurally, not cosmetically.

    MISSING RELATED RECORD RULE:
    - If the query asks for base entities with at least one related record missing a field, anchor the WHERE pattern on the related record class that owns the missing field.
    - If the related record has the base entity key as a literal property, count/select DISTINCT that key directly from the related record.
    - Avoid traversing through the base entity class for this pattern unless the related record does not carry the base key.
    - Apply FILTER NOT EXISTS to the related record, not to the base entity.

    Output strictly the corrected raw SPARQL text without explanations, reasoning tags, prose, comments, or markdown formatting.
    The first non-whitespace characters in your response must be PREFIX or SELECT.
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
