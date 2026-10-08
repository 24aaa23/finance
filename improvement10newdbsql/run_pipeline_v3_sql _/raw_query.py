"""Render the supported single-source retrieval contract without model translation.

Unknown RDF bindings return None so the existing Generate fallback remains usable.
Malformed supported declarations raise ValueError for the existing repair loop.
"""
import json
import re
from decimal import Decimal, InvalidOperation

XSD = "http://www.w3.org/2001/XMLSchema#"


def iri(value):
    if not isinstance(value, str) or not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value) or re.search(r'[\s<>"{}|^`\\]', value):
        raise ValueError("Expected an absolute RDF IRI.")
    return "<" + value + ">"


def literal(value, kind=""):
    kind = str(kind).lower()
    if kind in {"iri", "uri", "resource_iri", "object_reference"}:
        return iri(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if kind in {"number", "numeric", "integer", "float", "decimal", "double"} or isinstance(value, (int, float)):
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("Numeric filter requires a finite number.") from exc
        if not number.is_finite():
            raise ValueError("Numeric filter requires a finite number.")
        return str(number)
    if value is None or isinstance(value, (dict, list)):
        raise ValueError("Comparison requires a scalar literal; use is_null for null.")
    text = json.dumps(str(value), ensure_ascii=False)
    if kind in {"date", "datetime"}:
        text += "^^" + iri(XSD + ("date" if kind == "date" else "dateTime"))
    return text


def render_raw_query(retrieval, schema):
    details = schema.get(retrieval.get("class"), {})
    if details.get("backend") in {"sqlite", "duckdb"}:
        # Query_Spec's existing contract validation must validate SQL filters
        # too, so errors take the same repair route before Generate executes.
        from .raw_sql import render_raw_sql
        return render_raw_sql(retrieval, schema)
    if not details.get("class_iri") or not details.get("subject_field"):
        return None
    fields = retrieval.get("fields", [])
    if not isinstance(fields, list) or not fields or any(not isinstance(f, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", f) for f in fields):
        raise ValueError("Raw fields must be explicit SPARQL variable names.")
    subject = details["subject_field"]
    columns = {c["name"]: c for c in details.get("columns", []) if isinstance(c, dict) and c.get("name")}
    properties = {**{name: c.get("predicate_iri") for name, c in columns.items()}, **details.get("property_iris", {})}
    if subject not in fields or any(not properties.get(f) for f in fields if f != subject):
        return None
    optional = set(retrieval.get("optional_fields", []))
    if optional - set(fields):
        raise ValueError("Optional fields must be selected fields.")
    body = [f"?{subject} a {iri(details['class_iri'])} ."]
    for field in dict.fromkeys(fields):
        if field == subject:
            continue
        binding = f"?{subject} {iri(properties[field])} ?{field} ."
        body.append("OPTIONAL { " + binding + " }" if field in optional else binding)

    def predicate(item):
        if not isinstance(item, dict):
            raise ValueError("Filter must be a predicate object.")
        for key in ("all", "any", "not", "conditions", "filters"):
            if key not in item:
                continue
            children = item[key]
            if key == "not":
                return "!(" + predicate(children) + ")"
            if not isinstance(children, list) or not children:
                raise ValueError("Logical filters require nonempty predicate lists.")
            logic = "or" if key == "any" else "and" if key == "all" else str(item.get("logic", "and")).lower()
            if logic not in {"and", "or"}:
                raise ValueError("Unsupported logical filter.")
            return "(" + (" || " if logic == "or" else " && ").join(predicate(c) for c in children) + ")"
        field = item.get("field")
        if field not in fields:
            raise ValueError(f"Filter field is not selected: {field}")
        var = "?" + field
        op = str(item.get("operator", "=")).lower().replace("_", " ")
        op = {"eq": "=", "==": "=", "equals": "=", "ne": "!=", "<>": "!="}.get(op, op)
        value = item.get("value")
        if "value" in item and value is None:
            op = {"=": "is null", "!=": "is not null"}.get(op, op)
        if op in {"is null", "is not null"}:
            return ("!" if op == "is null" else "") + f"BOUND({var})"
        metadata = columns.get(field, {})
        types = set(metadata.get("rdf_datatypes", []))
        kind = item.get("value_type", "")
        if types == {XSD + "date"}:
            kind = "date"
        elif types and types <= {XSD + "dateTime", XSD + "dateTimeStamp"}:
            kind = "datetime"
        elif not kind:
            datatype = str(metadata.get("datatype", ""))
            kind = "iri" if datatype.startswith("object_reference") or field == subject else datatype
        if op in {"in", "not in"}:
            if not isinstance(value, list):
                raise ValueError("IN requires a literal list, not a branch reference.")
            if not value:
                return "true" if op == "not in" else "false"
            return f"{var} {op.upper()} (" + ", ".join(literal(v, kind) for v in value) + ")"
        if op == "between":
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("BETWEEN requires two endpoints.")
            return f"({var} >= {literal(value[0], kind)} && {var} <= {literal(value[1], kind)})"
        if op == "contains":
            return f"CONTAINS(STR({var}), {literal(value)})"
        if op not in {"=", "!=", "<", "<=", ">", ">="}:
            raise ValueError(f"Unsupported raw filter operator: {op}")
        return f"{var} {op} {literal(value, kind)}"

    filters = retrieval.get("filters", [])
    if not isinstance(filters, list):
        raise ValueError("Filters must be a list.")
    # Keep FILTER outside OPTIONAL. In particular IS NULL and disjunctions must
    # not make their referenced optional properties mandatory.
    body.extend("FILTER(" + predicate(item) + ")" for item in filters)
    return "SELECT " + " ".join("?" + f for f in dict.fromkeys(fields)) + " WHERE {\n  " + "\n  ".join(body) + "\n}"
