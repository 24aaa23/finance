import os
import re
import json
import rdflib
from typing import Dict, Any
from code.config import INSTANCE_FILE, ALIAS_MAP_FILE

# Global cache
RDF_ID_ALIAS_MAP = {}

def load_rdf_id_alias_map(alias_file: str) -> Dict[str, Any]:
    if not alias_file or not os.path.exists(alias_file):
        return {}
    with open(alias_file) as f:
        alias_data = json.load(f)
    if not isinstance(alias_data, dict):
        return {}
    return alias_data

def resolve_graph_id_alias(value: str) -> str:
    entry = RDF_ID_ALIAS_MAP.get(canonical_id_key(value), {})
    if not isinstance(entry, dict) or entry.get("ambiguous"):
        return value
    resolved_id = entry.get("resolved_id")
    if resolved_id:
        return str(resolved_id)
    candidates = entry.get("candidates", [])
    if len(candidates) == 1:
        return str(candidates[0])
    if value in candidates:
        return value
    return value

def normalize_compact_kg_ids(text: str) -> str:
    text = re.sub(
        r"\bex:([A-Za-z]+-?\d{1,4})\b",
        lambda m: f"wm:{resolve_graph_id_alias(m.group(1))}",
        text,
        flags=re.I,
    )
    text = re.sub(
        r'(["\'])([A-Za-z]+-?\d{1,4})\1',
        lambda m: f"{m.group(1)}{resolve_graph_id_alias(m.group(2))}{m.group(1)}",
        text,
        flags=re.I,
    )
    return text


# --- INTEGRATED ALIAS BUILDER LOGIC ---
def canonical_id_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

def is_compact_graph_id(value: Any) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]+-?\d{1,4}", str(value or "")))

def generated_aliases(real_id: str) -> set[str]:
    aliases = {real_id, real_id.lower(), real_id.upper()}
    match = re.fullmatch(r"([A-Za-z]+)-?(\d{1,4})", real_id)
    if not match:
        return aliases
    prefix = match.group(1)
    digits = match.group(2)
    number = int(digits)
    widths = range(1, max(3, len(digits)) + 1)
    for prefix_variant in {prefix, prefix.lower(), prefix.upper()}:
        for width in widths:
            numeric_variant = str(number).zfill(width)
            aliases.add(f"{prefix_variant}{numeric_variant}")
            aliases.add(f"{prefix_variant}-{numeric_variant}")
    return aliases

def build_alias_map(instance_file: str) -> dict[str, dict[str, Any]]:
    graph = rdflib.Graph()
    graph.parse(instance_file, format="turtle")
    real_ids = set()
    def add_real_id(value: Any) -> None:
        text = str(value or "")
        if is_compact_graph_id(text):
            real_ids.add(text)
    for subject, predicate, obj in graph:
        if isinstance(subject, rdflib.term.URIRef) and str(subject).startswith("http://example.org/kg#"):
            add_real_id(str(subject).split("#")[-1])
        if isinstance(obj, rdflib.term.URIRef) and str(obj).startswith("http://example.org/kg#"):
            add_real_id(str(obj).split("#")[-1])
        if isinstance(obj, rdflib.Literal) and str(predicate).lower().endswith("id"):
            add_real_id(str(obj))
    grouped = {}
    for real_id in sorted(real_ids):
        for alias in generated_aliases(real_id):
            alias_key = canonical_id_key(alias)
            grouped.setdefault(alias_key, {"candidates": set(), "aliases": set()})
            grouped[alias_key]["candidates"].add(real_id)
            grouped[alias_key]["aliases"].add(alias)
    alias_map = {}
    for alias_key, grouped_data in sorted(grouped.items()):
        sorted_candidates = sorted(grouped_data["candidates"])
        alias_map[alias_key] = {
            "resolved_id": sorted_candidates[0] if len(sorted_candidates) == 1 else None,
            "candidates": sorted_candidates,
            "aliases": sorted(grouped_data["aliases"]),
            "ambiguous": len(sorted_candidates) > 1,
        }
    return alias_map

def check_and_rebuild_alias_map():
    """Automatically checks if the alias map needs rebuilding, runs it, and loads it."""
    global RDF_ID_ALIAS_MAP
    rebuild = False
    if not os.path.exists(ALIAS_MAP_FILE):
        print(f"[ALIAS] {ALIAS_MAP_FILE} not found. Rebuilding...")
        rebuild = True
    elif os.path.exists(INSTANCE_FILE):
        # Compare modified timestamps
        ttl_time = os.path.getmtime(INSTANCE_FILE)
        json_time = os.path.getmtime(ALIAS_MAP_FILE)
        if ttl_time > json_time:
            print("[ALIAS] Knowledge Graph is newer than alias map. Rebuilding...")
            rebuild = True
            
    if rebuild and os.path.exists(INSTANCE_FILE):
        try:
            alias_map = build_alias_map(INSTANCE_FILE)
            os.makedirs(os.path.dirname(ALIAS_MAP_FILE), exist_ok=True)
            with open(ALIAS_MAP_FILE, "w") as f:
                json.dump(alias_map, f, indent=2)
            print(f"[ALIAS] Saved rebuilt alias map to {ALIAS_MAP_FILE}")
        except Exception as e:
            print(f"[ALIAS] Error rebuilding alias map: {e}")
            
    # Load into memory
    loaded = load_rdf_id_alias_map(ALIAS_MAP_FILE)
    RDF_ID_ALIAS_MAP.clear()
    RDF_ID_ALIAS_MAP.update(loaded)

# Auto-run checks on import
check_and_rebuild_alias_map()
