"""Select source fragments by ID and derive exact citations and source coverage."""
from collections import defaultdict
from copy import deepcopy
import re


def extraction_units(chunk):
    """Partition source text without rewriting it or removing non-whitespace.

    Sentences, list items and table cells remain in their original chunk, with
    the complete documents available as context. Inline code is not split.
    Benchmark tokens are separate, unselectable units; all other omissions need
    the model's explicit reason. YAML sections stay whole unless mixed.
    """
    from .knowledge import BENCHMARK_ID, PRIVATE_TEXT
    units = []
    for section in chunk["sections"]:
        text = section["text"]
        cuts = {0, len(text)}
        mixed = bool(BENCHMARK_ID.search(text))
        if not section["source"].startswith("yaml/") or mixed:
            code = 0
            depth = 0
            i = 0
            while i < len(text):
                char = text[i]
                if char == "\\":
                    i += 2
                    continue
                if char == "`":
                    end = i + 1
                    while end < len(text) and text[end] == "`":
                        end += 1
                    width = end - i
                    if not code:
                        code = width
                    elif code == width:
                        code = 0
                    i = end
                    continue
                if not code:
                    if char == "|" and text.lstrip().startswith("|"):
                        cuts.update((i, i + 1))
                    if text.startswith("*(", i):
                        cuts.add(i)
                    if text.startswith(")*", i):
                        cuts.add(i + 2)
                    if char in "([":
                        depth += 1
                    elif char in ")]":
                        depth = max(0, depth - 1)
                    if char in ".!?" and not depth and i + 1 < len(text) and text[i + 1].isspace():
                        cuts.add(i + 1)
                    if char == "\n" and re.match(r"[ \t]*[-*+]\s", text[i + 1:]):
                        cuts.add(i + 1)
                i += 1
        # Preserve every other character around benchmark references; do not
        # automatically discard the surrounding sentence's business meaning.
        for match in BENCHMARK_ID.finditer(text):
            cuts.update(match.span())
        spans = [(left, right) for left, right in zip(sorted(cuts), sorted(cuts)[1:])
                 if text[left:right].strip()]
        for index, (left, right) in enumerate(spans, 1):
            quote = text[left:right]
            blocked = ("Benchmark identifier." if BENCHMARK_ID.search(quote) else
                       "Private configuration." if PRIVATE_TEXT.search(quote) else
                       "Markdown table separator." if quote.strip() == "|" else None)
            units.append({"id": section["id"] if len(spans) == 1 else f"{section['id']}/f{index:03d}",
                          "section_id": section["id"], "source": section["source"],
                          "start": section["start"] + left, "end": section["start"] + right,
                          "text": quote, "selectable": blocked is None, "exclusion_reason": blocked})
    return units


def materialize_units(value, chunk):
    """Require a decision for every fragment; compute full/partial coverage."""
    if not isinstance(value, dict) or set(value) != {"rules", "conflicts", "excluded_units"}:
        raise ValueError("Return exactly rules, conflicts and excluded_units for fragment selection.")
    if not isinstance(value["rules"], list) or not isinstance(value["excluded_units"], dict):
        raise ValueError("rules must be a list and excluded_units must map fragment IDs to reasons.")
    units = extraction_units(chunk)
    by_id = {unit["id"]: unit for unit in units}
    excluded = deepcopy(value["excluded_units"])
    for unit_id, reason in excluded.items():
        if unit_id not in by_id:
            raise ValueError(f"Unknown excluded fragment ID: {unit_id}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"Exclusion needs a specific reason: {unit_id}")
    for unit in units:
        if not unit["selectable"]:
            excluded.setdefault(unit["id"], unit["exclusion_reason"])
    selected = defaultdict(list)
    sources = {doc["id"]: doc["content"] for doc in chunk["documents"]}
    result = {"rules": [], "conflicts": deepcopy(value["conflicts"]), "coverage": {},
              "source_review": {source: "reviewed" for source in sources}}
    for rule in value["rules"]:
        if not isinstance(rule, dict) or set(rule) != {"id", "unit_ids", "fields"}:
            raise ValueError("Each rule must have id, unit_ids and fields. Select IDs; do not copy quotes.")
        ids = rule["unit_ids"]
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
            raise ValueError("Each rule needs a nonempty list of fragment IDs.")
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate fragment IDs in rule {rule['id']}")
        for unit_id in ids:
            if unit_id not in by_id:
                raise ValueError(f"Unknown selected fragment ID: {unit_id}")
            if unit_id in excluded:
                raise ValueError(f"Fragment {unit_id} is excluded or unselectable; do not select it in {rule['id']}.")
            selected[unit_id].append(rule["id"])
        # Restore source order and coalesce contiguous spans so line breaks and
        # punctuation are identical to the original document, even across units.
        spans = []
        for unit in units:
            if unit["id"] not in ids:
                continue
            if (spans and spans[-1]["source"] == unit["source"] and
                    spans[-1]["end"] == unit["start"]):
                spans[-1]["end"] = unit["end"]
            else:
                spans.append({k: unit[k] for k in ("source", "start", "end")})
        citations = [{"source": s["source"], "quote": sources[s["source"]][s["start"]:s["end"]]}
                     for s in spans]
        result["rules"].append({"id": rule["id"], "fields": deepcopy(rule["fields"]),
                                "citations": citations, "text": "\n".join(c["quote"] for c in citations)})
    missing = [u["id"] for u in units if u["id"] not in selected and u["id"] not in excluded]
    if missing:
        raise ValueError("Every fragment needs selection or an exclusion reason. Missing: " + ", ".join(missing))
    grouped = defaultdict(list)
    for unit in units:
        grouped[unit["section_id"]].append(unit)
    for section in chunk["sections"]:
        parts = grouped[section["id"]]
        omitted = [u for u in parts if u["id"] in excluded]
        rule_ids = list(dict.fromkeys(i for u in parts for i in selected[u["id"]]))
        if omitted:
            retained = f" Retained source fragments in {', '.join(rule_ids)}." if rule_ids else ""
            result["coverage"][section["id"]] = {"exclude": "Omitted fragments: " + "; ".join(
                f"{u['id']}: {excluded[u['id']]}" for u in omitted) + retained}
        else:
            result["coverage"][section["id"]] = {"rule_ids": rule_ids}
    return result
