"""Deterministic pre-scan checks for the active raw SELECT query."""

from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.parserutils import CompValue
from pyparsing import ParseResults

from ..common import Any, Dict, LOCAL_MODEL
from ..spec_contracts import flatten_identifiers


def _nodes(value):
    if isinstance(value, CompValue):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, (list, tuple, ParseResults)):
        for child in value:
            yield from _nodes(child)


def _structure(value):
    if isinstance(value, CompValue):
        return (value.name, tuple((key, _structure(child)) for key, child in value.items()))
    if isinstance(value, (list, tuple, ParseResults)):
        return tuple(_structure(child) for child in value)
    return value


def semantic_pre_scan_validate(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """Check executable structure; Scan evaluates against the actual data.

    An explicit date/non-null predicate can legitimately remove unbound OPTIONAL
    values. A single branch need not retrieve other branches' source classes.
    """
    sparql = inputs.get("sparql", "")
    query_spec = inputs.get("query_spec") or {}

    def reject(reason: str, stage: str = "Generate") -> dict:
        return {"pre_scan_validation": {
            "is_valid": False, "severity": "hard_error", "reason": reason,
            "rewrite_hint": "Return an executable SELECT with the active retrieval's declared field aliases.",
            "repair_stage": stage,
        }}

    if isinstance(query_spec, dict) and query_spec.get("contract_errors"):
        return reject("Query_Spec has unresolved contract errors: " + "; ".join(query_spec["contract_errors"]), "Query_Spec")
    if not isinstance(sparql, str) or not sparql.strip():
        return reject("No SPARQL was generated.")
    try:
        parsed = parseQuery(sparql)[1]
    except Exception as exc:
        return reject("Invalid SPARQL syntax: " + str(exc))
    if parsed.name != "SelectQuery":
        return reject("Raw retrieval must be a SELECT query.")
    for node in _nodes(parsed):
        if node.name in {"SelectQuery", "SubSelect"} and any(
                key in node for key in ("modifier", "groupby", "having", "orderby", "limitoffset")):
            return reject("Raw retrieval must preserve all rows: remove DISTINCT/REDUCED, grouping, sorting, and limits; calculate them in the final plan.")
        if node.name.startswith("Aggregate_"):
            return reject("Raw retrieval cannot aggregate records; select the raw fields for the final plan.")

    retrieval = inputs.get("retrieval_spec") or {}
    if not retrieval and isinstance(query_spec, dict):
        retrievals = query_spec.get("retrieval_specs", [])
        if isinstance(retrievals, list) and len(retrievals) == 1:
            retrieval = retrievals[0]
    required = flatten_identifiers(retrieval.get("fields", [])) if isinstance(retrieval, dict) else []
    if isinstance(retrieval, dict):
        from ..raw_query import render_raw_query
        try:
            canonical = render_raw_query(retrieval, inputs.get("global_schema", {}))
        except (ValueError, TypeError) as exc:
            return reject("Invalid retrieval contract: " + str(exc), "Query_Spec")
        # When bindings are known, Generate owns a canonical query. Refine must
        # not move filters into OPTIONAL, change properties or add a raw join.
        # This compares parsed structures, not a regex over keywords/literals.
        if canonical is not None and _structure(parsed) != _structure(parseQuery(canonical)[1]):
            return reject("Query differs from the rendered retrieval contract. Regenerate its canonical raw SELECT.")
    # SELECT * omits projection in the parser. Actual Scan bindings are checked
    # downstream; named expression aliases are represented through evar.
    if "projection" in parsed:
        selected = {
            str(term[key]) for term in parsed["projection"]
            for key in ("var", "evar") if key in term
        }
        missing = [field for field in required if field not in selected]
        if missing:
            return reject("SPARQL omits declared projection fields: " + ", ".join(missing))
    return {"pre_scan_validation": {
        "is_valid": True, "severity": "valid",
        "reason": "SELECT syntax and declared projection passed deterministic checks.",
        "rewrite_hint": "", "validation_method": "sparql_parser",
    }}
