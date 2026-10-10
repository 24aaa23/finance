"""Render the schema-grounded raw SPARQL retrieval contract."""
from ..raw_query import render_raw_query


def semantic_generate_sparql(inputs, client=None, model=None):
    retrieval = inputs.get("retrieval_spec") or {}
    if not retrieval:
        retrievals = inputs.get("query_spec", {}).get("retrieval_specs", [])
        if len(retrievals) == 1:
            retrieval = retrievals[0]
    query = render_raw_query(retrieval, inputs.get("global_schema", {}))
    if query is None:
        raise ValueError("Retrieval has no complete RDF class/property binding; repair Query_Spec.")
    return {"sparql": query, "generation_method": "retrieval_contract"}
