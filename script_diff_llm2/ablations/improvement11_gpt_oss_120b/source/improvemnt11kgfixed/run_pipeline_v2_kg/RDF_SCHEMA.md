# RDF planning metadata

`kg_metadata.load_kg_metadata(ontology, instance_file, cache_dir)` returns one entry
per populated domain class. Each entry contains `class_iri`, `subject_field`,
`property_iris`, `columns`, descriptions, source primitive IDs and relationship
targets. `subject_iri` is the actual typed RDF subject, not a predicate.

V3 also supplies `ontology_metadata`: complete relevant triples from the supplied
ontology for the class, its properties and linked primitive metadata. This includes
attributes, documented examples, derived definitions and context nodes without
filtering their content. `derived_metrics` exposes documented derived names and
definitions. It does not infer missing formulas. The physical KG profile remains
separate; literal instance values never enter this documentation context.

Columns use the physical predicate name, for example `currentValue`; the
`ontology_attribute` annotation preserves the documented `current_value` name.
Model responses may use the exact declared class IRI, predicate IRI, source
primitive ID or documented attribute name. Contract normalization resolves these
to schema dictionary/column keys only when the mapping is unambiguous. It never
matches a foreign namespace by local name or changes filter literals. Genuine
source switches and unknown fields remain validation errors.
Annotations are matched only to an unambiguous normalized name within a primitive
identified by the graph's `sourceTable`. RDF datatypes come from actual bindings.
Undocumented constraints and formulas remain unspecified.

Retrieval contracts select one class, explicit fields, identity keys, optional
fields and raw filters. Every RDF property is optional unless the contract
explicitly requires its presence. Missing properties produce `None` in result
rows. Link values remain full IRIs. Numeric and boolean literals become native
Python values; dates retain ISO lexical values.

Multiple values on a property can expand result rows. Neither generation nor
scan adds DISTINCT, limits or aggregation. The declared final Python plan must
choose identity keys and aggregation grain intentionally.

Business knowledge is compiled from exact ontology, domain and rule sources.
Its schema payload contains RDF bindings and ontology annotations, with no
live instance counts, row values, local input paths or observed sample rows. Supplied
source documents and their examples remain available unchanged. Source and schema
hashes protect cache reuse; ontology source changes always invalidate the cache.
