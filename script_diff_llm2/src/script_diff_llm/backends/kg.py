import difflib
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

import rdflib


STANDARD_NAMESPACE_PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "owl": "http://www.w3.org/2002/07/owl#",
}


def is_standard_namespace(uri: str) -> bool:
    text = str(uri or "")
    return text.startswith("http://www.w3.org/") or text.startswith("https://www.w3.org/")


def schema_datatype_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_schema_attribute_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if any(marker in normalized for marker in ("decimal", "integer", "float", "double", "numeric", "number")):
        return "numeric"
    if any(marker in normalized for marker in ("string", "text", "date", "categorical")):
        return "categorical_string"
    return "unknown"


def extract_schema_datatypes_by_property(graph: rdflib.Graph) -> dict[str, str]:
    predicates = {predicate for _, predicate, _ in graph}
    attribute_name_predicates = {
        predicate
        for predicate in predicates
        if local_name(predicate) in {"attributeName", "derivedName"}
    }
    attribute_type_predicates = [
        predicate for predicate in predicates if local_name(predicate) == "attributeType"
    ]
    datatypes: dict[str, str] = {}
    for attribute_type_predicate in attribute_type_predicates:
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


def load_rdf_prefix_map(schema_file: str) -> dict[str, str]:
    graph = rdflib.Graph()
    graph.parse(schema_file, format="turtle")
    prefixes = {
        str(prefix): str(namespace)
        for prefix, namespace in graph.namespaces()
        if prefix
    }
    for prefix, namespace in STANDARD_NAMESPACE_PREFIXES.items():
        prefixes.setdefault(prefix, namespace)
    return prefixes


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
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT ?term
WHERE {
  {
    ?s rdf:type ?term .
  }
  UNION
  {
    ?s ?term ?o .
  }
  UNION
  {
    ?s ?p ?o .
    FILTER(isIRI(?o))
    ?o rdf:type ?term .
  }
  FILTER(isIRI(?term))
  FILTER(!STRSTARTS(STR(?term), "http://www.w3.org/"))
  FILTER(!STRSTARTS(STR(?term), "https://www.w3.org/"))
}
"""
    result = execute_sparql_on_fuseki(query, endpoint, timeout_seconds)
    if result.get("status") != "success":
        logger(f"[WARN] Fuseki term collection failed: {result.get('error_message')}")
        return set()
    return {str(row["term"]) for row in result.get("data", []) if row.get("term")}


def extract_ex_terms_from_sparql(sparql: str) -> list[str]:
    body = re.sub(r"PREFIX\s+\w+:\s*<[^>]+>", "", sparql or "", flags=re.I)
    standard_prefixes = {"rdf", "rdfs", "xsd", "owl", "skos"}
    terms = set()
    for prefix, term in re.findall(r"\b([A-Za-z][A-Za-z0-9_-]*):([A-Za-z_][A-Za-z0-9_-]*)\b", body):
        if prefix.lower() in standard_prefixes:
            continue
        terms.add(term)
    return sorted(terms)


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
    known_names = {local_name(term) for term in known_terms}
    unknown_terms = [term for term in used_terms if term not in known_names]
    # Local names alone cannot distinguish two different RDF vocabularies.
    # Resolve prefixes with the SPARQL parser and check predicate/class URIs.
    known_uris = {term for term in known_terms if "://" in term}
    if known_uris:
        from rdflib.plugins.sparql.algebra import translateQuery
        from rdflib.plugins.sparql.parser import parseQuery

        def vocabulary_uris(value):
            if isinstance(value, dict):
                for subject, predicate, obj in (value["triples"] if "triples" in value else []):
                    if predicate == rdflib.RDF.type:
                        if isinstance(obj, rdflib.URIRef):
                            yield str(obj)
                    elif isinstance(predicate, rdflib.URIRef):
                        yield str(predicate)
                for child in value.values():
                    yield from vocabulary_uris(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    yield from vocabulary_uris(child)

        try:
            algebra = translateQuery(parseQuery(sparql)).algebra
            unknown_terms.extend(sorted({
                uri for uri in vocabulary_uris(algebra)
                if not is_standard_namespace(uri) and uri not in known_uris
            }))
        except Exception:
            # Syntax validation is owned by Pre_Scan_Validate. Do not mask its
            # diagnostic with a parser-specific exception at this stage.
            pass
    unknown_terms = sorted(set(unknown_terms))
    suggestions = {
        term: difflib.get_close_matches(term, sorted(known_uris or known_names), n=5, cutoff=0.55)
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
        description = graph.value(subject, rdflib.RDFS.comment)
        kg_metadata[class_name] = {"name": label, "uri": str(subject), "description": str(description or ""), "columns": set(), "property_datatypes": {}, "property_uris": {}}

    metadata_query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT ?class ?p ?datatype ?targetClass
WHERE {
  ?s rdf:type ?class .
  ?s ?p ?o .
  FILTER(?p != rdf:type)
  FILTER(!STRSTARTS(STR(?class), "http://www.w3.org/"))
  FILTER(!STRSTARTS(STR(?class), "https://www.w3.org/"))
  BIND(IF(isLiteral(?o), DATATYPE(?o), "") AS ?datatype)
  OPTIONAL {
    FILTER(isIRI(?o))
    ?o rdf:type ?targetClass .
    FILTER(!STRSTARTS(STR(?targetClass), "http://www.w3.org/"))
    FILTER(!STRSTARTS(STR(?targetClass), "https://www.w3.org/"))
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
            kg_metadata[class_name]["uri"] = str(row.get("class", ""))
            prop_name = local_name(row.get("p", ""))
            if not prop_name:
                continue
            property_uri = str(row.get("p", ""))
            ambiguous = kg_metadata[class_name].setdefault("ambiguous_property_names", [])
            mapping = kg_metadata[class_name].setdefault("property_uris", {})
            if prop_name in ambiguous:
                prop_name = property_uri
            elif prop_name in mapping and mapping[prop_name] != property_uri:
                # Preserve both namespaces rather than merging their evidence.
                ambiguous.append(prop_name)
                previous_uri = mapping[prop_name]
                kg_metadata[class_name]["columns"].discard(prop_name)
                kg_metadata[class_name]["columns"].add(previous_uri)
                for key in ("property_uris", "property_datatypes", "literal_datatypes"):
                    values = kg_metadata[class_name].get(key, {})
                    if prop_name in values:
                        values[previous_uri] = values.pop(prop_name)
                prop_name = property_uri
            kg_metadata[class_name]["columns"].add(prop_name)
            kg_metadata[class_name].setdefault("property_uris", {})[prop_name] = str(row.get("p", ""))
            schema_datatype = schema_datatypes_by_property.get(schema_datatype_key(prop_name))
            datatype = str(row.get("datatype", "") or "").lower()
            if datatype:
                observed = kg_metadata[class_name].setdefault("literal_datatypes", {}).setdefault(prop_name, [])
                actual_datatype = str(row.get("datatype"))
                if actual_datatype not in observed:
                    observed.append(actual_datatype)
            target_class = row.get("targetClass", "")
            if target_class:
                kg_metadata[class_name]["property_datatypes"][prop_name] = f"object_reference (points to: {local_name(target_class)})"
            elif schema_datatype:
                kg_metadata[class_name]["property_datatypes"][prop_name] = schema_datatype
            elif any(marker in datatype for marker in ("decimal", "integer", "float", "double")):
                kg_metadata[class_name]["property_datatypes"][prop_name] = "numeric"
            else:
                kg_metadata[class_name]["property_datatypes"][prop_name] = "categorical_string"

    # Profile complete small text domains in one bounded endpoint request.
    # Encode values before concatenation: source strings may contain separators.
    value_query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?class ?p (COUNT(DISTINCT STR(?value)) AS ?valueCount)
       (GROUP_CONCAT(DISTINCT ENCODE_FOR_URI(STR(?value)); separator="|") AS ?encodedValues)
WHERE {
  { SELECT ?class ?p WHERE {
      ?record a ?class ; ?p ?v .
      FILTER(isLiteral(?v))
      FILTER(DATATYPE(?v) IN (xsd:string, rdf:langString))
      FILTER(!STRSTARTS(STR(?class), "http://www.w3.org/"))
      FILTER(?p != rdf:type)
    } GROUP BY ?class ?p
      HAVING(COUNT(DISTINCT STR(?v)) <= 32 && MAX(STRLEN(STR(?v))) <= 256)
  }
  ?record a ?class ; ?p ?value .
  FILTER(isLiteral(?value))
  FILTER(DATATYPE(?value) IN (xsd:string, rdf:langString))
} GROUP BY ?class ?p
LIMIT 1000
"""
    value_result = execute_sparql_on_fuseki(value_query, endpoint, metadata_timeout_seconds)
    if value_result.get("status") == "success":
        from urllib.parse import unquote
        for row in value_result.get("data", []):
            details = kg_metadata.get(local_name(row.get("class", "")))
            prop = local_name(row.get("p", ""))
            if details and prop in details.get("ambiguous_property_names", []):
                prop = str(row.get("p", ""))
            if not details or details.get("property_uris", {}).get(prop) != str(row.get("p", "")):
                continue
            encoded = row.get("encodedValues")
            try:
                count = int(row.get("valueCount"))
                values = sorted(set(unquote(v) for v in str(encoded).split("|")))
            except (ValueError, TypeError):
                continue
            if encoded is not None and len(values) == count and 0 < count <= 32 and all(len(v) <= 256 for v in values):
                details.setdefault("allowed_values", {})[prop] = values
    else:
        print("[WARN] RDF text-domain profiling unavailable; continuing without value evidence.")

    taxonomy_markers = ("type", "category", "segment", "sector", "class", "status", "tier")
    for class_name, details in kg_metadata.items():
        formatted_columns = []
        for prop in details["columns"]:
            dtype = details["property_datatypes"].get(prop, "unknown")
            column = {"name": prop, "uri": details.get("property_uris", {}).get(prop), "type": "Property", "datatype": dtype}
            uri = column.get("uri")
            if uri:
                comment = graph.value(rdflib.URIRef(uri), rdflib.RDFS.comment)
                label = graph.value(rdflib.URIRef(uri), rdflib.RDFS.label)
                if comment:
                    column["description"] = str(comment)
                if label:
                    column["label"] = str(label)
            if prop in details.get("allowed_values", {}):
                column.update(allowed_values=details["allowed_values"][prop], allowed_values_complete=True)
            formatted_columns.append(column)
        details["columns"] = formatted_columns
        if any(marker in class_name.lower() for marker in taxonomy_markers):
            details["CRITICAL_label_property"] = "Use the schema-supported human-readable label/name property (for example rdfs:label or a domain-specific name field)."
            details["usage_note"] = "Always SELECT ?label via this property. NEVER return the raw node IRI."

    print(f"[SYSTEM] Successfully loaded {len(kg_metadata)} classes with Fuseki dynamic properties.")
    return kg_metadata
