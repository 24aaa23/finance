"""Expose existing source documentation to planners; do not invent metric rules."""
import re

import rdflib


def attach_schema_annotations(graph, metadata):
    wm = rdflib.Namespace("https://wealth.example.org/ontology/")
    description = rdflib.URIRef("http://purl.org/dc/terms/description")
    key = lambda value: re.sub(r"[^a-z0-9]", "", str(value).lower())
    primitives = list(graph.subjects(rdflib.RDF.type, wm.Primitive))
    by_id = {str(graph.value(p, wm.primitiveId)): p for p in primitives}
    for name, details in metadata.items():
        sources = {by_id[s] for s in details.get("source_tables", []) if s in by_id}
        if not sources:
            # Exact normalized labels/names only. Multiple matches remain
            # unresolved rather than transferring one source's field meaning.
            names = {key(name), key(details.get("name", ""))} - {""}
            sources = {p for p in primitives if names & {
                key(v) for prop in (wm.primitiveName, rdflib.RDFS.label) for v in graph.objects(p, prop)}}
        if len(sources) != 1:
            continue
        source = next(iter(sources))
        details["documentation_source"] = str(source)
        details["description"] = str(graph.value(source, description) or "")
        attrs = {}
        for attr in graph.objects(source, wm.hasPrimitiveAttribute):
            attr_name = graph.value(attr, wm.attributeName)
            if attr_name is not None:
                attrs.setdefault(key(attr_name), []).append(attr)
        for column in details.get("columns", []):
            if not isinstance(column, dict):
                continue
            matches = attrs.get(key(column.get("source_column") or column.get("name", "")), [])
            if len(matches) != 1:
                continue
            attr = matches[0]
            column["description"] = str(graph.value(attr, description) or "")
            column["synonyms"] = sorted(str(v) for v in graph.objects(attr, wm.synonym))
            column["allowed_values"] = sorted(str(v) for v in graph.objects(attr, wm.allowedValue))
        details["derived_metrics"] = [{
            "name": str(graph.value(attr, wm.derivedName) or graph.value(attr, rdflib.RDFS.label) or ""),
            "description": str(graph.value(attr, description) or ""),
        } for attr in graph.objects(source, wm.hasDerivedAttribute)]
    return metadata
