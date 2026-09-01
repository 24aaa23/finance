import difflib
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

import rdflib


def schema_datatype_key(value: Any) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_schema_attribute_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if any(marker in normalized for marker in ("decimal", "integer", "float", "double", "numeric", "number")):
        return "numeric"
    if any(marker in normalized for marker in ("string", "text", "date", "categorical")):
        return "categorical_string"
    return "unknown"


def extract_schema_datatypes_by_property(graph: rdflib.Graph) -> dict[str, str]:
    attribute_name_predicates = {
        rdflib.URIRef("https://wealth.example.org/ontology/attributeName"),
        rdflib.URIRef("https://wealth.example.org/ontology/derivedName"),
    }
    attribute_type_predicate = rdflib.URIRef("https://wealth.example.org/ontology/attributeType")
    datatypes: dict[str, str] = {}
    for attr_uri, _, attr_type in graph.triples((None, attribute_type_predicate, None)):
        datatype = normalize_schema_attribute_type(attr_type)
        if datatype == "unknown":
            continue
        for name_predicate in attribute_name_predicates:
            attr_name = graph.value(attr_uri, name_predicate)
            if attr_name is not None:
                datatypes[schema_datatype_key(attr_name)] = datatype
    return datatypes


def local_name(uri: Any) -> str:
    text = str(uri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rstrip("/").rsplit("/", 1)[-1]


def parse_fuseki_sparql_json(payload: dict[str, Any]) -> list[dict[str, str]]:
    if "boolean" in payload:
        return [{"boolean": str(bool(payload.get("boolean"))).lower()}]

    vars_order = payload.get("head", {}).get("vars", [])
    bindings = payload.get("results", {}).get("bindings", [])
    data = []
    for binding in bindings:
        row_dict = {}
        for var in vars_order:
            value = binding.get(var, {})
            if isinstance(value, dict):
                row_dict[str(var)] = str(value.get("value", ""))
            else:
                row_dict[str(var)] = ""
        data.append(row_dict)
    return data


def execute_sparql_on_fuseki(sparql_query: str, endpoint: str, timeout_seconds: float) -> dict[str, Any]:
    try:
        request_body = urllib.parse.urlencode({"query": sparql_query}).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=request_body,
            method="POST",
            headers={
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
        payload = json.loads(response_body)
        data = parse_fuseki_sparql_json(payload)
        return {"status": "success", "data": data, "row_count": len(data), "sparql": sparql_query}
    except socket.timeout:
        return {"status": "error", "error_message": f"Fuseki SPARQL execution timed out after {timeout_seconds:g} seconds.", "failed_sparql": sparql_query, "timeout_seconds": timeout_seconds}
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        return {"status": "error", "error_message": f"Fuseki HTTP {exc.code}: {error_body or str(exc)}", "failed_sparql": sparql_query}
    except urllib.error.URLError as exc:
        return {"status": "error", "error_message": f"Fuseki connection error: {exc.reason}", "failed_sparql": sparql_query}
    except json.JSONDecodeError as exc:
        return {"status": "error", "error_message": f"Fuseki returned non-JSON SPARQL results: {exc}", "failed_sparql": sparql_query}
    except Exception as exc:
        return {"status": "error", "error_message": str(exc), "failed_sparql": sparql_query}


def check_fuseki_health(endpoint: str = "http://127.0.0.1:3030/wealth/query", timeout_seconds: float = 10.0) -> None:
    result = execute_sparql_on_fuseki("ASK {\n  ?s ?p ?o .\n}\n", endpoint, timeout_seconds)
    if result.get("status") == "success":
        print("[SYSTEM] Fuseki health check passed.")
        return
    raise RuntimeError(
        "Fuseki is not reachable or did not execute the health check. "
        f"Endpoint: {endpoint}. Error: {result.get('error_message')}. "
        "Start Fuseki first and verify the /wealth dataset is loaded."
    )


def collect_fuseki_graph_terms(cache: set[str] | None, endpoint: str, timeout_seconds: float, logger: Callable[[str], None]) -> set[str]:
    if cache is not None:
        return cache
    query = """
SELECT DISTINCT ?term
WHERE {
  {
    ?s ?term ?o .
  }
  UNION
  {
    ?s ?p ?term .
  }
  FILTER(isIRI(?term))
  FILTER(STRSTARTS(STR(?term), "https://wealth.example.org/ontology/"))
}
"""
    result = execute_sparql_on_fuseki(query, endpoint, timeout_seconds)
    if result.get("status") != "success":
        logger(f"[WARN] Fuseki term collection failed: {result.get('error_message')}")
        return set()
    return {local_name(row.get("term", "")) for row in result.get("data", []) if row.get("term")}


def extract_ex_terms_from_sparql(sparql: str) -> list[str]:
    import re

    body = re.sub(r"PREFIX\s+\w+:\s*<[^>]+>", "", sparql or "", flags=re.I)
    return sorted(set(re.findall(r"\bwm:([A-Za-z_][A-Za-z0-9_-]*)\b", body)))


def validate_sparql_terms(sparql: str, known_terms: set[str]) -> dict[str, Any]:
    used_terms = extract_ex_terms_from_sparql(sparql)
    if not known_terms:
        return {
            "is_valid": True,
            "used_terms": used_terms,
            "unknown_terms": [],
            "suggestions": {},
            "warning": "Known graph terms could not be collected; skipped strict term validation.",
        }
    unknown_terms = [term for term in used_terms if term not in known_terms]
    suggestions = {
        term: difflib.get_close_matches(term, sorted(known_terms), n=5, cutoff=0.55)
        for term in unknown_terms
    }
    return {"is_valid": not unknown_terms, "used_terms": used_terms, "unknown_terms": unknown_terms, "suggestions": suggestions}


def get_lightweight_table_index(kg_metadata: dict[str, Any]) -> dict[str, Any]:
    return {table: [col["name"] for col in data.get("columns", [])] for table, data in kg_metadata.items()}


def load_rdf_knowledge_graph(
    schema_file: str,
    endpoint: str,
    metadata_timeout_seconds: float,
) -> dict[str, Any]:
    print("[SYSTEM] Loading RDF Knowledge Graph metadata from schema + Fuseki...")
    graph = rdflib.Graph()
    graph.parse(schema_file, format="turtle")
    schema_datatypes_by_property = extract_schema_datatypes_by_property(graph)

    kg_metadata = {}
    for subject, _, _ in graph.triples((None, rdflib.RDF.type, rdflib.OWL.Class)):
        class_name = local_name(subject)
        if "__" in class_name:
            continue
        label = str(graph.value(subject, rdflib.RDFS.label)) if graph.value(subject, rdflib.RDFS.label) else class_name
        kg_metadata[class_name] = {"name": label, "description": "", "columns": set(), "property_datatypes": {}}

    metadata_query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT ?class ?p ?datatype ?targetClass
WHERE {
  ?s rdf:type ?class .
  ?s ?p ?o .
  FILTER(STRSTARTS(STR(?class), "https://wealth.example.org/ontology/"))
  FILTER(!STRSTARTS(STR(?p), "http://www.w3.org/"))
  OPTIONAL {
    FILTER(isLiteral(?o))
    BIND(DATATYPE(?o) AS ?datatype)
  }
  OPTIONAL {
    FILTER(isIRI(?o))
    ?o rdf:type ?targetClass .
    FILTER(STRSTARTS(STR(?targetClass), "https://wealth.example.org/ontology/"))
  }
}
"""
    metadata_result = execute_sparql_on_fuseki(metadata_query, endpoint, metadata_timeout_seconds)
    if metadata_result.get("status") != "success":
        print(f"[WARN] Fuseki metadata extraction failed: {metadata_result.get('error_message')}")
        print("[WARN] Continuing with schema classes only; Generate may have less property context.")
    else:
        for row in metadata_result.get("data", []):
            class_name = local_name(row.get("class", ""))
            kg_metadata.setdefault(class_name, {"name": class_name, "description": "", "columns": set(), "property_datatypes": {}})
            prop_name = local_name(row.get("p", ""))
            if not prop_name:
                continue
            kg_metadata[class_name]["columns"].add(prop_name)
            schema_datatype = schema_datatypes_by_property.get(schema_datatype_key(prop_name))
            datatype = str(row.get("datatype", "") or "").lower()
            target_class = row.get("targetClass", "")
            if target_class:
                kg_metadata[class_name]["property_datatypes"][prop_name] = f"object_reference (points to: {local_name(target_class)})"
            elif schema_datatype:
                kg_metadata[class_name]["property_datatypes"][prop_name] = schema_datatype
            elif any(marker in datatype for marker in ("decimal", "integer", "float", "double")):
                kg_metadata[class_name]["property_datatypes"][prop_name] = "numeric"
            else:
                kg_metadata[class_name]["property_datatypes"][prop_name] = "categorical_string"

    taxonomy_classes = {"InvestmentType", "Sector", "RiskToleranceContext", "InvestmentRiskCategory", "AssetClass"}
    for class_name, details in kg_metadata.items():
        formatted_columns = []
        for prop in details["columns"]:
            dtype = details["property_datatypes"].get(prop, "unknown")
            formatted_columns.append({"name": prop, "type": "Property", "datatype": dtype})
        details["columns"] = formatted_columns
        if class_name in taxonomy_classes:
            details["CRITICAL_label_property"] = "rdfs:label (or domain-specific name property like wm:investmentTypeName)"
            details["usage_note"] = "Always SELECT ?label via this property. NEVER return the raw node IRI."

    print(f"[SYSTEM] Successfully loaded {len(kg_metadata)} classes with Fuseki dynamic properties.")
    return kg_metadata
