import os
import json
import rdflib
from typing import Dict, Any
from code.operators.base import local_name
from code.config import ALIAS_MAP_FILE
from code.kg.alias import load_rdf_id_alias_map

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

    #Parsing the files
    print("[SYSTEM] Loading RDF Knowledge Graph...")
    g = rdflib.Graph()
    g.parse(schema_file, format="turtle")
    g.parse(instance_file, format="turtle")

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

    #Extract properties directly from the INSTANCES!
    for s, p, o in g:
        # Ignore standard w3 metadata properties immediately to save time
        if "www.w3.org" in str(p):
            continue

        # O(1) direct lookup for the subject's type
        for s_type in g.objects(subject=s, predicate=rdflib.RDF.type):
            class_name = local_name(s_type)

            if class_name in kg_metadata:
                prop_name = local_name(p)
                kg_metadata[class_name]["columns"].add(prop_name)

                # --- DATATYPE & EDGE EXTRACTION ---
                if isinstance(o, rdflib.Literal):
                    # Check if the literal is a number
                    if o.datatype and ("decimal" in str(o.datatype).lower() or "integer" in str(o.datatype).lower() or "float" in str(o.datatype).lower()):
                        kg_metadata[class_name]["property_datatypes"][prop_name] = "numeric"
                    else:
                        kg_metadata[class_name]["property_datatypes"][prop_name] = "categorical_string"

                elif isinstance(o, rdflib.URIRef):
                    # --- NEW GRAPH TRAVERSAL FIX ---
                    # Instead of just saying "object_reference", tell the LLM exactly which Class this links to!
                    target_classes = list(g.objects(subject=o, predicate=rdflib.RDF.type))
                    if target_classes:
                        target_class_name = local_name(target_classes[0])
                        kg_metadata[class_name]["property_datatypes"][prop_name] = f"object_reference (points to: {target_class_name})"
                    else:
                        kg_metadata[class_name]["property_datatypes"][prop_name] = "object_reference"
                    # ---------------------------------------------

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

    print(f"[SYSTEM] Successfully loaded {len(kg_metadata)} classes with dynamic properties.")
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

def setup_rdf_graph(instance_file: str) -> rdflib.Graph:
    """Loads the RDF instance data into an executable graph database."""
    print("[SYSTEM] Loading RDF Instance Graph for SPARQL queries...")
    g = rdflib.Graph()
    g.parse(instance_file, format="turtle") #or "xml" depending on the file. Change it accordingly
    global RDF_ID_ALIAS_MAP
    RDF_ID_ALIAS_MAP = load_rdf_id_alias_map(ALIAS_MAP_FILE)
    if RDF_ID_ALIAS_MAP:
        print(f"[SYSTEM] Loaded RDF ID alias map with {len(RDF_ID_ALIAS_MAP)} normalized keys.")
    else:
        print(f"[WARN] RDF ID alias map not found or empty: {ALIAS_MAP_FILE}")
    return g

