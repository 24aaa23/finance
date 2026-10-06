"""Source-section evidence and auditable reasons for knowledge omissions."""
import re


def source_sections(documents):
    sections = []
    for document in documents:
        content = document["content"]
        start, end, offset, number = None, 0, 0, 0

        def emit():
            nonlocal start, number
            if start is not None:
                number += 1
                sections.append({"id": f"{document['id']}:{number:04d}", "source": document["id"],
                                 "start": start, "end": end, "text": content[start:end]})
                start = None

        for line in content.splitlines(keepends=True):
            stripped = line.strip()
            structural = not stripped or re.fullmatch(r"[|:\s-]+", stripped)
            if structural:
                emit()
            elif stripped.startswith(("|", "#")):
                emit()
                start, end = offset, offset + len(line.rstrip("\r\n"))
                emit()
            else:
                if start is None:
                    start = offset
                end = offset + len(line.rstrip("\r\n"))
            offset += len(line)
        emit()
    return sections


def validate_coverage(pack, documents, sections=None):
    sections = source_sections(documents) if sections is None else sections
    expected = {section["id"] for section in sections}
    coverage = pack.get("coverage")
    if not isinstance(coverage, dict) or set(coverage) != expected:
        missing = sorted(expected - set(coverage or {})) if isinstance(coverage, dict) else sorted(expected)
        raise ValueError("Coverage must account for every source section; missing/unknown sections. Missing: "
                         + ", ".join(missing[:20]))
    rules = {rule["id"]: rule for rule in pack["rules"]}
    sources = {document["id"]: document["content"] for document in documents}
    for section in sections:
        entry = coverage[section["id"]]
        if isinstance(entry, dict) and set(entry) == {"exclude"}:
            if not isinstance(entry["exclude"], str) or not entry["exclude"].strip():
                raise ValueError("Every excluded section requires an explicit reason.")
            continue
        if not isinstance(entry, dict) or set(entry) != {"rule_ids"}:
            raise ValueError("Coverage entry must contain rule_ids or exclude, not both.")
        ids = entry["rule_ids"]
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in rules for i in ids):
            raise ValueError("Coverage must reference existing rule IDs.")
        covered = bytearray(section["end"] - section["start"])
        content = sources[section["source"]]
        for rule_id in ids:
            for citation in rules[rule_id]["citations"]:
                if citation["source"] != section["source"]:
                    continue
                quote = citation["quote"]
                position = content.find(quote)
                while position != -1:
                    left = max(position, section["start"]) - section["start"]
                    right = min(position + len(quote), section["end"]) - section["start"]
                    if right > left:
                        covered[left:right] = b"\x01" * (right - left)
                    position = content.find(quote, position + 1)
        if any(not char.isspace() and not covered[index] for index, char in enumerate(section["text"])):
            raise ValueError(f"Coverage for {section['id']} is incomplete; cite its full content or explicitly exclude it with a reason.")


def coverage_report(pack, documents, identity, pack_hash):
    sections = source_sections(documents)
    if "validation_notes" in pack:
        return {"identity": identity, "pack_hash": pack_hash, "section_count": len(sections),
                "coverage_checked": False, "excluded_sections": [], "validation_notes": pack["validation_notes"],
                "review_status": pack.get("review_status", "not_run"),
                "finalization_status": pack.get("finalization_status", "not_run")}
    return {"identity": identity, "pack_hash": pack_hash,
            "section_count": len(sections),
            "excluded_sections": [{**section, "reason": pack["coverage"][section["id"]]["exclude"]}
                                  for section in sections if "exclude" in pack["coverage"][section["id"]]]}


