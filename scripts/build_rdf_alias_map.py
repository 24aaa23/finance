import argparse
import csv
import json
import os
import re
from typing import Any

import rdflib


BASE_DIR = "/DATAAMAN/financial"
DEFAULT_INSTANCE_FILE = os.path.join(BASE_DIR, "business_data_kg_schema_aligned.ttl")
OUTPUT_DIR = os.path.join(BASE_DIR, "Pipeline_Outputs")
DEFAULT_JSON_OUTPUT = os.path.join(OUTPUT_DIR, "rdf_id_alias_map.json")
DEFAULT_CSV_OUTPUT = os.path.join(OUTPUT_DIR, "rdf_id_alias_map.csv")
EX_PREFIX = "http://example.org/kg#"


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
    # Include every common zero-padding width, not only the unpadded and
    # three-digit forms. For INV001 this safely produces INV1, INV01, and
    # INV001. Ambiguous variants are detected later and are never resolved.
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
        if isinstance(subject, rdflib.term.URIRef) and str(subject).startswith(EX_PREFIX):
            add_real_id(str(subject).split("#")[-1])
        if isinstance(obj, rdflib.term.URIRef) and str(obj).startswith(EX_PREFIX):
            add_real_id(str(obj).split("#")[-1])
        if isinstance(obj, rdflib.Literal) and str(predicate).lower().endswith("id"):
            add_real_id(str(obj))

    grouped: dict[str, dict[str, set[str]]] = {}
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


def write_csv(alias_map: dict[str, dict[str, Any]], csv_path: str) -> None:
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["alias_key", "aliases", "resolved_id", "ambiguous", "candidates"])
        writer.writeheader()
        for alias_key, data in alias_map.items():
            writer.writerow({
                "alias_key": alias_key,
                "aliases": ", ".join(data["aliases"]),
                "resolved_id": data["resolved_id"] or "",
                "ambiguous": data["ambiguous"],
                "candidates": ", ".join(data["candidates"]),
            })


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an alias map from compact RDF IDs.")
    parser.add_argument("--instance-file", default=DEFAULT_INSTANCE_FILE)
    parser.add_argument("--json-output", default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--csv-output", default=DEFAULT_CSV_OUTPUT)
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.json_output), exist_ok=True)
    os.makedirs(os.path.dirname(args.csv_output), exist_ok=True)

    alias_map = build_alias_map(args.instance_file)
    with open(args.json_output, "w") as f:
        json.dump(alias_map, f, indent=2)
    write_csv(alias_map, args.csv_output)

    print(f"Alias keys: {len(alias_map)}")
    print(f"Saved JSON: {args.json_output}")
    print(f"Saved CSV:  {args.csv_output}")


if __name__ == "__main__":
    main()
