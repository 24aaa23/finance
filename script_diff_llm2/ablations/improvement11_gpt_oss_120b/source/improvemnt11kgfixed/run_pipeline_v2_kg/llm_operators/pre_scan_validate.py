"""Validate canonical raw SPARQL before any network request."""
from ..raw_query import render_raw_query, canonical_sparql_tokens
from ..kg_backend import validate_read_query


def semantic_pre_scan_validate(inputs, client=None, model=None):
    spec = inputs.get("query_spec") or {}

    def reject(reason, stage="Generate"):
        return {"pre_scan_validation": {"is_valid": False, "severity": "hard_error", "reason": reason,
                "rewrite_hint": "Regenerate SPARQL from the active RDF retrieval contract.", "repair_stage": stage}}

    if spec.get("contract_errors"):
        return reject("Query_Spec has unresolved contract errors: " + "; ".join(spec["contract_errors"]), "Query_Spec")
    retrieval = inputs.get("retrieval_spec") or {}
    if not retrieval:
        retrievals = spec.get("retrieval_specs", [])
        if len(retrievals) == 1:
            retrieval = retrievals[0]
    try:
        canonical = render_raw_query(retrieval, inputs.get("global_schema", {}))
        if canonical is None:
            return reject("Retrieval lacks a complete RDF binding.", "Query_Spec")
    except (ValueError, TypeError, AttributeError) as error:
        return reject("Invalid RDF retrieval contract: " + str(error), "Query_Spec")
    query = inputs.get("sparql", "")
    try:
        validate_read_query(query)
        if canonical_sparql_tokens(query) != canonical_sparql_tokens(canonical):
            return reject("SPARQL differs from its retrieval contract (source, fields, optional fields or filters). Calculations belong in Python.")
    except Exception as error:
        return reject("Invalid SPARQL: " + str(error))
    return {"pre_scan_validation": {"is_valid": True, "severity": "valid",
            "reason": "Canonical RDF retrieval and SPARQL syntax passed deterministic checks.",
            "rewrite_hint": "", "validation_method": "rdf_retrieval_contract"}}
