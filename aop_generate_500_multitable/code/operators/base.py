import re
import json
import unicodedata
import rdflib
from typing import Any, Dict, List

def sanitize_user_query(raw_query: str) -> str:
    """
    Strips corrupted Unicode, unprintable characters, and normalizes the text
    to prevent downstream JSON hallucination and pipeline crashes.
    """
    # Normalize unicode characters to their closest ASCII representation if possible
    normalized = unicodedata.normalize('NFKD', raw_query).encode('ascii', 'ignore').decode('utf-8')
    # Remove any lingering unprintable/control characters
    cleaned = re.sub(r'[^\x20-\x7E]', '', normalized)
    # Remove awkward multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned if cleaned else "Invalid Query"

def parse_llm_json(raw_text: str, default: Any, context: str) -> Any:
    text = (raw_text or "").strip()
    if not text:
        print(f"[WARN] Empty JSON response from {context}; using default.")
        return default

    text = text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    candidates = [text]

    array_start = text.find("[")
    array_end = text.rfind("]")
    if array_start != -1 and array_end > array_start:
        candidates.append(text[array_start:array_end + 1])

    object_start = text.find("{")
    object_end = text.rfind("}")
    if object_start != -1 and object_end > object_start:
        candidates.append(text[object_start:object_end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[start:])
            return parsed
        except json.JSONDecodeError:
            continue

    preview = text[:300].replace("\n", " ")
    print(f"[WARN] Invalid JSON response from {context}; using default. Response preview: {preview}")
    return default

def normalize_classification(raw_classification: Any, query: str = "") -> Dict[str, Any]:
    if isinstance(raw_classification, dict) and isinstance(raw_classification.get("intent"), str):
        intent = raw_classification.get("intent", "")
        reason = str(raw_classification.get("reason", "")).lower()
        bad_reason_markers = ["invalid json", "invalid format", "did not return", "malformed", "parse"]
        if intent == "out_of_domain_unanswerable" and any(marker in reason for marker in bad_reason_markers):
            print("[WARN] Classify returned unanswerable due to malformed output; using point_lookup fallback.")
            return {
                "intent": "point_lookup",
                "confidence": 0.0,
                "reason": "Classifier output was malformed; do not short-circuit.",
            }
        if intent == "out_of_domain_unanswerable":
            schema_datatype = str(raw_classification.get("schema_datatype", "")).strip().lower()
            target_field = normalize_for_compare(raw_classification.get("target_field", ""))
            query_text = normalize_for_compare(query)
            target_tokens = {token for token in target_field.split() if len(token) > 2 and token not in {"field", "value", "values"}}
            query_tokens = set(query_text.split())
            if schema_datatype != "categorical_string" or not (target_tokens and target_tokens <= query_tokens):
                fallback_intent = "aggregation_numeric" if re.search(r"\b(average|avg|sum|minimum|min|maximum|max|highest|lowest|total|count)\b", query_text) else "point_lookup"
                print("[WARN] Rejected ungrounded unanswerable classification; continuing the pipeline.")
                return {"intent": fallback_intent, "confidence": 0.0, "target_field": target_field, "schema_datatype": schema_datatype or "unknown", "reason": "Unanswerable classification was not grounded in the requested field and schema datatype."}
        return raw_classification

    print(f"[WARN] Invalid Classify payload shape: {type(raw_classification).__name__}; using point_lookup fallback.")
    return {
        "intent": "point_lookup",
        "confidence": 0.0,
        "reason": "Classifier did not return a JSON object.",
    }

def strip_llm_reasoning_blocks(text: str) -> str:
    """Remove reasoning wrappers that some models emit before the requested payload."""
    cleaned = re.sub(r"(?is)<reasoning>.*?</reasoning>", "", text or "")
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
    cleaned = re.sub(r"(?ims)^\s*<reasoning>.*?(?=^\s*(?:PREFIX|SELECT|ASK|CONSTRUCT|DESCRIBE)\b)", "", cleaned)
    cleaned = re.sub(r"(?ims)^\s*<think>.*?(?=^\s*(?:PREFIX|SELECT|ASK|CONSTRUCT|DESCRIBE)\b)", "", cleaned)

    sparql_start = re.search(r"(?im)^\s*(PREFIX|SELECT|ASK|CONSTRUCT|DESCRIBE)\b", cleaned)
    if sparql_start:
        cleaned = cleaned[sparql_start.start():]
    return cleaned.strip()

def preprocess_user_query(query: str) -> str:
    """Normalize entity aliases before retrieval, planning, and SPARQL generation."""
    cleaned = sanitize_user_query(query)
    return re.sub(
        r"\b([A-Za-z]+-?\d{1,4})\b",
        lambda match: resolve_graph_id_alias(match.group(1)),
        cleaned,
    )

def repair_sparql_query(sparql: str) -> str:
    normalized = (sparql or "").strip()
    if not normalized:
        return ""

    normalized = strip_llm_reasoning_blocks(normalized)
    normalized = re.sub(
        r"^\s*```(?:sparql)?\s*|\s*```\s*$",
        "",
        normalized,
        flags=re.I,
    ).strip()
    normalized = strip_llm_reasoning_blocks(normalized)
    normalized = normalize_compact_kg_ids(normalized)

    required_prefixes = {
        "wm": "https://wealth.example.org/ontology/",
        "kg": "https://wealth.example.org/kg/",
        "wmmeta": "https://wealth.example.org/metadata/",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "schema1": "http://schema.org/",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }
    missing_prefixes = [
        f"PREFIX {prefix}: <{uri}>"
        for prefix, uri in required_prefixes.items()
        if not re.search(rf"(?im)^\s*PREFIX\s+{re.escape(prefix)}\s*:", normalized)
    ]
    if missing_prefixes:
        normalized = "\n".join(missing_prefixes) + "\n\n" + normalized

    return normalized.strip()

def repair_sparql_for_query(sparql: str, query: str) -> str:
    return repair_sparql_query(sparql)

def normalize_sparql_for_compare(sparql: str) -> str:
    sparql = re.sub(r"#.*", "", sparql or "")
    sparql = re.sub(r"\s+", " ", sparql).strip().lower()
    return sparql

def sparql_too_similar(a: str, b: str, threshold: float = 0.92) -> bool:
    normalized_a = normalize_sparql_for_compare(a)
    normalized_b = normalize_sparql_for_compare(b)
    if not normalized_a or not normalized_b:
        return False
    return difflib.SequenceMatcher(None, normalized_a, normalized_b).ratio() >= threshold

def local_name(uri: Any) -> str:
    text = str(uri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rstrip("/").rsplit("/", 1)[-1]

def collect_graph_terms(rdf_graph: rdflib.Graph) -> set:
    terms = set()
    for subject, predicate, obj in rdf_graph:
        for node in (subject, predicate, obj):
            if isinstance(node, rdflib.term.URIRef) and str(node).startswith("https://wealth.example.org/ontology/"):
                terms.add(local_name(node))
    return terms

def extract_ex_terms_from_sparql(sparql: str) -> list:
    body = re.sub(r"PREFIX\s+\w+:\s*<[^>]+>", "", sparql or "", flags=re.I)
    return sorted(set(re.findall(r"\bwm:([A-Za-z_][A-Za-z0-9_-]*)\b", body)))

def validate_sparql_terms(sparql: str, rdf_graph: rdflib.Graph) -> Dict[str, Any]:
    used_terms = extract_ex_terms_from_sparql(sparql)
    known_terms = collect_graph_terms(rdf_graph)
    unknown_terms = [term for term in used_terms if term not in known_terms]
    suggestions = {
        term: difflib.get_close_matches(term, sorted(known_terms), n=5, cutoff=0.55)
        for term in unknown_terms
    }
    return {
        "is_valid": not unknown_terms,
        "used_terms": used_terms,
        "unknown_terms": unknown_terms,
        "suggestions": suggestions,
    }

def build_schema_generation_rules(schema_details: Dict[str, Any]) -> str:
    if not schema_details:
        return "No schema slice was available. Use only classes and predicates visible in the RDF graph."

    lines = [
        "Use the schema slice below as the source of truth. Do not invent classes or predicates.",
        "For each selected class, prefer its listed properties and relationship fields.",
    ]
    for class_name, details in schema_details.items():
        lines.append(f"- Class: {class_name}")
        if isinstance(details, dict):
            for key in ("properties", "dynamic_properties", "columns", "attributes", "relationships"):
                values = details.get(key)
                if isinstance(values, dict):
                    values = list(values.keys())
                if isinstance(values, list) and values:
                    preview = ", ".join(str(value) for value in values[:30])
                    lines.append(f"  {key}: {preview}")
    return "\n".join(lines)

