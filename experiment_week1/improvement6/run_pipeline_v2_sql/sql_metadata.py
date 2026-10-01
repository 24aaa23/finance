"""Combine physical SQL schema with the same business documentation used by KG."""
from pathlib import Path

import rdflib

from .schema_annotations import attach_schema_annotations
from .sqlite_backend import load_sqlite_schema


def load_sqlite_metadata(db_path, schema_file):
    """Annotate existing tables/columns only; never import RDF tables or keys.

    The small schema TTL is the KG pipeline's documentation source. Its allowed
    values are documented categories, not an exhaustive inventory of SQL rows.
    Missing or invalid documentation fails startup instead of silently running
    a comparison with less context. No instance graph or Fuseki is accessed.
    """
    path = Path(schema_file).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SQL business metadata schema does not exist: {path}")
    graph = rdflib.Graph().parse(str(path), format="turtle")
    metadata = load_sqlite_schema(db_path)
    attach_schema_annotations(graph, metadata)
    documented = sum(bool(details.get("documentation_source")) for details in metadata.values())
    print(f"[SYSTEM] SQL business metadata: {path} ({documented}/{len(metadata)} tables matched)")
    if documented != len(metadata):
        missing = sorted(name for name, details in metadata.items() if not details.get("documentation_source"))
        print(f"[WARN] No matching business documentation for SQL tables: {', '.join(missing)}")
    return metadata
