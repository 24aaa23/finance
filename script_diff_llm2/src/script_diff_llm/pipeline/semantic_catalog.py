"""Load independently authored metric definitions for the current source."""

import json
import re
from pathlib import Path
from typing import Any

from script_diff_llm.pipeline.contracts import column_names


_ENTRY_FIELDS = {
    "id", "backend", "source", "fields", "terms", "definition",
    "formula", "unit", "provenance",
}


def load_semantic_catalog(path: str, sql_schema: dict, kg_schema: dict) -> dict[str, Any]:
    """Validate a source-owned catalog without reading benchmark answers."""
    if not path:
        return {"version": "", "metrics": []}
    with Path(path).open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    if not isinstance(catalog, dict) or not {"version", "metrics"} <= set(catalog) or set(catalog) - {"version", "metrics", "identity_bindings"}:
        raise ValueError("Semantic catalog needs version and metrics, with optional identity_bindings.")
    if not isinstance(catalog["version"], str) or not catalog["version"].strip():
        raise ValueError("Semantic catalog version must be a nonempty string.")
    if not isinstance(catalog["metrics"], list):
        raise ValueError("Semantic catalog metrics must be a list.")
    seen = set()
    for entry in catalog["metrics"]:
        if not isinstance(entry, dict) or set(entry) - _ENTRY_FIELDS:
            raise ValueError("Catalog metric has unsupported fields.")
        for name in ("id", "backend", "source", "definition", "provenance"):
            if not isinstance(entry.get(name), str) or not entry[name].strip():
                raise ValueError(f"Catalog metric needs nonempty {name}.")
        if entry["id"] in seen:
            raise ValueError(f"Duplicate catalog metric id: {entry['id']}")
        seen.add(entry["id"])
        backend = entry["backend"].lower()
        if backend not in {"sql", "kg"}:
            raise ValueError(f"Unsupported catalog backend: {entry['backend']}")
        schema = sql_schema if backend == "sql" else kg_schema
        source = entry["source"]
        if source not in schema:
            raise ValueError(f"Catalog metric {entry['id']} has unknown source {source}")
        fields = entry.get("fields")
        terms = entry.get("terms")
        if not isinstance(fields, list) or not fields or not all(isinstance(x, str) and x for x in fields):
            raise ValueError(f"Catalog metric {entry['id']} needs fields.")
        if not set(fields) <= column_names(schema[source]):
            raise ValueError(f"Catalog metric {entry['id']} references unknown fields.")
        if not isinstance(terms, list) or not terms or not all(isinstance(x, str) and x.strip() for x in terms):
            raise ValueError(f"Catalog metric {entry['id']} needs matching terms.")
        for optional in ("formula", "unit"):
            if optional in entry and not isinstance(entry[optional], str):
                raise ValueError(f"Catalog metric {entry['id']} has invalid {optional}.")
    bindings = catalog.get("identity_bindings", [])
    if not isinstance(bindings, list):
        raise ValueError("identity_bindings must be a list.")
    seen_prefixes = set()
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {"kg_uri_prefix", "sql_source", "sql_field", "provenance"}:
            raise ValueError("Identity binding needs kg_uri_prefix, sql_source, sql_field and provenance.")
        prefix = binding["kg_uri_prefix"]
        if not isinstance(prefix, str) or not prefix.startswith(("http://", "https://")) or not prefix.endswith(("/", "#")) or prefix in seen_prefixes:
            raise ValueError("Identity binding needs a unique HTTP URI namespace prefix.")
        seen_prefixes.add(prefix)
        source = binding["sql_source"]
        field = binding["sql_field"]
        if source not in sql_schema or field not in column_names(sql_schema[source]):
            raise ValueError("Identity binding references an unknown SQL field.")
        if not isinstance(binding["provenance"], str) or not binding["provenance"].strip():
            raise ValueError("Identity binding needs provenance.")
    return catalog


def relevant_catalog_metrics(
    catalog: dict[str, Any], question: str, backend: str, schema_slice: dict,
) -> list[dict[str, Any]]:
    """Expose only entries whose term and source match this subquery."""
    if not isinstance(catalog, dict):
        return []
    matches = []
    for entry in catalog.get("metrics", []):
        if not isinstance(entry, dict) or entry.get("backend", "").lower() != backend.lower():
            continue
        if entry.get("source") not in schema_slice:
            continue
        if any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", question, re.IGNORECASE)
               for term in entry.get("terms", [])):
            matches.append(entry)
    return matches
