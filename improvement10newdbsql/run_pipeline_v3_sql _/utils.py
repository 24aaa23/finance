"""Shared SQL pipeline utilities."""
from .common import Any, difflib, json, re, unicodedata


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
    """Keep existing text sanitation without consulting external alias maps."""
    return sanitize_user_query(query)


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
    if is_quota_exhaustion_error(error):
        return False
    if getattr(error, 'status_code', None) in {408, 429, 500, 502, 503, 504} or 'rate_limit_exceeded' in text or 'too many requests' in text:
        return True
    markers = (
        "connection error", "connection refused", "connection reset",
        "read timed out", "request timed out", "connect timeout", "service unavailable",
        "temporarily unavailable", "gateway timeout",
    )
    return any(marker in text for marker in markers)
