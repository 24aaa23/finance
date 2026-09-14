"""Generate operator: creates SPARQL using an LLM."""

from ..common import (
    Any,
    Dict,
    api_logger,
    json,
)
from ..clients import build_llm_messages
from ..utils import repair_sparql_for_query


def semantic_generate_sparql(inputs: Dict[str, Any], client: Any, model: str) -> Dict[str, Any]:
    """
    Operator: Generate
    Purpose: Dynamically writes an executable SPARQL query based on the specific
             classes retrieved and the strict rules of the target ontology. The rules are specified
             by us and can be changed as per our needs. In case the KG is modified, these need to be changed as well

    Inputs: 'query', 'retrieved_tables', 'global_schema'
    Outputs: 'sparql' (Executable query string)
    """

    #the data from KG
    retrieved_classes = inputs.get('retrieved_tables', [])
    global_schema = inputs.get('global_schema', {})

    print(f"\n[DEBUG] Retrieve passed these classes: {retrieved_classes}")

    pruned_schema = {cls: global_schema[cls] for cls in retrieved_classes if cls in global_schema}
    if not pruned_schema:
        print("[DEBUG] Target Classes empty/invalid. Passing full dynamic schema to Generate.")
        pruned_schema = global_schema

    # || Adding these feedback and failed query to correct regeneration
    logic_feedback = inputs.get('logic_feedback', '')
    failed_sparql = inputs.get('sparql', '')
    query_spec = inputs.get('query_spec', {})
    active_retrieval_spec = inputs.get("retrieval_spec", {})
    if not active_retrieval_spec and isinstance(query_spec, dict):
        retrievals = query_spec.get("retrieval_specs", [])
        if len(retrievals) == 1 and isinstance(retrievals[0], dict):
            active_retrieval_spec = retrievals[0]
    # The active contract may use a connector added after the initial Retrieve.
    source_class = active_retrieval_spec.get("class") if isinstance(active_retrieval_spec, dict) else None
    if source_class in global_schema and source_class not in pruned_schema:
        pruned_schema = {**pruned_schema, source_class: global_schema[source_class]}
    prompt = f"""
Write one raw SPARQL SELECT from the retrieval specification below.
The specification defines one source class, selected fields, identity keys,
optional fields (which may be missing), and filters. Implement it without changing
the requested population. Later Python operators calculate the answer.

Original question: {inputs.get('original_query', inputs.get('query'))}
Retrieval specification: {json.dumps(active_retrieval_spec)}
Schema: {json.dumps(pruned_schema)}
Previous query, if repairing: {failed_sparql if logic_feedback else ''}
Repair feedback: {logic_feedback}

Rules:
- Use exact class_iri and predicate_iri values in the schema. Full <IRI> syntax is
  allowed; declare any prefixes you use. An IRI is a full RDF resource identifier.
- Anchor the subject with rdf:type. The schema's subject_field names this subject
  variable, not a predicate. Select every declared field with its exact alias.
- Bind ordinary fields through their listed predicates. A label_field is a display
  value, not an identity key. Do not invent properties or replace fields by labels.
- Wrap each optional_fields binding in OPTIONAL, including the full path if it
  retrieves a label. Do not also require the same binding outside OPTIONAL.
  When a field is listed in optional_fields, its binding AND any filter on it
  must both be inside the same OPTIONAL block. A filter outside OPTIONAL on an
  unbound variable silently drops all rows.
- Apply every declared filter with its exact values and boundaries. Preserve
  AND/OR/NOT scope. Equality is not substring matching. is_null tests an unbound
  value (use !BOUND(?var)); is_not_null tests a bound value (use BOUND(?var)).
  Other missing values remain unbound.
- For filters on optional fields, place the FILTER inside the OPTIONAL block so
  that rows missing the field are not dropped. Only exclude rows when the filter
  explicitly requires a specific value (equality, range, in).
- Match numeric/date comparison literals to the RDF datatype. Cast in the filter
  only when necessary; preserve raw selected values. Never compare an RDF date
  with an xsd:string boundary. Preserve the requested date interval.
- Return raw records with identity and linking fields. No aggregates, formulas,
  GROUP BY, ORDER BY, LIMIT, DISTINCT, or nested calculation queries. Do not add
  another source, weaken a condition, or omit a field to make execution easier.

Return raw SPARQL only, beginning with PREFIX or SELECT. No prose or code fences.
"""

    api_logger.log_call(inputs.get('query'), "Generate")
    request = {
        "model": model,
        "messages": build_llm_messages("generate", prompt),
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    result = response.choices[0].message.content.strip()

    # UI-SAFE SPARQL EXTRACTOR
    #since the sparql query generated is sometimes in the form of markdown, in order to maintain uniformity
    # we extract only the useful part in a fixed format
    if "```" in result:
        parts = result.split("```")
        if len(parts) >= 3:
            code_block = parts[1]
            if code_block.lower().startswith("sparql"):
                code_block = code_block[6:]
            sparql_query = code_block.strip()
        else:
            sparql_query = result.replace("```sparql", "").replace("```SPARQL", "").replace("```", "").strip()
    else:
        sparql_query = result.strip()

    return {"sparql": repair_sparql_for_query(sparql_query, inputs.get("query", ""))}
