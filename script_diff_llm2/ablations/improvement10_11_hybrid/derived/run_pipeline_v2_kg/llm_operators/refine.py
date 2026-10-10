"""Regenerate a failed query without weakening the active retrieval contract."""
from .generate import semantic_generate_sparql


def semantic_refine(inputs, client=None, model=None):
    schema = inputs.get("schema_details") or inputs.get("global_schema", {})
    return semantic_generate_sparql({**inputs, "global_schema": schema}, client, model)
