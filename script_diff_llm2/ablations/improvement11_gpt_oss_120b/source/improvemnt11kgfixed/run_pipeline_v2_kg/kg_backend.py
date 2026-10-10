"""Read-only SPARQL transport and typed result conversion for Fuseki."""
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from rdflib.plugins.sparql.parser import parseQuery
from pyparsing import ParseResults

XSD = "http://www.w3.org/2001/XMLSchema#"


def binding_value(binding):
    if not binding:
        return None
    value = binding["value"]
    datatype = binding.get("datatype", "")
    if binding.get("type") == "uri":
        return value
    kind = datatype.removeprefix(XSD) if datatype.startswith(XSD) else ""
    if kind in {"integer", "int", "long", "short", "byte", "nonNegativeInteger", "positiveInteger", "unsignedInt", "unsignedLong"}:
        return int(value)
    if kind in {"decimal", "double", "float"}:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite RDF numeric result.")
        return number
    if kind == "boolean":
        if value not in {"true", "false", "1", "0"}:
            raise ValueError("Invalid RDF boolean result.")
        return value in {"true", "1"}
    # ISO date/dateTime lexical values remain usable by Date_Extract and JSON.
    return value


def parse_sparql_json(payload):
    if "boolean" in payload:
        return [{"boolean": bool(payload["boolean"])}], ["boolean"]
    fields = payload["head"]["vars"]
    return [{field: binding_value(row.get(field)) for field in fields}
            for row in payload["results"]["bindings"]], fields


def validate_read_query(query):
    parsed = parseQuery(query)
    if parsed[1].name not in {"SelectQuery", "AskQuery"}:
        raise ValueError("Only read-only SELECT/ASK queries are supported.")

    def walk(value):
        if getattr(value, "name", "") == "ServiceGraphPattern":
            raise ValueError("External SERVICE queries are not supported.")
        if isinstance(value, (list, tuple, ParseResults)):
            for child in value:
                walk(child)
        elif hasattr(value, "values"):
            for child in value.values():
                walk(child)
    walk(parsed)


def execute_sparql(query, endpoint, timeout_seconds=60):
    try:
        validate_read_query(query)
        request = urllib.request.Request(endpoint, method="POST",
            data=urllib.parse.urlencode({"query": query}).encode("utf-8"),
            headers={"Accept": "application/sparql-results+json",
                     "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"})
        with urllib.request.urlopen(request, timeout=timeout_seconds or None) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows, fields = parse_sparql_json(payload)
        return {"status": "success", "data": rows, "columns": fields,
                "row_count": len(rows), "sparql": query}
    except Exception as error:
        return {"status": "error", "error_message": f"SPARQL execution failed: {error}",
                "failed_sparql": query, "data": [], "columns": [], "row_count": 0}


def check_kg_health(endpoint, metadata, timeout_seconds=60):
    values = " ".join("<" + details["class_iri"] + ">" for details in metadata.values())
    query = "SELECT ?class (COUNT(DISTINCT ?s) AS ?n) WHERE { VALUES ?class { " + values + " } ?s a ?class } GROUP BY ?class"
    result = execute_sparql(query, endpoint, timeout_seconds)
    if result["status"] != "success":
        raise RuntimeError(result["error_message"] + ". Run start_fuseki.cmd from improvemnt11kgfixed first.")
    observed = {row["class"]: row["n"] for row in result["data"]}
    mismatches = [name for name, details in metadata.items()
                  if observed.get(details["class_iri"], 0) != details["instance_count"]]
    if mismatches:
        raise RuntimeError("Endpoint class populations differ from the supplied KG: " + ", ".join(mismatches))
