"""Generate raw SPARQL from a validated retrieval contract.

The normal path is deterministic.  The model fallback is kept for schemas that
do not expose enough RDF metadata to compile a contract locally.
"""

import os
import re

from ..common import (
    Any,
    Dict,
    api_logger,
    json,
)
from ..clients import build_llm_messages
from ..utils import repair_sparql_for_query


def _sparql_string(value: Any) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _literal(value: Any, value_type: str = "") -> str:
    if value is None:
        return ""
    kind = str(value_type or "").lower()
    if kind in {"number", "numeric", "integer", "float", "decimal"}:
        text = str(value).strip()
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text):
            return text
    if kind in {"date", "datetime"}:
        datatype = "http://www.w3.org/2001/XMLSchema#date" if kind == "date" else "http://www.w3.org/2001/XMLSchema#dateTime"
        return f"{_sparql_string(value)}^^<{datatype}>"
    if isinstance(value, bool):
        return "true" if value else "false"
    return _sparql_string(value)


def _filter_expression(predicate: dict, variables: dict[str, str]) -> str:
    if "conditions" in predicate or "filters" in predicate:
        children = predicate.get("conditions", predicate.get("filters", []))
        if not isinstance(children, list) or not children:
            raise ValueError("logical filter group requires conditions")
        logic = str(predicate.get("logic", predicate.get("join", "and"))).lower()
        if logic not in {"and", "or"}:
            raise ValueError(f"unsupported filter logic: {logic}")
        parts = [_filter_expression(item, variables) for item in children if isinstance(item, dict)]
        if len(parts) != len(children):
            raise ValueError("logical filter group contains a malformed condition")
        return "(" + (" && " if logic == "and" else " || ").join(parts) + ")"
    field = str(predicate.get("field") or "")
    variable = variables.get(field)
    if not variable:
        raise ValueError(f"filter field is not selected: {field}")
    operator = str(predicate.get("operator") or "=").strip().lower().replace("_", " ")
    value = predicate.get("value")
    if value is None and operator in {"=", "=="}:
        return f"!BOUND({variable})"
    if value is None and operator in {"!=", "<>", "is not null", "is not null"}:
        return f"BOUND({variable})"
    if operator in {"is null", "is not null"}:
        return f"{'!' if operator == 'is null' else ''}BOUND({variable})"
    if operator in {"in", "not in"}:
        values = value if isinstance(value, list) else [value]
        expression = f"{variable} IN ({', '.join(_literal(item, predicate.get('value_type', '')) for item in values)})"
        return f"!({expression})" if operator == "not in" else expression
    if operator == "between":
        values = value if isinstance(value, list) else []
        if len(values) != 2:
            raise ValueError("between requires exactly two values")
        low = _literal(values[0], predicate.get("value_type", ""))
        high = _literal(values[1], predicate.get("value_type", ""))
        return f"({variable} >= {low} && {variable} <= {high})"
    if operator == "contains":
        return f"CONTAINS(STR({variable}), {_literal(value)})"
    symbols = {"==": "=", "equals": "=", "eq": "=", "ne": "!=", "<>": "!="}
    operator = symbols.get(operator, operator)
    if operator not in {"=", "!=", ">", "<", ">=", "<="}:
        raise ValueError(f"unsupported raw filter operator: {operator}")
    return f"{variable} {operator} {_literal(value, predicate.get('value_type', ''))}"


def _compile_contract_sparql(retrieval: dict, schema: dict) -> str | None:
    """Compile the supported single-source raw contract without interpretation."""
    source = str(retrieval.get("class") or "")
    details = schema.get(source, {}) if isinstance(schema, dict) else {}
    class_iri = details.get("class_iri")
    properties = details.get("property_iris", {})
    subject = str(details.get("subject_field") or "subject_iri")
    fields = list(dict.fromkeys(str(field) for field in retrieval.get("fields", []) if field))
    if not class_iri or not properties or not fields:
        return None
    if subject not in fields:
        fields.insert(0, subject)
    optional = set(str(field) for field in retrieval.get("optional_fields", []) if field != subject)
    def filter_fields(items):
        result = set()
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("field"):
                result.add(str(item["field"]))
            result.update(filter_fields(item.get("conditions", item.get("filters", []))))
        return result
    filtered = filter_fields(retrieval.get("filters", []))
    optional -= filtered  # an explicit filter must control row eligibility
    variables = {field: "?f_" + re.sub(r"[^A-Za-z0-9_]", "_", field) for field in fields if field != subject}
    variables[subject] = "?subject"
    selected = [f"({variables[field]} AS ?{field})" if field != subject else "(?subject AS ?" + subject + ")" for field in fields]
    required_patterns = [f"?subject <{properties[field]}> {variables[field]} ." for field in fields if field != subject and field not in optional and field in properties]
    optional_patterns = [f"OPTIONAL {{ ?subject <{properties[field]}> {variables[field]} . }}" for field in fields if field != subject and field in optional and field in properties]
    if any(field != subject and field not in properties for field in fields):
        return None
    filters = [_filter_expression(item, variables) for item in retrieval.get("filters", []) if isinstance(item, dict)]
    body = [f"?subject <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <{class_iri}> .", *required_patterns, *optional_patterns]
    if filters:
        body.append("FILTER (" + " && ".join(filters) + ")")
    return "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nSELECT " + " ".join(selected) + " WHERE {\n  " + "\n  ".join(body) + "\n}"


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

    # Query_Spec has already validated the source, fields, keys, and predicates.
    # Compiling that contract here removes a second model interpretation.  Set
    # V6_DETERMINISTIC_GENERATE=0 only for controlled fallback comparisons.
    if os.getenv("V6_DETERMINISTIC_GENERATE", "1").strip().lower() not in {"0", "false", "no"}:
        try:
            compiled = _compile_contract_sparql(active_retrieval_spec, global_schema)
        except (TypeError, ValueError, KeyError):
            compiled = None
        if compiled:
            return {"sparql": compiled}
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
- Apply every declared filter with its exact values and boundaries. Preserve
  AND/OR/NOT scope. Equality is not substring matching. is_null tests an unbound
  value; is_not_null tests a bound value. Other missing values remain unbound.
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
