"""Small real RDF fixtures shared by retrieval regression tests."""
import json
import rdflib
from rdflib import RDF, URIRef, Literal, XSD


def schema_for(name, fields):
    columns = [{"name": "subject_iri", "datatype": "resource_iri"}]
    for field, kind in fields.items():
        types = [str(XSD.date)] if kind == "date" else []
        columns.append({"name": field, "datatype": "categorical_string" if kind == "date" else kind,
                        "predicate_iri": "urn:field:" + field, "rdf_datatypes": types})
    return {name: {"backend": "rdf", "class_iri": "urn:class:" + name,
                   "subject_field": "subject_iri", "columns": columns}}


def graph_for(name, rows):
    graph = rdflib.Graph()
    for index, row in enumerate(rows):
        subject = URIRef("urn:row:" + str(index))
        graph.add((subject, RDF.type, URIRef("urn:class:" + name)))
        for field, value in row.items():
            if value is not None:
                datatype = XSD.date if field == "date" else None
                graph.add((subject, URIRef("urn:field:" + field), Literal(value, datatype=datatype)))
    return graph


def execute_local(graph, query):
    from support import load
    payload = json.loads(graph.query(query).serialize(format="json"))
    return load("kg_backend").parse_sparql_json(payload)[0]
