"""Extract planning metadata from the ontology and physical RDF bindings.

The disk profile contains graph structure and counts, never query result rows.
Instance data is read only on a profile miss; business knowledge uses the ontology.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile
import os

import rdflib
from rdflib import RDF, RDFS, OWL, XSD, URIRef, Literal, Namespace
from rdflib.store import Store

WM = Namespace("https://wealth.example.org/ontology/")
DCT = Namespace("http://purl.org/dc/terms/")
VERSION = "rdf-profile-v1"


def file_hash(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def local_name(value):
    return str(value).rsplit("#", 1)[-1].rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def name_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


class StructuralStore(Store):
    """Turtle parser sink: keep types/property kinds, discard literal row values."""
    context_aware = False
    formula_aware = False
    graph_aware = False

    def __init__(self):
        super().__init__()
        self.records = defaultdict(lambda: {"types": set(), "properties": defaultdict(set),
                                           "sources": set()})

    def add(self, triple, context, quoted=False):
        subject, predicate, value = triple
        record = self.records[subject]
        if predicate == RDF.type:
            record["types"].add(str(value))
        elif predicate == WM.sourceTable:
            record["sources"].add(str(value))
        elif isinstance(value, Literal):
            record["properties"][str(predicate)].add(("literal", str(value.datatype or XSD.string)))
        elif isinstance(value, URIRef):
            record["properties"][str(predicate)].add(("resource", value))

    def bind(self, prefix, namespace, override=True):
        pass

    def prefix(self, namespace):
        return None

    def namespace(self, prefix):
        return None

    def namespaces(self):
        return iter(())


def instance_profile(path, cache_dir=None):
    identity = file_hash(path)
    version = file_hash(__file__)
    cached = Path(cache_dir) / (identity + ".json") if cache_dir else None
    if cached and cached.is_file():
        value = json.loads(cached.read_text(encoding="utf-8"))
        if value.get("loader_hash") == version and value.get("instance_hash") == identity:
            return value["classes"]
    store = StructuralStore()
    rdflib.Graph(store=store).parse(str(path), format="turtle")
    classes = {}
    for record in store.records.values():
        for cls in record["types"]:
            details = classes.setdefault(cls, {"count": 0, "sources": set(), "properties": {}})
            details["count"] += 1
            details["sources"].update(record["sources"])
            for predicate, kinds in record["properties"].items():
                prop = details["properties"].setdefault(predicate, {"datatypes": set(), "targets": set(), "resource": False})
                for kind, value in kinds:
                    if kind == "literal":
                        prop["datatypes"].add(value)
                    else:
                        prop["resource"] = True
                        prop["targets"].update(store.records.get(value, {}).get("types", []))
    for details in classes.values():
        details["sources"] = sorted(details["sources"])
        for prop in details["properties"].values():
            prop["datatypes"] = sorted(prop["datatypes"])
            prop["targets"] = sorted(prop["targets"])
    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cached.parent, delete=False) as handle:
            json.dump({"loader_hash": version, "instance_hash": identity, "classes": classes}, handle)
            temporary = handle.name
        os.replace(temporary, cached)
    return classes


def ontology_context(ontology, roots):
    """Copy complete related declarations from the supplied ontology only.

    Follow linked metadata nodes (attributes, derived definitions, contexts and
    blank nodes). Never read values from the instance graph for this context.
    """
    pending, visited, triples = list(roots), set(), set()
    while pending:
        subject = pending.pop()
        if subject in visited:
            continue
        visited.add(subject)
        for triple in ontology.triples((subject, None, None)):
            triples.add(tuple(term.n3() for term in triple))
            value = triple[2]
            if not isinstance(value, Literal) and any(ontology.triples((value, None, None))):
                pending.append(value)
    return [{"subject": s, "predicate": p, "object": o} for s, p, o in sorted(triples)]


def documented_metrics(ontology, primitives):
    result = []
    nodes = {node for primitive in primitives
             for relation in (WM.hasDerivedAttribute, WM.hasDerivedContext)
             for node in ontology.objects(primitive, relation)}
    for node in sorted(nodes, key=str):
        result.append({"name": str(ontology.value(node, WM.derivedName) or
                                   ontology.value(node, WM.attributeName) or local_name(node)),
                       "description": str(ontology.value(node, DCT.description) or ""),
                       "definition": ontology_context(ontology, [node])})
    return result


def load_kg_metadata(schema_file, instance_file, cache_dir=None):
    ontology = rdflib.Graph().parse(str(schema_file), format="turtle")
    profile = instance_profile(instance_file, cache_dir)
    declared = set(ontology.subjects(RDF.type, OWL.Class)) | set(ontology.subjects(RDF.type, RDFS.Class))
    primitives = {str(ontology.value(subject, WM.primitiveId)): subject
                  for subject in ontology.subjects(RDF.type, WM.Primitive)}
    result = {}
    internal = {WM.Primitive, WM.PrimitiveAttribute, WM.DerivedAttribute, WM.ContextValue, WM.DerivedContext}
    for cls in sorted(declared - internal, key=str):
        observed = profile.get(str(cls), {})
        if not observed.get("count"):
            continue
        name = local_name(cls)
        if name in result:
            raise ValueError(f"Ambiguous class name: {name}")
        sources = observed.get("sources", [])
        docs = [primitives[source] for source in sources if source in primitives]
        columns = [{"name": "subject_iri", "datatype": "resource_iri", "type": "Subject"}]
        properties = {}
        attributes = defaultdict(list)
        for doc in docs:
            for attr in ontology.objects(doc, WM.hasPrimitiveAttribute):
                attributes[name_key(ontology.value(attr, WM.attributeName))].append(attr)
        for predicate, prop in sorted(observed.get("properties", {}).items()):
            field = "rdfs_label" if predicate == str(RDFS.label) else local_name(predicate)
            if field in properties or field == "subject_iri":
                raise ValueError(f"Ambiguous property name on {name}: {field}")
            types = prop["datatypes"]
            targets = [local_name(target) for target in prop["targets"]]
            if prop["resource"] and types:
                raise ValueError(f"Mixed resource/literal property on {name}: {field}")
            dtype = ("object_reference (points to: " + ", ".join(targets) + ")" if targets else
                     "resource_iri" if prop["resource"] else
                     "numeric" if types and all(local_name(t) in {"decimal", "integer", "int", "long", "double", "float", "short", "nonNegativeInteger", "positiveInteger"} for t in types) else
                     "boolean" if types == [str(XSD.boolean)] else "categorical_string")
            column = {"name": field, "datatype": dtype, "predicate_iri": predicate,
                      "rdf_datatypes": types, "target_classes": targets}
            attrs = attributes.get(name_key(field), [])
            if len(attrs) > 1:
                raise ValueError(f"Ambiguous ontology attribute mapping: {name}.{field}")
            if attrs:
                attr = attrs[0]
                column.update(ontology_attribute=str(ontology.value(attr, WM.attributeName)),
                              description=str(ontology.value(attr, DCT.description) or ""),
                              synonyms=sorted(str(v) for v in ontology.objects(attr, WM.synonym)),
                              allowed_values=sorted(str(v) for v in ontology.objects(attr, WM.allowedValue)))
                for flag in ("filterable", "aggregatable", "searchable"):
                    value = ontology.value(attr, WM[flag])
                    if value is not None:
                        column[flag] = value.toPython()
            columns.append(column)
            properties[field] = predicate
        result[name] = {"name": str(ontology.value(cls, RDFS.label) or name), "backend": "rdf",
                        "class_iri": str(cls), "subject_field": "subject_iri", "columns": columns,
                        "property_iris": properties, "source_tables": sources,
                        "description": "\n".join(str(ontology.value(doc, DCT.description) or "") for doc in docs),
                        "business_purpose": "\n".join(str(ontology.value(doc, WM.businessPurpose) or "") for doc in docs),
                        "documentation_source": "ontology", "instance_count": observed["count"],
                        "derived_metrics": documented_metrics(ontology, docs),
                        "ontology_metadata": ontology_context(ontology, [cls, *docs,
                             *(URIRef(predicate) for predicate in properties.values())]),
                        "usage_note": "Use exact class/predicate IRIs. subject_iri is record identity; links carry full IRIs. "
                                      "Keep optional properties optional. Labels and literal IDs are not resource IRIs. "
                                      "Multi-valued properties can expand rows; preserve the declared calculation grain."}
        if "rdfs_label" in properties:
            result[name]["label_field"] = "rdfs_label"
    if not result:
        raise ValueError("Ontology has no populated classes in the supplied instance KG.")
    return result


def get_lightweight_table_index(metadata):
    return {name: {"description": details.get("description", ""), "class_iri": details.get("class_iri", ""),
                   "columns": details["columns"], "source_tables": details.get("source_tables", [])}
            for name, details in metadata.items()}
