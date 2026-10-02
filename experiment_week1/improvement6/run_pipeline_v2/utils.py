"""Shared utility helpers used by the pipeline."""

from . import common
from .common import (
    Any,
    Dict,
    FUSEKI_ENDPOINT,
    FUSEKI_METADATA_TIMEOUT_SECONDS,
    difflib,
    json,
    os,
    rdflib,
    re,
    unicodedata,
)


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

    # Strip thinking/reasoning tags from reasoning models (e.g. GPT-OSS 120B)
    text = re.sub(r"<(?:thought|reasoning)>.*?</(?:thought|reasoning)>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    if not text:
        print(f"[WARN] Response from {context} contained only reasoning tags; using default.")
        return default

    # Strip markdown code fences
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    candidates = [text]

    object_start = text.find("{")
    object_end = text.rfind("}")
    if object_start != -1 and object_end > object_start:
        candidates.append(text[object_start:object_end + 1])

    array_start = text.find("[")
    array_end = text.rfind("]")
    if array_start != -1 and array_end > array_start:
        candidates.append(text[array_start:array_end + 1])

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




def normalize_for_compare(value: Any) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", str(value).lower()).strip()


def canonical_id_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def load_rdf_id_alias_map(alias_file: str) -> Dict[str, Any]:
    if not alias_file or not os.path.exists(alias_file):
        return {}
    with open(alias_file) as f:
        alias_data = json.load(f)
    if not isinstance(alias_data, dict):
        return {}
    return alias_data


def resolve_graph_id_alias(value: str) -> str:
    entry = common.RDF_ID_ALIAS_MAP.get(canonical_id_key(value), {})
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
        lambda m: f"kg:{resolve_graph_id_alias(m.group(1))}",
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
    if sparql is None:
        return ""
    normalized = str(sparql).strip()
    if not normalized or normalized.lower() == "nan":
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

    # Auto-repair casing bug: LCASE(...) = "UPPER" -> LCASE(...) = "lower"
    normalized = re.sub(
        r'(LCASE\s*\(.+?\)\s*=\s*)"([^"]+)"',
        lambda m: f'{m.group(1)}"{m.group(2).lower()}"',
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r'"([^"]+)"(\s*=\s*LCASE\s*\(.+?\))',
        lambda m: f'"{m.group(1).lower()}"{m.group(2)}',
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r'(CONTAINS\s*\(\s*LCASE\s*\(.+?\)\s*,\s*)"([^"]+)"',
        lambda m: f'{m.group(1)}"{m.group(2).lower()}"',
        normalized,
        flags=re.I,
    )

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
    # this function takes a URI (Uniform Resource Identifier) as input and returns the local name of the URI. The local name is the part of the URI that comes after the last '#' or '/' character. If the URI contains a '#' character, the function splits the URI at the last '#' and returns the part after it. If there is no '#' character, it removes any trailing '/' characters and splits the URI at the last '/' to return the part after it. This is useful for extracting meaningful names from URIs in RDF graphs or ontologies.
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


def collect_fuseki_graph_terms() -> set:
    if common.FUSEKI_GRAPH_TERMS_CACHE is not None:
        return common.FUSEKI_GRAPH_TERMS_CACHE

    query = """
SELECT DISTINCT ?term
WHERE {
  {
    ?s ?term ?o .
  }
  UNION
  {
    ?s ?p ?term .
  }
  FILTER(isIRI(?term))
  FILTER(STRSTARTS(STR(?term), "https://wealth.example.org/ontology/"))
}
"""
    from .non_llm_operators.fuseki import execute_sparql_on_fuseki

    result = execute_sparql_on_fuseki(
        query,
        FUSEKI_ENDPOINT,
        FUSEKI_METADATA_TIMEOUT_SECONDS,
    )
    if result.get("status") != "success":
        print(f"[WARN] Fuseki term collection failed: {result.get('error_message')}")
        return set()
    common.FUSEKI_GRAPH_TERMS_CACHE = {local_name(row.get("term", "")) for row in result.get("data", []) if row.get("term")}
    return common.FUSEKI_GRAPH_TERMS_CACHE


def extract_ex_terms_from_sparql(sparql: str) -> list:
    body = re.sub(r"PREFIX\s+\w+:\s*<[^>]+>", "", sparql or "", flags=re.I)
    return sorted(set(re.findall(r"\bwm:([A-Za-z_][A-Za-z0-9_-]*)\b", body)))


def validate_sparql_terms(sparql: str, rdf_graph: rdflib.Graph) -> Dict[str, Any]:
    used_terms = extract_ex_terms_from_sparql(sparql)
    known_terms = collect_fuseki_graph_terms() if rdf_graph is None else collect_graph_terms(rdf_graph)
    if not known_terms:
        return {
            "is_valid": True,
            "used_terms": used_terms,
            "unknown_terms": [],
            "suggestions": {},
            "warning": "Known graph terms could not be collected; skipped strict term validation.",
        }
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


def is_quota_exhaustion_error(error: Any) -> bool:
    text = str(error or "").lower()
    return (
        "insufficient_quota" in text
        or "exceeded your current quota" in text
        or ("error code: 429" in text and "quota" in text)
    )


def is_transient_connection_error(error: Any) -> bool:
    """Classify transport/service interruptions without inspecting question content."""
    text = str(error or "").lower()
    markers = (
        "connection error", "connection refused", "connection reset",
        "read timed out", "connect timeout", "service unavailable",
        "temporarily unavailable", "gateway timeout",
    )
    return any(marker in text for marker in markers)


def tokenize_column_name(col_name: Any) -> set:
    """Splits camelCase, PascalCase, snake_case, or kebab-case into normalized word tokens.
    Universal and domain-agnostic for any schema or dataset.
    """
    clean = re.sub(r"^(?:has|is|wm|kg)_?", "", str(col_name or ""), flags=re.I)
    words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z]|\b)", clean)
    stop = {"has", "is", "the", "a", "an", "id", "pk", "fk"}
    tokens = set()
    for w in words:
        wl = w.lower()
        if len(wl) > 1 and wl not in stop:
            tokens.add(wl)
            if wl.endswith("s") and len(wl) > 3:
                tokens.add(wl[:-1])
            if wl in {"pct", "pctg"}:
                tokens.update({"percentage", "percent", "rate", "ratio"})
            elif wl in {"amt", "amount"}:
                tokens.update({"amt", "amount"})
            elif wl in {"cnt", "count", "num"}:
                tokens.update({"cnt", "count", "number"})
            elif wl in {"val", "value"}:
                tokens.update({"val", "value"})
            elif wl in {"tot", "total"}:
                tokens.update({"tot", "total", "sum"})
            elif wl in {"avg", "average"}:
                tokens.update({"avg", "average", "mean"})
    return tokens


def find_column_by_semantic_match(columns: Any, target_text: str, candidates: list = None) -> Any:
    """Finds the column whose tokenized words best match target_text.
    100% domain-agnostic: relies purely on NLP token overlap and substring containment.
    """
    if not target_text or columns is None or len(columns) == 0:
        return None
    raw_tokens = re.findall(r"[a-z0-9]+", str(target_text).lower())
    target_words = set(raw_tokens)
    for w in raw_tokens:
        if w.endswith("s") and len(w) > 3:
            target_words.add(w[:-1])
        if w in {"percentage", "percent"}:
            target_words.add("pct")

    cols = candidates if candidates is not None else list(columns)
    best_col = None
    best_score = 0
    for col in cols:
        col_words = tokenize_column_name(col)
        if not col_words:
            continue
        overlap = len(col_words & target_words)
        if overlap > best_score:
            best_score = overlap
            best_col = col

        clean_col = re.sub(r"[^a-z0-9]+", "", str(col).lower())
        clean_target = re.sub(r"[^a-z0-9]+", "", str(target_text).lower())
        if clean_col in clean_target or clean_target in clean_col:
            score = 1.5 if len(clean_col) > 3 else 1.0
            if score > best_score:
                best_col = col
                best_score = score

    return best_col if best_score > 0 else None
