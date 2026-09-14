"""RDF schema and graph loading helpers."""

from . import common
from .common import (
    ALIAS_MAP_FILE,
    Any,
    Dict,
    FUSEKI_ENDPOINT,
    FUSEKI_METADATA_TIMEOUT_SECONDS,
    rdflib,
    re,
)
from .utils import load_rdf_id_alias_map, local_name


def schema_datatype_key(value: Any) -> str:
    # it is basically a function that takes a value (which can be of any type) and normalizes it to create a key for schema datatypes. The function first converts the value to a string, then converts it to lowercase, and finally removes any characters that are not lowercase letters or digits. This normalized key can be used to look up schema datatypes in a dictionary or other data structure.
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_schema_attribute_type(value: Any) -> str:
    # it is basically a function that takes a value (which can be of any type) and normalizes it to determine the schema attribute type. The function first converts the value to a string, strips any leading or trailing whitespace, and converts it to lowercase. It then checks if the normalized value contains certain markers that indicate whether the attribute type is numeric or categorical string. If it finds any of the numeric markers, it returns "numeric". If it finds any of the categorical string markers, it returns "categorical_string". If none of the markers are found, it returns "unknown".

    normalized = str(value or "").strip().lower()
    if any(marker in normalized for marker in ("decimal", "integer", "float", "double", "numeric", "number")):
        return "numeric"
    if any(marker in normalized for marker in ("string", "text", "date", "categorical")):
        return "categorical_string"
    return "unknown"


def extract_schema_datatypes_by_property(g: rdflib.Graph) -> Dict[str, str]:
    # this function takes an RDF graph schema as input and extracts the schema datatypes for each property in the graph. It does this by looking for triples that define the attribute type of each property, and then normalizing the attribute type to either "numeric" or "categorical_string". The function returns a dictionary that maps the normalized property names to their corresponding schema datatypes.
    attribute_name_predicates = {
        rdflib.URIRef("https://wealth.example.org/ontology/attributeName"),
        rdflib.URIRef("https://wealth.example.org/ontology/derivedName"),
    }
    attribute_type_predicate = rdflib.URIRef("https://wealth.example.org/ontology/attributeType")
    datatypes: Dict[str, str] = {}

    for attr_uri, _, attr_type in g.triples((None, attribute_type_predicate, None)):
        datatype = normalize_schema_attribute_type(attr_type)
        #this normalises to just numeric or categorical string
        if datatype == "unknown":
            continue
        for name_predicate in attribute_name_predicates:
            attr_name = g.value(attr_uri, name_predicate)
            if attr_name is not None:
                datatypes[schema_datatype_key(attr_name)] = datatype
    return datatypes


def load_rdf_knowledge_graph(schema_file: str, instance_file: str) -> Dict[str, Any]:
    """
    Loads RDF files and extracts a dictionary of classes and their dynamic properties.
    Basically, provides the schema of metadata and allows the LLM to understand the graph data structure

    Args:
        schema_file (str): Path to the RDF schema/linkage file.
        instance_file (str): Path to the Turtle (.ttl) instance data file.

    Returns:
        Dict[str, Any]: A dictionary mapping class names to their properties and descriptions.
    """

    # In the Fuseki-backed pipeline, keep rdflib out of the large instance file.
    # The full KG is hosted by Fuseki; rdflib only reads the small schema file.
    print("[SYSTEM] Loading RDF Knowledge Graph metadata from schema + Fuseki...")
    g = rdflib.Graph()
    g.parse(schema_file, format="turtle")
    schema_datatypes_by_property = extract_schema_datatypes_by_property(g)

    WM = rdflib.Namespace("http://www.semanticweb.org/openai/ontologies/2026/4/wealth-management/v3#")

    kg_metadata = {}

    #Find all Classes in the schema
    for s, p, o in g.triples((None, rdflib.RDF.type, rdflib.OWL.Class)):
        class_name = local_name(s)

        #Exclude internal/hidden classes containing double underscores
        if "__" not in class_name:
            label = str(g.value(s, rdflib.RDFS.label)) if g.value(s, rdflib.RDFS.label) else class_name
            kg_metadata[class_name] = {
                "name": label,
                "description": "",
                "columns": set(),
                "property_datatypes": {} # ADDED: Tracks if fields are numeric vs string (Fix E-05)
            }

    # Extract dynamic properties from the Fuseki-hosted instance graph.
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
    from .non_llm_operators.fuseki import execute_sparql_on_fuseki

    metadata_result = execute_sparql_on_fuseki(
        metadata_query,
        FUSEKI_ENDPOINT,
        FUSEKI_METADATA_TIMEOUT_SECONDS,
    )
    if metadata_result.get("status") != "success":
        print(f"[WARN] Fuseki metadata extraction failed: {metadata_result.get('error_message')}")
        print("[WARN] Continuing with schema classes only; Generate may have less property context.")
        
    else:
        for row in metadata_result.get("data", []):
            class_name = local_name(row.get("class", ""))
            if class_name not in kg_metadata:
                kg_metadata[class_name] = {
                    "name": class_name,
                    "description": "",
                    "columns": set(),
                    "property_datatypes": {}
                }

            prop_name = local_name(row.get("p", ""))
            if not prop_name:
                continue

            kg_metadata[class_name]["columns"].add(prop_name)
            schema_datatype = schema_datatypes_by_property.get(schema_datatype_key(prop_name))
            datatype = str(row.get("datatype", "") or "").lower()
            target_class = row.get("targetClass", "")
            if target_class:
                kg_metadata[class_name]["property_datatypes"][prop_name] = (
                    f"object_reference (points to: {local_name(target_class)})"
                )
            elif schema_datatype:
                kg_metadata[class_name]["property_datatypes"][prop_name] = schema_datatype
            elif any(marker in datatype for marker in ("decimal", "integer", "float", "double")):
                kg_metadata[class_name]["property_datatypes"][prop_name] = "numeric"
            else:
                kg_metadata[class_name]["property_datatypes"][prop_name] = "categorical_string"

    #Convert sets back to structured lists for the JSON output
    for class_name in kg_metadata:

        # --- ADDED: TAXONOMY LABELS WARNING (FIX E-04) ---
        taxonomy_classes = ["InvestmentType", "Sector", "RiskToleranceContext", "InvestmentRiskCategory", "AssetClass"]
        if class_name in taxonomy_classes:
            kg_metadata[class_name]["CRITICAL_label_property"] = "rdfs:label (or domain-specific name property like wm:investmentTypeName)"
            kg_metadata[class_name]["usage_note"] = "Always SELECT ?label via this property. NEVER return the raw node IRI."
        # -------------------------------------------------

        # Format columns list to include the extracted datatypes
        formatted_columns = []
        for prop in kg_metadata[class_name]["columns"]:
            dtype = kg_metadata[class_name]["property_datatypes"].get(prop, "unknown")
            formatted_columns.append({"name": prop, "type": "Property", "datatype": dtype})

        kg_metadata[class_name]["columns"] = formatted_columns

    print(f"[SYSTEM] Successfully loaded {len(kg_metadata)} classes with Fuseki dynamic properties.")
    return kg_metadata


def get_lightweight_table_index(kg_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Passes class names and their columns so Retrieve knows exactly where data lives."""
    index = {}
    for table, data in kg_metadata.items():
        # Extract just the column names so the LLM can search them
        index[table] = [col["name"] for col in data.get("columns", [])]
    return index


def add_cardinality_hints(kg_metadata: Dict[str, Any], rdf_graph: rdflib.Graph) -> Dict[str, Any]:
    """
    Infer generic join-risk hints from the data itself.
    No class or property names are hardcoded: repeated literal values indicate a
    property can create many-to-many expansion when used as a join key.
    """
    if rdf_graph is None:
        print("[SYSTEM] Skipping rdflib cardinality hints; Fuseki is the Scan backend.")
        return kg_metadata

    class_uri_by_name = {}
    for _, _, type_uri in rdf_graph.triples((None, rdflib.RDF.type, None)):
        class_uri_by_name.setdefault(local_name(type_uri), type_uri)

    for class_name, meta in kg_metadata.items():
        class_uri = class_uri_by_name.get(class_name)
        if class_uri is None:
            continue

        subjects = set(rdf_graph.subjects(rdflib.RDF.type, class_uri))
        subject_count = len(subjects)
        if not subject_count:
            continue

        cardinality_hints = {}
        for prop in meta.get("columns", []):
            prop_name = prop.get("name")
            if not prop_name:
                continue

            matching_predicates = {
                predicate
                for subject in subjects
                for predicate, obj in rdf_graph.predicate_objects(subject)
                if local_name(predicate) == prop_name and isinstance(obj, rdflib.Literal)
            }
            if not matching_predicates:
                continue

            value_to_subjects = {}
            subjects_with_value = set()
            for subject in subjects:
                for predicate in matching_predicates:
                    for value in rdf_graph.objects(subject, predicate):
                        if isinstance(value, rdflib.Literal):
                            value_text = str(value)
                            value_to_subjects.setdefault(value_text, set()).add(str(subject))
                            subjects_with_value.add(str(subject))

            if not value_to_subjects:
                continue

            subjects_per_value = [len(value_subjects) for value_subjects in value_to_subjects.values()]
            max_subjects_per_value = max(subjects_per_value)
            avg_subjects_per_value = sum(subjects_per_value) / len(subjects_per_value)
            coverage = len(subjects_with_value) / subject_count
            distinct_ratio = len(value_to_subjects) / max(len(subjects_with_value), 1)
            join_cardinality = "many_per_value" if max_subjects_per_value > 1 else "unique_per_value"

            cardinality_hints[prop_name] = {
                "subject_count": subject_count,
                "subjects_with_value": len(subjects_with_value),
                "distinct_values": len(value_to_subjects),
                "coverage": round(coverage, 3),
                "distinct_ratio": round(distinct_ratio, 3),
                "max_subjects_per_value": max_subjects_per_value,
                "avg_subjects_per_value": round(avg_subjects_per_value, 3),
                "join_cardinality": join_cardinality,
                "join_warning": (
                    "A flat join through this literal property can expand rows if the other "
                    "class also has many_per_value behavior for the same value domain. Prefer "
                    "direct object predicates or pre-aggregate before joining."
                    if join_cardinality == "many_per_value"
                    else "This literal property is unique per value within this class."
                ),
            }

        if cardinality_hints:
            meta["cardinality_hints"] = cardinality_hints

    return kg_metadata


def setup_rdf_graph(instance_file: str) -> Any:
    """Prepare lightweight local RDF helpers; the full instance graph lives in Fuseki."""
    print("[SYSTEM] Using Apache Jena Fuseki as the RDF instance graph. Skipping rdflib instance load.")
    common.RDF_ID_ALIAS_MAP = load_rdf_id_alias_map(ALIAS_MAP_FILE)
    if common.RDF_ID_ALIAS_MAP:
        print(f"[SYSTEM] Loaded RDF ID alias map with {len(common.RDF_ID_ALIAS_MAP)} normalized keys.")
    else:
        print(f"[WARN] RDF ID alias map not found or empty: {ALIAS_MAP_FILE}")
    return None
