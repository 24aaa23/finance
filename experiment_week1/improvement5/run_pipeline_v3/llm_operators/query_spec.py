"""Query_Spec operator and its helpers."""

from decimal import Decimal, InvalidOperation

from ..common import (
    Any,
    Dict,
    LOCAL_MODEL,
    api_logger,
    json,
)
from ..clients import build_llm_messages
from ..utils import parse_llm_json
from ..spec_contracts import flatten_identifiers, normalize_spec, validate_query_spec_contract
from ..connections import retain_connection_keys
from ..business_context import business_context_prompt


def _predicate_operator(value: Any) -> str:
    operator = " ".join(str(value or "=").strip().lower().replace("_", " ").split())
    return {
        "==": "=", "eq": "=", "equals": "=", "ne": "!=", "<>": "!=",
        "isnull": "is null", "isnotnull": "is not null", "not null": "is not null",
    }.get(operator, operator)


def _predicate_value_matches(actual: dict, expected: dict) -> bool:
    if _predicate_kind(expected) in {"is null", "is not null"}:
        return True  # Unary predicates have no comparison literal.
    left, right = actual.get("value"), expected.get("value")
    if left == right:
        return True
    if str(actual.get("value_type") or expected.get("value_type") or "").lower() in {"number", "numeric"}:
        try:
            a, b = Decimal(str(left)), Decimal(str(right))
            return a.is_finite() and b.is_finite() and a == b
        except (InvalidOperation, ValueError):
            pass
    return False


def _predicate_kind(predicate: dict) -> str:
    operator = _predicate_operator(predicate.get("operator"))
    if "value" in predicate and predicate["value"] is None:
        return {"=": "is null", "!=": "is not null"}.get(operator, operator)
    return operator


def _source_field(value: Any, class_name: str, details: dict) -> str:
    """Strip only the active class qualifier from a known schema field."""
    name = str(value or "")
    known = {
        str(column.get("name")) if isinstance(column, dict) else str(column)
        for column in details.get("columns", [])
        if (isinstance(column, dict) and column.get("name")) or isinstance(column, str)
    }
    known.update(str(details[key]) for key in ("subject_field", "label_field") if details.get(key))
    prefix = class_name + "."
    if name.startswith(prefix) and name[len(prefix):] in known:
        return name[len(prefix):]
    return name


def _normalize_rdf_fields(spec: dict, schema: dict) -> None:
    """Use the loader's explicit RDF bindings, without guessing domain properties."""
    for retrieval in spec.get("retrieval_specs", []):
        if not isinstance(retrieval, dict):
            continue
        class_name = str(retrieval.get("class") or "")
        details = schema.get(class_name, {})
        subject_field = details.get("subject_field")
        label_field = details.get("label_field")
        aliases = {}
        if subject_field:
            aliases.update({"@id": subject_field, "@subject": subject_field})
            if not flatten_identifiers(retrieval.get("entity_key")):
                retrieval["entity_key"] = [subject_field]
        if label_field:
            aliases.update({"rdfs:label": label_field, "http://www.w3.org/2000/01/rdf-schema#label": label_field})
        def field_name(value):
            return aliases.get(value, _source_field(value, class_name, details))
        for key in ("fields", "optional_fields", "entity_key"):
            if key in retrieval:
                retrieval[key] = [field_name(field) for field in flatten_identifiers(retrieval[key])]
        columns = {column["name"]: column for column in details.get("columns", [])
                   if isinstance(column, dict) and column.get("name")}
        # In a typed raw scan, selecting a property must not impose its presence.
        # Requested presence/eligibility is expressed by the explicit filters.
        if subject_field:
            optional = retrieval.setdefault("optional_fields", [])
            for field in retrieval.get("fields", []):
                if field != subject_field and field in columns and field not in optional:
                    optional.append(field)
        for predicate in retrieval.get("filters", []):
            if isinstance(predicate, dict) and predicate.get("field"):
                predicate["field"] = field_name(predicate["field"])
                datatypes = set(columns.get(predicate["field"], {}).get("rdf_datatypes", []))
                if datatypes == {"http://www.w3.org/2001/XMLSchema#date"}:
                    predicate["value_type"] = "date"
                elif datatypes and datatypes <= {"http://www.w3.org/2001/XMLSchema#dateTime", "http://www.w3.org/2001/XMLSchema#dateTimeStamp"}:
                    predicate["value_type"] = "datetime"
        if len(spec.get("retrieval_specs", [])) == 1:
            spec["output_schema"] = [field_name(field) for field in flatten_identifiers(spec.get("output_schema"))]


def _answer_requirement_errors(spec: Dict[str, Any], decomposition: Dict[str, Any], schema: Dict[str, Any]) -> list[str]:
    """Preserve this branch's declared predicates and explicit relationship keys."""
    requirements = decomposition.get("answer_requirements", {}) if isinstance(decomposition, dict) else {}
    if not isinstance(requirements, dict):
        return []
    retrievals = spec.get("retrieval_specs", []) if isinstance(spec, dict) else []
    retrieval = retrievals[0] if isinstance(retrievals, list) and retrievals and isinstance(retrievals[0], dict) else {}
    class_name = str(retrieval.get("class") or "")
    class_columns = {
        str(column.get("name")) if isinstance(column, dict) else str(column)
        for column in schema.get(class_name, {}).get("columns", [])
        if (isinstance(column, dict) and column.get("name")) or isinstance(column, str)
    }
    fields = set(flatten_identifiers(retrieval.get("fields", [])))
    errors = []
    # Final aliases/grouping notes do not require every raw class with a
    # similarly named field to supply that field.
    details = schema.get(class_name, {})
    branch_id = str(spec.get("branch_id") or spec.get("id") or "")
    for predicate in requirements.get("predicates", []):
        if not isinstance(predicate, dict) or predicate.get("source_class") != class_name:
            continue
        branch_ids = flatten_identifiers(predicate.get("branch_ids", []))
        if branch_ids and branch_id not in branch_ids:
            continue
        field = _source_field(predicate.get("field"), class_name, details)
        if predicate.get("stage", "scan") != "scan":
            if field in class_columns and field not in fields:
                errors.append(f"Query_Spec omits downstream predicate input: {field}")
            continue
        expected_operator = _predicate_kind(predicate)
        matches = [item for item in retrieval.get("filters", []) if isinstance(item, dict)
                   and _source_field(item.get("field"), class_name, details) == field
                   and _predicate_kind(item) == expected_operator
                   and _predicate_value_matches(item, predicate)]
        if not matches:
            errors.append(f"Query_Spec drops or changes required predicate {predicate.get('id', field)}: "
                          f"{field} {predicate.get('operator')} {predicate.get('value')!r}")
    for join in requirements.get("joins", []):
        if not isinstance(join, dict):
            continue
        for side in ("left", "right"):
            if str(join.get(f"{side}_branch") or "") == branch_id:
                for original_field in flatten_identifiers(join.get(f"{side}_on", join.get(f"{side}_field", []))):
                    field = _source_field(original_field, class_name, details)
                    if field in class_columns and field not in fields:
                        errors.append(f"Query_Spec omits required join key: {field}")
    return errors


def _declared_raw_contract(branch, decomposition, schema):
    """Compile explicitly complete raw declarations without reinterpreting them."""
    if branch.get("retrieval_contract_complete") is not True:
        return None
    requirements = decomposition.get("answer_requirements", {})
    source, branch_id = branch.get("source_class"), branch.get("id")
    details = schema.get(source, {})
    subject = details.get("subject_field")
    if not subject or not branch_id or not branch.get("required_fields"):
        return None
    if not all(isinstance(requirements.get(key), list) for key in ("predicates", "joins")):
        return None
    predicates, joins = requirements["predicates"], requirements["joins"]
    if any(not isinstance(item, dict) for item in predicates + joins):
        return None
    # Logical predicate trees still use the established model path. Do not flatten
    # OR/NOT into an AND or drop conditions whose ownership is incomplete.
    if any(not p.get("source_class") or not p.get("field") or not p.get("operator")
           or any(key in p for key in ("any", "all", "not", "conditions", "filters"))
           or p.get("stage", "scan") not in {"scan", "final"} for p in predicates):
        return None
    assigned = [p for p in predicates if p["source_class"] == source and
                (not p.get("branch_ids") or branch_id in flatten_identifiers(p["branch_ids"]))]
    if set(flatten_identifiers(branch.get("requirement_ids"))) - {p.get("id") for p in assigned}:
        return None
    fields = [subject] + flatten_identifiers(branch["required_fields"])
    filters = []
    for predicate in assigned:
        field = _source_field(predicate["field"], source, details)
        if predicate.get("stage", "scan") == "scan":
            filters.append({key: value for key, value in predicate.items()
                            if key in {"field", "operator", "value", "value_type"}})
            fields.append(field)
        elif field in {c.get("name") if isinstance(c, dict) else c for c in details.get("columns", [])}:
            fields.append(field)
    for join in joins:
        for side in ("left", "right"):
            if join.get(side + "_branch") == branch_id:
                keys = flatten_identifiers(join.get(side + "_on", join.get(side + "_field")))
                if not keys:
                    return None
                fields.extend(keys)
    fields = list(dict.fromkeys(_source_field(field, source, details) for field in fields))
    return {"id": branch_id, "construction": "declared_branch_contract",
            "retrieval_specs": [{"id": branch_id, "class": source, "entity_key": [subject],
                                 "fields": fields, "filters": filters,
                                 "purpose": branch.get("purpose", "")}], "output_schema": fields}


def semantic_build_query_spec(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Query_Spec
    Convert one decomposition branch into a schema-grounded raw retrieval contract.
    """

    query = inputs.get("query", "")
    original_query = inputs.get("original_query", query)
    subquestion = inputs.get("subquestion", {})
    decomposition = inputs.get("decomposition", {})
    retrieved_tables = inputs.get("retrieved_tables", [])
    spec_feedback = inputs.get("spec_feedback", "")

    global_schema = inputs.get("global_schema", {})
    schema_details = inputs.get("schema_details")
    if not schema_details:
        schema_details = {
            cls: global_schema[cls]
            for cls in retrieved_tables
            if cls in global_schema
        }
        if not schema_details:
            schema_details = global_schema
    # Decompose can add a connector that Retrieve did not initially select.
    source_class = subquestion.get("source_class") if isinstance(subquestion, dict) else None
    if source_class in global_schema:
        schema_details = {source_class: global_schema[source_class]}
    elif source_class in schema_details:
        schema_details = {source_class: schema_details[source_class]}
    branch_id = subquestion.get("id", "branch id")
    business_context = business_context_prompt()

    prompt = f"""
Describe the raw records to retrieve for one branch.
A retrieval specification (called Query_Spec in code) is JSON naming one source
class, selected fields, record identity, optional fields, and raw-field filters.
It does not contain calculations or a database query.

Assigned source for this call: {source_class}
Assigned branch ID for this call: {branch_id}
Original question: {original_query}
Active branch: {json.dumps(subquestion)}
Shared metric, population and condition contracts: {json.dumps(decomposition.get('answer_requirements', {}))}
Schema: {json.dumps(schema_details)}
Business rule pack, authoritative for metric operands, signs, weighting, and null policy: {business_context}
Repair feedback: {spec_feedback}
Previous branch contract, if any: {json.dumps(inputs.get('previous_query_spec', {}), default=str)}

Rules:
- Use the branch's assigned source class and exact local field names from schema.
  This call implements ONLY the active branch. Other metric sources are handled
  by their own branches. Do not switch to a fact source while retrieving its
  profile/connector, even if most metrics in the original question use that fact.
  The original question remains authoritative; preserve its conditions and meaning.
  When the branch supports a governed metric, select the raw operands required
  by the business rule pack rather than a similarly named shortcut field.
- fields lists every raw value needed for calculation, display, filtering, and
  joining. Include the complete identity and linking keys, even if not displayed.
- entity_key identifies a raw record. Prefer schema subject_field, the RDF subject
  itself. A link to another entity is not the identity of this record.
- optional_fields is the subset of fields that may be missing. Keep measures,
  display values, and grouping values optional unless an explicit condition needs
  them present. Missing one measure must not remove rows needed by another measure.
- filters contains only requested raw-field conditions. Preserve literal values,
  boundaries, AND/OR and negation scope. Use equality for exact categories, contains
  only for requested substrings, and is_null/is_not_null for missing/present values.
  A condition on a sum/average belongs in the final calculation. Absence of related
  records needs a separate exclusion branch, not a raw not-equal filter.
- Use typed values: number, date, string, list, or null. Do not label a date as a
  string merely because its JSON representation is text.
- Match links to the same entity type and key representation. Do not substitute
  a display label or require a field owned by another source on this source.
- Return exactly one retrieval_specs entry; no formulas, totals, sorting or limits.

Return only JSON. id names the retrieval; class names the source; filters use
field/operator/value/value_type; output_schema repeats the selected field names.
{{"id":{json.dumps(branch_id)}, "retrieval_specs":[{{
 "id":{json.dumps(branch_id)}, "class":{json.dumps(source_class or 'exact source class')}, "entity_key":["record key"],
 "fields":["record key","needed field"], "optional_fields":["needed field"],
 "filters":[], "purpose":"what this source contributes"
}}], "output_schema":["record key","needed field"]}}
Filter example: {{"field":"exact field", "operator":">", "value":10, "value_type":"number"}}
Supported operators: =, !=, >, <, >=, <=, between, in, not_in, contains, is_null, is_not_null.
"""

    parsed_spec = _declared_raw_contract(subquestion, decomposition, global_schema or schema_details)
    if parsed_spec is None:
        api_logger.log_call(query, "Query_Spec")
        request = {
            "model": model,
            "messages": build_llm_messages("query_spec", prompt),
        }
        if not model.lower().startswith("gpt-5"):
            request["temperature"] = 0.0
        response = client.chat.completions.create(**request)
        parsed_spec = parse_llm_json(response.choices[0].message.content, None, "Query_Spec")
    if not isinstance(parsed_spec, dict):
        return {"query_spec": {"contract_errors": ["Query_Spec did not return a valid JSON object."]}}

    if isinstance(decomposition, dict):
        parsed_spec["answer_requirements"] = decomposition.get("answer_requirements", {})
    parsed_spec["branch_id"] = str(subquestion.get("id") or parsed_spec.get("id") or "") if isinstance(subquestion, dict) else str(parsed_spec.get("id") or "")
    contract_schema = inputs.get("global_schema", schema_details)
    _normalize_rdf_fields(parsed_spec, contract_schema)
    parsed_spec = cleanup_query_spec(parsed_spec, query, retrieved_tables)
    parsed_spec = normalize_spec(parsed_spec)
    connection_errors = retain_connection_keys(parsed_spec, decomposition, contract_schema)
    parsed_spec["contract_errors"] = validate_query_spec_contract(parsed_spec, contract_schema)
    parsed_spec["contract_errors"].extend(connection_errors)
    from ..semantic_contracts import predicate_errors
    for retrieval in parsed_spec.get("retrieval_specs", []):
        parsed_spec["contract_errors"].extend(predicate_errors(retrieval.get("filters", [])))
    parsed_spec["contract_errors"].extend(parsed_spec.get("cleanup_contract_errors", []))
    parsed_spec["contract_errors"].extend(
        _answer_requirement_errors(parsed_spec, decomposition, contract_schema)
    )
    expected_source = subquestion.get("source_class") if isinstance(subquestion, dict) else None
    retrievals = parsed_spec.get("retrieval_specs", [])
    if expected_source and retrievals and isinstance(retrievals[0], dict) and retrievals[0].get("class") != expected_source:
        parsed_spec["contract_errors"].append(f"Query_Spec changed assigned source class {expected_source} to {retrievals[0].get('class')}.")
    elif expected_source and retrievals and isinstance(retrievals[0], dict):
        required = {_source_field(field, expected_source, contract_schema.get(expected_source, {}))
                    for field in flatten_identifiers(subquestion.get("required_fields", []))}
        missing = required - set(retrievals[0].get("fields", []))
        if missing:
            parsed_spec["contract_errors"].append(f"Query_Spec omits assigned branch fields: {sorted(missing)}.")
    return {"query_spec": parsed_spec}


def cleanup_query_spec(query_spec: Dict[str, Any], query: str, retrieved_tables: list) -> Dict[str, Any]:
    """Normalize Query_Spec output for the operator-first execution contract."""
    if not isinstance(query_spec, dict):
        return query_spec

    cleaned = json.loads(json.dumps(query_spec))
    cleanup_notes = []
    cleanup_errors = list(cleaned.get("cleanup_contract_errors", []))

    question_type = str(cleaned.get("question_type") or cleaned.get("query_type") or "multi_step").lower()
    if question_type not in {"lookup", "filter", "aggregation", "ranking", "comparison", "set_logic", "math", "multi_step"}:
        question_type = "multi_step"
        cleanup_notes.append("unknown question_type normalized to multi_step")
    cleaned["question_type"] = question_type
    cleaned["query_type"] = question_type

    retrieval_specs = cleaned.get("retrieval_specs", [])
    if not isinstance(retrieval_specs, list):
        retrieval_specs = []
    if not retrieval_specs:
        retrieval_specs = [
            {
                "id": "main",
                "class": retrieved_tables[0] if retrieved_tables else None,
                "fields": [],
                "filters": [],
                "purpose": "Retrieve raw facts for the original question.",
            }
        ]
        cleanup_notes.append("retrieval_specs filled from retrieved classes")
    # Preserve unsupported intent so contract validation can trigger repair. Dropping
    # a scan would turn a multi-source question into a different question.
    if len(retrieval_specs) > 1:
        cleanup_errors.append("Query_Spec requests multiple sources; repair decomposition into separate source branches without dropping any retrieval.")
    for index, spec in enumerate(retrieval_specs):
        if not isinstance(spec, dict):
            retrieval_specs[index] = {"id": f"scan_{index + 1}", "class": None, "fields": [], "filters": []}
            continue
        spec.setdefault("id", f"scan_{index + 1}")
        spec.setdefault("entity_key", [])
        spec.setdefault("fields", [])
        spec.setdefault("optional_fields", [])
        spec.setdefault("filters", [])
        spec.setdefault("purpose", "")
        spec["fields"] = flatten_identifiers(spec["fields"])
        # Both lists explicitly select raw fields. Treat optional_fields as an
        # optional subset, even when the model lists it separately from fields.
        # Normal schema validation below still rejects unknown field names.
        for key in ("entity_key", "optional_fields"):
            spec[key] = flatten_identifiers(spec[key])
            for field in spec[key]:
                if field not in spec["fields"]:
                    spec["fields"].append(field)
        for filter_spec in spec["filters"] if isinstance(spec["filters"], list) else []:
            if isinstance(filter_spec, dict) and filter_spec.get("field") and filter_spec["field"] not in spec["fields"]:
                spec["fields"].append(filter_spec["field"])
    cleaned["retrieval_specs"] = retrieval_specs

    if not cleaned.get("required_classes"):
        cleaned["required_classes"] = [
            spec.get("class")
            for spec in retrieval_specs
            if isinstance(spec, dict) and spec.get("class")
        ] or retrieved_tables
        cleanup_notes.append("required_classes filled from retrieval_specs")

    # If Decompose says a retrieved raw field will be a nullable final grouping
    # dimension, make it optional here.  This is schema-driven and preserves SQL NULL
    # groups without putting an aggregation in SPARQL.
    requirements = query_spec.get("answer_requirements", {})
    grouping_fields = set(flatten_identifiers(requirements.get("group_by", []))) if isinstance(requirements, dict) else set()
    preserve_nulls = bool(requirements.get("preserve_null_groups", False)) if isinstance(requirements, dict) else False
    if preserve_nulls:
        for spec in retrieval_specs:
            if isinstance(spec, dict):
                optional = set(flatten_identifiers(spec.get("optional_fields", [])))
                optional.update(str(field) for field in spec.get("fields", []) if str(field) in grouping_fields)
                spec["optional_fields"] = sorted(optional)

    # Do not erase computation or misplaced filters to make an invalid plan pass.
    # Their correct owner must repair the plan while the requested meaning is intact.
    for key in ("measures", "group_by", "filters"):
        if cleaned.get(key):
            cleanup_errors.append(f"Query_Spec has unsupported top-level {key}; place raw filters in retrieval_specs and computation in Processing_Spec/Final_Spec.")
    cleaned.setdefault("operator_plan", [])
    cleaned.setdefault("merge_plan", {"required": False, "operator": None, "join_key": None})

    output_schema = cleaned.get("output_schema", [])
    cleaned["output_schema"] = output_schema if isinstance(output_schema, list) else []

    # Backward-compatible hints used by Generate/Validate code paths.
    cleaned["execution_strategy"] = "raw_retrieval_only"
    cleaned.setdefault("measures", [])
    cleaned.setdefault("group_by", [])
    cleaned.setdefault("filters", [])
    cleaned["cleanup_contract_errors"] = list(dict.fromkeys(cleanup_errors))

    if cleanup_notes:
        prior_reason = str(cleaned.get("reason", "")).strip()
        cleaned["cleanup_notes"] = cleanup_notes
        cleaned["reason"] = (prior_reason + " Cleanup: " + "; ".join(cleanup_notes)).strip()

    return cleaned
