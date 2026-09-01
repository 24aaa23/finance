"""
Base Text-to-SPARQL Pipeline — Qwen 3 235B
===========================================

Simplified 6-step pipeline:
  1. INPUT      — Query + Schema
  2. GENERATE   — LLM produces SPARQL from query + schema
  3. EXECUTE    — Run SPARQL against Fuseki triplestore
  4. GRADE      — LLM compares output vs ground truth
  5. DECISION   — MATCH → SUCCESS, else RETRY
  6. RETRY      — Up to 3 attempts, then FAILURE

Model:  qwen.qwen3-235b-a22b-2507  (via Bedrock Mantle)
Grader: openai.gpt-oss-120b-1:0    (via Bedrock)
"""

import datetime
import json
import os
import re
import socket
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import pandas as pd
import rdflib
from openai import OpenAI as LLMClient


# ---------------------------------------------------------------------------
# 0. ENVIRONMENT
# ---------------------------------------------------------------------------

def load_local_env_file() -> None:
    """Read .env from standard candidate paths."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_candidates = [
        os.path.join(script_dir, ".env"),
        os.path.join(os.path.dirname(script_dir), ".env"),
    ]
    env_file = next((p for p in env_candidates if os.path.exists(p)), None)
    if not env_file:
        return
    with open(env_file, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            os.environ[key.strip()] = value


load_local_env_file()

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Models
GPT_OSS_MODEL = os.getenv("BEDROCK_GPT_OSS_MODEL", "openai.gpt-oss-120b-1:0")
TARGET_MODEL = os.getenv("TARGET_MODEL", GPT_OSS_MODEL)
GRADER_MODEL = os.getenv("GRADER_MODEL", "gpt-5.6-terra")

# Pipeline behaviour
MAX_RETRIES = 3
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION", "base-pipeline-qwen3-235b-v1")
TEST_QUERY_LIMIT = int(os.getenv("TEST_QUERY_LIMIT", "442"))
TEST_QUERY_OFFSET = int(os.getenv("TEST_QUERY_OFFSET", "0"))

# Fuseki
FUSEKI_ENDPOINT = os.getenv("FUSEKI_ENDPOINT", "http://127.0.0.1:3030/wealth/query")
FUSEKI_SCAN_TIMEOUT_SECONDS = max(0.0, float(os.getenv("FUSEKI_SCAN_TIMEOUT_SECONDS", "60")))
FUSEKI_METADATA_TIMEOUT_SECONDS = max(0.0, float(os.getenv("FUSEKI_METADATA_TIMEOUT_SECONDS", "60")))

# File paths
SCHEMA_FILE = os.getenv(
    "SCHEMA_FILE",
    os.path.join(SCRIPT_DIR, "kg_output_fixed", "wealth_management_diverse_schema.ttl"),
)
INSTANCE_FILE = os.getenv(
    "INSTANCE_FILE",
    os.path.join(SCRIPT_DIR, "kg_output_fixed", "wealth_management_diverse_kg.ttl"),
)
INPUT_SAMPLE_FILE = os.getenv(
    "INPUT_SAMPLE_FILE",
    os.path.join(SCRIPT_DIR, "dataset", "verification_results_v2_sql_correct_442.xlsx"),
)
OUTPUT_DIR = os.getenv("PIPELINE_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "pipeline_output"))
REPORT_FILE = os.getenv(
    "REPORT_FILE",
    os.path.join(OUTPUT_DIR, f"base_pipeline_{TARGET_MODEL.replace('.', '_').replace('-', '_')}.csv"),
)

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)


# ---------------------------------------------------------------------------
# 2. API CLIENTS
# ---------------------------------------------------------------------------

def build_gpt_oss_client() -> LLMClient:
    """Bedrock OpenAI-compatible client for GPT-OSS 120B (grading)."""
    api_key = (
        os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not api_key:
        raise RuntimeError("AWS_BEDROCK_API_KEY is required for GPT-OSS 120B Bedrock endpoint.")
    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError("BEDROCK_REGION is required (e.g. us-east-1).")
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"
    return LLMClient(api_key=api_key, base_url=base_url)


def build_target_client() -> LLMClient:
    """Build the client for SPARQL generation."""
    if TARGET_MODEL == GPT_OSS_MODEL or TARGET_MODEL.lower().startswith("openai.gpt-oss"):
        print(f"[SYSTEM] SPARQL generation uses Bedrock GPT-OSS API (model: {TARGET_MODEL})")
        return build_gpt_oss_client()

    api_key = (
        os.getenv("BEDROCK_MANTLE_API_KEY")
        or os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not api_key:
        raise RuntimeError("BEDROCK_MANTLE_API_KEY or AWS_BEDROCK_API_KEY is required.")
    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_MANTLE_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError("BEDROCK_REGION is required for Bedrock Mantle.")
        base_url = f"https://bedrock-mantle.{region}.api.aws/v1"
    print(f"[SYSTEM] SPARQL generation uses Bedrock Mantle API (model: {TARGET_MODEL})")
    return LLMClient(api_key=api_key, base_url=base_url)


def build_openai_client() -> LLMClient:
    """Native OpenAI client for GPT-5.x models (e.g. gpt-5.6-terra, gpt-5.6-sol)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for OpenAI grader models "
            "(gpt-5.6-terra, gpt-5.6-sol, etc.)."
        )
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        return LLMClient(api_key=api_key, base_url=base_url)
    return LLMClient(api_key=api_key)


def build_grader_client() -> LLMClient:
    """
    Auto-detect which client to build based on GRADER_MODEL:
      - gpt-5.x models → OpenAI native API
      - everything else → Bedrock (GPT-OSS 120B)
    """
    model_lower = GRADER_MODEL.lower()
    if model_lower.startswith("gpt-5") or model_lower.startswith("gpt-4"):
        print(f"[SYSTEM] Grader uses OpenAI API (model: {GRADER_MODEL})")
        return build_openai_client()
    else:
        print(f"[SYSTEM] Grader uses Bedrock API (model: {GRADER_MODEL})")
        return build_gpt_oss_client()


# ---------------------------------------------------------------------------
# 3. API LOGGER
# ---------------------------------------------------------------------------

class APILogger:
    def __init__(self):
        self.lock = threading.Lock()
        self.query_logs: Dict[str, Any] = {}
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(OUTPUT_DIR, f"api_usage_log_{timestamp}.json")

    def log_call(self, query: str, function_name: str):
        with self.lock:
            q_key = query or "Unknown_Query"
            if q_key not in self.query_logs:
                self.query_logs[q_key] = {"total_calls": 0, "functions": {}}
            self.query_logs[q_key]["total_calls"] += 1
            self.query_logs[q_key]["functions"][function_name] = (
                self.query_logs[q_key]["functions"].get(function_name, 0) + 1
            )

    def save(self):
        with self.lock:
            with open(self.log_file, "w") as f:
                json.dump(self.query_logs, f, indent=4)


api_logger = APILogger()


# ---------------------------------------------------------------------------
# 4. UTILITY FUNCTIONS
# ---------------------------------------------------------------------------

def sanitize_user_query(raw_query: str) -> str:
    """Strip corrupted Unicode and unprintable characters."""
    normalized = unicodedata.normalize("NFKD", raw_query).encode("ascii", "ignore").decode("utf-8")
    cleaned = re.sub(r"[^\x20-\x7E]", "", normalized)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else "Invalid Query"


def local_name(uri: Any) -> str:
    text = str(uri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rstrip("/").rsplit("/", 1)[-1]


def normalize_for_compare(value: Any) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", str(value).lower()).strip()


def strip_llm_reasoning_blocks(text: str) -> str:
    """Remove <reasoning>/<think> wrappers that some models emit."""
    cleaned = re.sub(r"(?is)<reasoning>.*?</reasoning>", "", text or "")
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
    sparql_start = re.search(r"(?im)^\s*(PREFIX|SELECT|ASK|CONSTRUCT|DESCRIBE)\b", cleaned)
    if sparql_start:
        cleaned = cleaned[sparql_start.start():]
    return cleaned.strip()


def repair_sparql_query(sparql: str) -> str:
    """Clean up LLM SPARQL output: strip markdown fences, add missing prefixes."""
    normalized = (sparql or "").strip()
    if not normalized:
        return ""

    normalized = strip_llm_reasoning_blocks(normalized)
    normalized = re.sub(r"^\s*```(?:sparql)?\s*|\s*```\s*$", "", normalized, flags=re.IGNORECASE | re.MULTILINE).strip()

    # Ensure standard prefixes are present
    standard_prefixes = {
        "wm:": 'PREFIX wm: <https://wealth.example.org/ontology/>',
        "kg:": 'PREFIX kg: <https://wealth.example.org/kg/>',
        "rdf:": 'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>',
        "rdfs:": 'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>',
        "xsd:": 'PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>',
        "schema1:": 'PREFIX schema1: <http://schema.org/>',
        "wmmeta:": 'PREFIX wmmeta: <https://wealth.example.org/metadata/>',
    }
    upper_query = normalized.upper()
    for prefix_alias, prefix_line in standard_prefixes.items():
        if prefix_alias in normalized and prefix_alias.upper().replace(":", ":") not in re.findall(
            r"PREFIX\s+(\S+:)", upper_query
        ):
            normalized = prefix_line + "\n" + normalized

    return normalized


def parse_llm_json(raw_text: str, default: Any, context: str) -> Any:
    """Robustly extract JSON from LLM responses."""
    text = (raw_text or "").strip()
    if not text:
        print(f"[WARN] Empty JSON response from {context}; using default.")
        return default

    text = text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    # Also strip reasoning blocks
    text = re.sub(r"(?is)<reasoning>.*?</reasoning>", "", text)
    text = re.sub(r"(?is)<think>.*?</think>", "", text).strip()

    candidates = [text]

    object_start = text.find("{")
    object_end = text.rfind("}")
    if object_start != -1 and object_end > object_start:
        candidates.append(text[object_start : object_end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    preview = text[:300].replace("\n", " ")
    print(f"[WARN] Invalid JSON response from {context}; using default. Preview: {preview}")
    return default


def is_quota_exhaustion_error(error: Any) -> bool:
    msg = str(error).lower()
    return any(marker in msg for marker in ("rate limit", "ratelimit", "quota", "throttl", "429", "too many requests"))


class GraderOutputError(RuntimeError):
    """Raised when the grader response is empty, truncated, or not valid JSON."""


# ---------------------------------------------------------------------------
# 5. SCHEMA LOADING (from Fuseki + rdflib schema TTL)
# ---------------------------------------------------------------------------

def normalize_schema_attribute_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if any(m in normalized for m in ("decimal", "integer", "float", "double", "numeric", "number")):
        return "numeric"
    if any(m in normalized for m in ("string", "text", "date", "categorical")):
        return "categorical_string"
    return "unknown"


def schema_datatype_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def extract_schema_datatypes_by_property(g: rdflib.Graph) -> Dict[str, str]:
    attribute_name_predicates = {
        rdflib.URIRef("https://wealth.example.org/ontology/attributeName"),
        rdflib.URIRef("https://wealth.example.org/ontology/derivedName"),
    }
    attribute_type_predicate = rdflib.URIRef("https://wealth.example.org/ontology/attributeType")
    datatypes: Dict[str, str] = {}

    for attr_uri, _, attr_type in g.triples((None, attribute_type_predicate, None)):
        datatype = normalize_schema_attribute_type(attr_type)
        if datatype == "unknown":
            continue
        for name_predicate in attribute_name_predicates:
            attr_name = g.value(attr_uri, name_predicate)
            if attr_name is not None:
                datatypes[schema_datatype_key(attr_name)] = datatype
    return datatypes


def load_rdf_knowledge_graph(schema_file: str) -> Dict[str, Any]:
    """
    Load the RDF schema from the TTL file via rdflib and dynamic properties from Fuseki.
    Returns a dict mapping class names to their properties/datatypes.
    """
    print("[SYSTEM] Loading RDF Knowledge Graph metadata from schema + Fuseki...")
    g = rdflib.Graph()
    g.parse(schema_file, format="turtle")
    schema_datatypes_by_property = extract_schema_datatypes_by_property(g)

    kg_metadata: Dict[str, Any] = {}

    # Find all Classes in the schema
    for s, p, o in g.triples((None, rdflib.RDF.type, rdflib.OWL.Class)):
        class_name = local_name(s)
        if "__" not in class_name:
            label = str(g.value(s, rdflib.RDFS.label)) if g.value(s, rdflib.RDFS.label) else class_name
            kg_metadata[class_name] = {
                "name": label,
                "description": "",
                "columns": set(),
                "property_datatypes": {},
            }

    # Extract dynamic properties from the Fuseki-hosted instance graph
    metadata_query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT ?class ?p ?datatype ?targetClass
WHERE {
  ?s rdf:type ?class .
  ?s ?p ?o .
  FILTER(STRSTARTS(STR(?class), "https://wealth.example.org/ontology/"))
  FILTER(!STRSTARTS(STR(?p), "http://www.w3.org/"))
  OPTIONAL {
    FILTER(isLiteral(?o))
    BIND(DATATYPE(?o) AS ?datatype)
  }
  OPTIONAL {
    FILTER(isIRI(?o))
    ?o rdf:type ?targetClass .
    FILTER(STRSTARTS(STR(?targetClass), "https://wealth.example.org/ontology/"))
  }
}
"""
    metadata_result = execute_sparql_on_fuseki(metadata_query, FUSEKI_ENDPOINT, FUSEKI_METADATA_TIMEOUT_SECONDS)
    if metadata_result.get("status") != "success":
        print(f"[WARN] Fuseki metadata extraction failed: {metadata_result.get('error_message')}")
        print("[WARN] Continuing with schema classes only.")
    else:
        for row in metadata_result.get("data", []):
            class_name = local_name(row.get("class", ""))
            if class_name not in kg_metadata:
                kg_metadata[class_name] = {
                    "name": class_name,
                    "description": "",
                    "columns": set(),
                    "property_datatypes": {},
                }
            prop_name = local_name(row.get("p", ""))
            if not prop_name:
                continue
            kg_metadata[class_name]["columns"].add(prop_name)

            schema_datatype = schema_datatypes_by_property.get(schema_datatype_key(prop_name))
            datatype = str(row.get("datatype", "") or "").lower()
            target_class = row.get("targetClass", "")
            if target_class:
                kg_metadata[class_name]["property_datatypes"][prop_name] = (
                    f"object_reference (points to: {local_name(target_class)})"
                )
            elif schema_datatype:
                kg_metadata[class_name]["property_datatypes"][prop_name] = schema_datatype
            elif any(m in datatype for m in ("decimal", "integer", "float", "double")):
                kg_metadata[class_name]["property_datatypes"][prop_name] = "numeric"
            else:
                kg_metadata[class_name]["property_datatypes"][prop_name] = "categorical_string"

    # Convert sets to structured lists
    for class_name in kg_metadata:
        formatted_columns = []
        for prop in kg_metadata[class_name]["columns"]:
            dtype = kg_metadata[class_name]["property_datatypes"].get(prop, "unknown")
            formatted_columns.append({"name": prop, "type": "Property", "datatype": dtype})
        kg_metadata[class_name]["columns"] = formatted_columns

    print(f"[SYSTEM] Successfully loaded {len(kg_metadata)} classes with Fuseki dynamic properties.")
    return kg_metadata


# ---------------------------------------------------------------------------
# 6. FUSEKI SPARQL EXECUTION
# ---------------------------------------------------------------------------

def parse_fuseki_sparql_json(payload: Dict[str, Any]) -> list:
    """Convert Fuseki SELECT/ASK JSON responses into the pipeline's row format."""
    if "boolean" in payload:
        return [{"boolean": str(bool(payload.get("boolean"))).lower()}]

    vars_order = payload.get("head", {}).get("vars", [])
    bindings = payload.get("results", {}).get("bindings", [])
    data = []
    for binding in bindings:
        row_dict = {}
        for var in vars_order:
            value = binding.get(var, {})
            if isinstance(value, dict):
                row_dict[str(var)] = str(value.get("value", ""))
            else:
                row_dict[str(var)] = ""
        data.append(row_dict)
    return data


def execute_sparql_on_fuseki(
    sparql_query: str,
    endpoint: str = FUSEKI_ENDPOINT,
    timeout_seconds: float = FUSEKI_SCAN_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Execute SPARQL through Apache Jena Fuseki and return results."""
    try:
        request_body = urllib.parse.urlencode({"query": sparql_query}).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=request_body,
            method="POST",
            headers={
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
        payload = json.loads(response_body)
        data = parse_fuseki_sparql_json(payload)
        return {
            "status": "success",
            "data": data,
            "row_count": len(data),
            "sparql": sparql_query,
        }
    except socket.timeout:
        return {
            "status": "error",
            "error_message": f"Fuseki SPARQL execution timed out after {timeout_seconds:g} seconds.",
            "failed_sparql": sparql_query,
        }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {
            "status": "error",
            "error_message": f"Fuseki HTTP {e.code}: {error_body[:500] or str(e)}",
            "failed_sparql": sparql_query,
        }
    except urllib.error.URLError as e:
        return {
            "status": "error",
            "error_message": f"Fuseki connection error: {e.reason}",
            "failed_sparql": sparql_query,
        }
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "error_message": f"Fuseki returned non-JSON SPARQL results: {e}",
            "failed_sparql": sparql_query,
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "failed_sparql": sparql_query,
        }


def check_fuseki_health(endpoint: str = FUSEKI_ENDPOINT) -> None:
    health_query = "ASK { ?s ?p ?o . }"
    result = execute_sparql_on_fuseki(health_query, endpoint, 10.0)
    if result.get("status") == "success":
        print("[SYSTEM] Fuseki health check passed.")
        return
    raise RuntimeError(
        f"Fuseki is not reachable. Endpoint: {endpoint}. "
        f"Error: {result.get('error_message')}. Start Fuseki first."
    )


# ---------------------------------------------------------------------------
# 7. BUILD SCHEMA TEXT FOR LLM PROMPT
# ---------------------------------------------------------------------------

def build_schema_text(kg_metadata: Dict[str, Any]) -> str:
    """Format the KG schema into a readable string for the LLM prompt."""
    lines = []
    for class_name, details in kg_metadata.items():
        if not isinstance(details, dict):
            continue
        columns = details.get("columns", [])
        if not columns:
            continue
        lines.append(f"Class: {class_name}")
        for col in columns:
            if isinstance(col, dict):
                lines.append(f"  - {col.get('name', '?')} ({col.get('datatype', 'unknown')})")
            else:
                lines.append(f"  - {col}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 8. STEP 2 — GENERATE SPARQL
# ---------------------------------------------------------------------------

def generate_sparql(
    query: str,
    schema_text: str,
    kg_metadata: Dict[str, Any],
    client: LLMClient,
    model: str,
    attempt: int = 1,
    previous_sparql: str = "",
    previous_error: str = "",
    previous_result: str = "",
) -> str:
    """
    Step 2: LLM generates a SPARQL query from the natural language query + schema.
    On retry, includes the previous failed SPARQL and error feedback.
    """

    retry_context = ""
    if attempt > 1 and previous_sparql:
        retry_context = f"""
WARNING: This is retry attempt {attempt} of {MAX_RETRIES}. Your previous SPARQL query did not produce the correct answer.
Previous Failed SPARQL:
{previous_sparql}

Previous Result (if any):
{previous_result}

You MUST rewrite the query differently. Analyze what went wrong and fix it.
"""

    prompt = f"""You are a SPARQL query generator for an RDF Knowledge Graph about wealth management.

User Query: "{query}"

RDF Knowledge Graph Schema:
{schema_text}

{retry_context}

Return ONLY raw SPARQL text. Do not explain. Do not include <reasoning>, <think>, markdown, comments, or prose.
The first non-whitespace characters in your response must be PREFIX or SELECT.

CRITICAL SPARQL RULES:

RULE 1 (PREFIXES): You MUST include these exact prefixes:
    PREFIX wm: <https://wealth.example.org/ontology/>
    PREFIX kg: <https://wealth.example.org/kg/>
    PREFIX wmmeta: <https://wealth.example.org/metadata/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX schema1: <http://schema.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

RULE 2 (RDF TYPES): Always anchor entities with rdf:type. Example: ?investor rdf:type wm:InvestorProfile .

RULE 3 (MATH & AGGREGATION): RDF stores values as strings. For aggregations (SUM, AVG) or math, MUST cast variables to decimal: e.g., SUM(xsd:decimal(?value)).
Never put aggregate functions like SUM, AVG, COUNT, MIN, or MAX inside BIND or OPTIONAL blocks.
Put aggregate expressions in SELECT, for example `(SUM(xsd:decimal(?amount)) AS ?totalAmount)`, and use GROUP BY for non-aggregated selected variables.

RULE 4 (CASE-INSENSITIVE FILTERS): When filtering by text or IDs, use lowercase comparison.
Example: FILTER(CONTAINS(LCASE(STR(?id)), "inv-001")).

RULE 5 (NEGATION): If the user query contains "never", "not", "excluding", "without", or "no X", use FILTER NOT EXISTS or MINUS.

RULE 6 (LABELS OVER IRIs): For controlled-vocabulary classes (InvestmentType, Sector, Segment, RiskCategory), always follow the label property to get the human-readable string.

RULE 7 (COUNT): Use COUNT(?id) by default. Use COUNT(DISTINCT ?id) only when the user asks for distinct/unique values.

RULE 8 (MONTH GROUPING): If the query asks "per month", "for each month", or "monthly", extract YYYY-MM from date strings. Use BIND(SUBSTR(STR(?date), 1, 7) AS ?month) and GROUP BY ?month.

RULE 9 (NULL GROUPS): For "for each", "by", "per" group-by questions, do not drop rows because the group field is missing. Use OPTIONAL for the group field and COALESCE to "NULL".

RULE 10 (JOIN SAFETY): Do not create flat joins between two classes through literal properties when both sides have many values. Aggregate each class separately in subqueries first, then join.

RULE 11 (VOCABULARY): Use only classes and predicates from the Schema above. Do NOT invent properties. Use wm: namespace properties, not schema1: properties, in graph patterns.
"""

    api_logger.log_call(query, f"Generate_attempt_{attempt}")
    request_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Some models don't support temperature
    if not model.lower().startswith("gpt-5"):
        request_kwargs["temperature"] = 0.0

    response = client.chat.completions.create(**request_kwargs)
    result = response.choices[0].message.content.strip()

    # Extract SPARQL from possible markdown wrapping
    if "```" in result:
        parts = result.split("```")
        if len(parts) >= 3:
            code_block = parts[1]
            if code_block.lower().startswith("sparql"):
                code_block = code_block[6:]
            sparql_query = code_block.strip()
        else:
            sparql_query = result.replace("```sparql", "").replace("```SPARQL", "").replace("```", "").strip()
    else:
        sparql_query = result.strip()

    return repair_sparql_query(sparql_query)


# ---------------------------------------------------------------------------
# 9. STEP 3 — EXECUTE SPARQL
# ---------------------------------------------------------------------------

def execute_sparql(sparql: str) -> Dict[str, Any]:
    """
    Step 3: Execute the generated SPARQL against Fuseki and return the result.
    Returns dict with 'status', 'data', 'row_count', or error info.
    """
    if not sparql or not sparql.strip():
        return {
            "status": "error",
            "error_message": "Empty SPARQL query — nothing to execute.",
            "data": [],
            "row_count": 0,
        }
    return execute_sparql_on_fuseki(sparql, FUSEKI_ENDPOINT, FUSEKI_SCAN_TIMEOUT_SECONDS)


# ---------------------------------------------------------------------------
# 10. FORMAT RESULTS FOR GRADING
# ---------------------------------------------------------------------------

def normalize_value_for_answer(value: Any) -> Any:
    """Normalize a single value for answer comparison."""
    text = str(value or "").strip()
    if not text:
        return ""
    # Try to normalize numeric values
    try:
        d = Decimal(text)
        # Round to 2 decimal places for comparison
        return str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        pass
    return text


def format_result_for_grading(scan_result: Dict[str, Any]) -> str:
    """Format SPARQL execution results into a readable string for the grader."""
    if scan_result.get("status") != "success":
        return f"EXECUTION ERROR: {scan_result.get('error_message', 'Unknown error')}"

    data = scan_result.get("data", [])
    if not data:
        return "No results returned (empty result set)."

    row_count = len(data)
    if row_count == 1 and len(data[0]) == 1:
        # Single scalar result
        key = list(data[0].keys())[0]
        return normalize_value_for_answer(data[0][key])

    # Multi-row or multi-column result
    lines = []
    for i, row in enumerate(data[:50]):  # Cap at 50 rows for the grader prompt
        formatted_values = []
        for k, v in row.items():
            formatted_values.append(f"{k}: {normalize_value_for_answer(v)}")
        lines.append(", ".join(formatted_values))

    result_text = "\n".join(lines)
    if row_count > 50:
        result_text += f"\n... ({row_count - 50} more rows truncated)"
    return result_text


# ---------------------------------------------------------------------------
# 11. STEP 4 — LLM GRADER
# ---------------------------------------------------------------------------

def truncate_for_prompt(value: str, max_chars: int = 60000) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head
    return text[:head] + "\n...[TRUNCATED_FOR_PROMPT]...\n" + text[-tail:]


def llm_grade(
    query: str,
    scan_raw_rows: str,
    ground_truth: str,
    client: LLMClient,
    model: str,
) -> Dict[str, Any]:
    """
    Step 4: LLM compares the pipeline scan raw rows against the known ground truth.
    Returns dict with 'verdict' (MATCH/PARTIAL/MISMATCH/OTHER) and 'reason'.
    """

    prompt = f"""
You are a strict but fair evaluator for a finance knowledge-graph QA benchmark.

You will receive:
1. The user question.
2. The SQL-derived ground truth JSON.
3. The pipeline scan raw rows JSON.

Your task:
Decide whether the pipeline scan raw rows correctly answer the user question, using the ground truth as the reference.

Important grading rule:
Compare only the information required by the question. If the ground truth contains extra fields that are not needed to answer the question, do not penalize the pipeline for omitting them. Extra harmless columns in the pipeline output are also acceptable if the requested answer is correct.

What to check:
- Required rows/entities: Are the required investors, holdings, goals, transactions, groups, or records present?
- Required values: Are the values required by the question the same as the ground truth values?
- Required columns/metrics: Are all values needed to answer the question present, even if column names differ?
- Filters/conditions: Did the result apply the question's filters correctly?
- Grouping: If the question asks "for each" or "across", are the correct groups present?
- Aggregation: If the question asks count, sum, average, min, max, total, net, etc., are the computed values correct and equal to the ground truth?
- Ranking/order: If the question asks top, bottom, highest, lowest, greatest, least, first, latest, or ordered results, is the ranking/order and limit correct?
- Entity sets: If the question asks for a list/set of entities, compare the entity set. Missing required entities or extra wrong entities should not be MATCH.
- Empty results: If ground truth is empty and the question expects no matching records, an empty scan result can be MATCH. If ground truth is non-empty and scan result is empty, it is usually MISMATCH.
- Extra rows: Extra incorrect rows should reduce the grade. If the correct answer is present but extra wrong rows are included, use PARTIAL unless the extras do not affect the requested answer.
- Field-name differences: Do not require identical field names when the meaning and values clearly correspond.
- Numeric formatting: Treat numeric strings and numbers as equivalent when values are materially the same.
- Numeric tolerance: If the ground truth contains numeric value X, treat the scan value as correct when it is between X - 1.5 and X + 1.5, unless the question explicitly requires exact precision.
- Column resolution: Do not require identical column names. Resolve meaning semantically from the question, ground truth fields, and scan fields. For example, investor id, investor profile, group labels, percentages, averages, totals, and counts may use different aliases if the required meaning is present.

Label definitions:
MATCH:
Use MATCH when the scan raw rows completely answer what the question asks. The answer must have the required rows/entities, values, filters, grouping, aggregation, and ranking/order when applicable. All values required by the question must be semantically equal to the ground truth values. Missing unused ground-truth fields or extra harmless columns are okay.

PARTIAL:
Use PARTIAL when the scan raw rows answer part of the question correctly, but some required information is missing, incomplete, extra, or wrong. Examples: some correct rows but missing others, correct grouping but one metric wrong/missing, correct entities but wrong aggregation, correct top results but wrong order, correct values for some but not all groups, or correct answer plus extra wrong rows.

MISMATCH:
Use MISMATCH when the scan raw rows do not answer the question, are mostly wrong, use wrong filters/entities, use wrong aggregation/ranking, return empty when the ground truth has required results, have required values that conflict with the ground truth, or are unrelated to the ground truth.

OTHER:
Use OTHER only when the input is impossible to judge, malformed beyond interpretation, or the ground truth itself is unusable. Do not use OTHER just because the answer is wrong; use MISMATCH for wrong answers.

Return only JSON with this schema:
{{
  "status": "MATCH" | "MISMATCH" | "PARTIAL" | "OTHER",
  "reason": "short explanation",
  "evidence": {{
    "main_correct_parts": [],
    "main_missing_or_wrong_parts": []
  }}
}}

Question:
{truncate_for_prompt(query, 8000)}

Ground Truth JSON:
{truncate_for_prompt(ground_truth)}

Pipeline Scan Raw Rows:
{truncate_for_prompt(scan_raw_rows)}
""".strip()

    api_logger.log_call(query, "Direct_LLM_Grade")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict senior finance benchmark grader with 15 years of experience evaluating "
                    "wealth-management database answers. Return only valid JSON; no markdown or prose outside JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    if not response.choices:
        raise GraderOutputError("Direct grader returned no choices.")
    finish_reason = str(response.choices[0].finish_reason or "").lower()
    if finish_reason == "length":
        raise GraderOutputError("Direct grader output was truncated: finish_reason=length.")
    raw = response.choices[0].message.content
    if not raw or not raw.strip():
        raise GraderOutputError("Direct grader returned empty output.")

    result = parse_llm_json(
        raw,
        {
            "status": "OTHER",
            "reason": "Direct grader returned empty or invalid JSON output.",
            "evidence": {"main_correct_parts": [], "main_missing_or_wrong_parts": []},
        },
        "Direct_LLM_Grade",
    )
    if not isinstance(result, dict):
        result = {
            "status": "OTHER",
            "reason": "Grader returned non-dict response.",
            "evidence": {"main_correct_parts": [], "main_missing_or_wrong_parts": []},
        }

    verdict = str(result.get("status", result.get("verdict", "OTHER"))).strip().upper()
    if verdict not in ("MATCH", "PARTIAL", "MISMATCH", "OTHER"):
        verdict = "OTHER"

    return {
        "verdict": verdict,
        "reason": str(result.get("reason", "")),
        "evidence": result.get("evidence", {}),
    }


# ---------------------------------------------------------------------------
# 12. DATASET LOADING
# ---------------------------------------------------------------------------

def load_input_samples(sample_file: str) -> pd.DataFrame:
    """Load benchmark questions from CSV or XLSX."""
    extension = os.path.splitext(sample_file)[1].lower()
    if extension in {".xlsx", ".xls"}:
        return pd.read_excel(sample_file)
    return pd.read_csv(sample_file)


# ---------------------------------------------------------------------------
# 13. MAIN PIPELINE
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("  BASE PIPELINE — Qwen 3 235B Text-to-SPARQL")
    print("=" * 60)

    # --- Configuration ---
    print(f"[CONFIG] Target model (SPARQL generation): {TARGET_MODEL}")
    print(f"[CONFIG] Grader model: {GRADER_MODEL}")
    print(f"[CONFIG] Max retries: {MAX_RETRIES}")
    print(f"[CONFIG] Pipeline version: {PIPELINE_VERSION}")
    print(f"[CONFIG] Fuseki endpoint: {FUSEKI_ENDPOINT}")
    print(f"[CONFIG] Query window: offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT}")
    print(f"[CONFIG] Report file: {REPORT_FILE}")
    script_start_time = time.perf_counter()

    # --- Health check ---
    print("\n[SYSTEM] Checking Fuseki connectivity...")
    check_fuseki_health()

    # --- Build clients ---
    print("[SYSTEM] Building API clients...")
    target_client = build_target_client()
    grader_client = build_grader_client()

    # --- Step 1: Load INPUT (Schema) ---
    print(f"\n[STEP 1] Loading schema from {SCHEMA_FILE}...")
    kg_metadata = load_rdf_knowledge_graph(SCHEMA_FILE)
    if not kg_metadata:
        print("[ERROR] Could not load Knowledge Graph schema. Exiting.")
        return
    schema_text = build_schema_text(kg_metadata)
    print(f"[STEP 1] Schema loaded: {len(kg_metadata)} classes.")

    # --- Step 1: Load INPUT (Dataset) ---
    print(f"\n[STEP 1] Loading dataset from {INPUT_SAMPLE_FILE}...")
    try:
        df_all = load_input_samples(INPUT_SAMPLE_FILE)
    except Exception as e:
        print(f"[ERROR] Failed to load dataset: {e}")
        return

    # Normalize column names
    if {"question", "ground_truth_answer"}.issubset(df_all.columns):
        records = pd.DataFrame({
            "Sample Row ID": df_all.get("global_question_id", pd.Series(range(1, len(df_all) + 1))).astype(str),
            "Question": df_all["question"].astype(str),
            "Ground Truth": df_all["ground_truth_answer"].astype(str),
            "Difficulty": df_all.get("difficulty", pd.Series([""] * len(df_all))).astype(str),
            "Category": df_all.get("category", pd.Series([""] * len(df_all))).astype(str),
            "Query Type": df_all.get("query_type", pd.Series([""] * len(df_all))).astype(str),
            "Source CSV": df_all.get("source_csv", pd.Series([""] * len(df_all))).astype(str),
        })
    else:
        print(f"[ERROR] Dataset must have 'question' and 'ground_truth_answer' columns. Found: {list(df_all.columns)}")
        return

    test_records = records.iloc[TEST_QUERY_OFFSET : TEST_QUERY_OFFSET + TEST_QUERY_LIMIT].to_dict(orient="records")
    print(f"[STEP 1] Loaded {len(test_records)} queries for evaluation.")

    # --- Report columns ---
    report_columns = [
        "Pipeline Version",
        "Sample Row ID",
        "Question",
        "Ground Truth",
        "Difficulty",
        "Category",
        "Query Type",
        "Source CSV",
        "Pipeline Result",
        "New Status",
        "Grader Verdict",
        "Grader Reason",
        "Attempts Used",
        "Generated SPARQL (Final)",
        "Scan Status",
        "Scan Row Count",
        "Scan Error",
        "All Attempts Log",
        "Started At",
        "Elapsed Seconds",
    ]

    def save_report(rows: list):
        df_report = pd.DataFrame(rows)
        for col in report_columns:
            if col not in df_report.columns:
                df_report[col] = ""
        df_report = df_report[report_columns]
        tmp_file = f"{REPORT_FILE}.tmp"
        df_report.to_csv(tmp_file, index=False)
        os.replace(tmp_file, REPORT_FILE)

    # --- Resume logic ---
    results_list: list = []
    completed_row_ids: set = set()
    if os.path.exists(REPORT_FILE):
        try:
            existing = pd.read_csv(REPORT_FILE)
            if "Sample Row ID" in existing.columns:
                # Retry CRASH and QUOTA_EXHAUSTED rows
                status_series = existing.get("New Status", pd.Series(dtype=str)).astype(str).str.upper()
                keep_mask = ~status_series.isin({"CRASH", "QUOTA_EXHAUSTED"})
                existing = existing[keep_mask].copy()
                results_list = existing.to_dict(orient="records")
                completed_row_ids = set(existing["Sample Row ID"].astype(str))
                print(f"[RESUME] Found {len(results_list)} completed rows. Skipping them.")
        except Exception as e:
            print(f"[WARN] Could not read existing report: {e}. Starting fresh.")

    pending_records = [r for r in test_records if str(r.get("Sample Row ID", "")) not in completed_row_ids]
    skipped = len(test_records) - len(pending_records)
    if skipped:
        print(f"[RESUME] Skipping {skipped} already-completed queries.")
    print(f"[SYSTEM] Pending queries this run: {len(pending_records)}")

    # --- Process each query ---
    for idx, record in enumerate(pending_records, 1):
        query_start = time.perf_counter()
        started_at = datetime.datetime.now().isoformat(timespec="seconds")
        query = sanitize_user_query(record.get("Question", ""))
        ground_truth = str(record.get("Ground Truth", ""))
        sample_row_id = record.get("Sample Row ID", "")
        row_metadata = {
            "Difficulty": record.get("Difficulty", ""),
            "Category": record.get("Category", ""),
            "Query Type": record.get("Query Type", ""),
            "Source CSV": record.get("Source CSV", ""),
        }

        print(f"\n{'─' * 60}")
        print(f"[{idx}/{len(pending_records)}] Row {sample_row_id}: {query[:80]}...")

        attempts_log: List[Dict[str, Any]] = []
        final_status = "FAILURE"
        final_result = ""
        final_sparql = ""
        final_verdict = "MISMATCH"
        final_reason = ""
        final_scan_status = ""
        final_scan_row_count = ""
        final_scan_error = ""
        attempts_used = 0

        try:
            for attempt in range(1, MAX_RETRIES + 1):
                attempts_used = attempt
                print(f"  [Attempt {attempt}/{MAX_RETRIES}]")

                # Previous attempt feedback (for retries)
                prev_sparql = attempts_log[-1]["sparql"] if attempts_log else ""
                prev_error = attempts_log[-1]["error"] if attempts_log else ""
                prev_result = attempts_log[-1]["result_text"] if attempts_log else ""

                # ── STEP 2: GENERATE SPARQL ──
                print(f"    → Generating SPARQL via {TARGET_MODEL}...")
                try:
                    sparql = generate_sparql(
                        query=query,
                        schema_text=schema_text,
                        kg_metadata=kg_metadata,
                        client=target_client,
                        model=TARGET_MODEL,
                        attempt=attempt,
                        previous_sparql=prev_sparql,
                        previous_error=prev_error,
                        previous_result=prev_result,
                    )
                except Exception as gen_err:
                    if is_quota_exhaustion_error(gen_err):
                        raise
                    print(f"    ✗ Generate failed: {gen_err}")
                    attempts_log.append({
                        "attempt": attempt,
                        "sparql": "",
                        "scan_status": "GENERATE_ERROR",
                        "result_text": "",
                        "error": str(gen_err),
                        "verdict": "MISMATCH",
                    })
                    continue

                if not sparql.strip():
                    print("    ✗ Empty SPARQL generated.")
                    attempts_log.append({
                        "attempt": attempt,
                        "sparql": "",
                        "scan_status": "EMPTY_SPARQL",
                        "result_text": "",
                        "error": "LLM returned empty SPARQL.",
                        "verdict": "MISMATCH",
                    })
                    continue

                # ── STEP 3: EXECUTE SPARQL ──
                print("    → Executing SPARQL on Fuseki...")
                scan_result = execute_sparql(sparql)
                scan_status = scan_result.get("status", "error")
                scan_error = scan_result.get("error_message", "")

                if scan_status != "success":
                    print(f"    ✗ Execution failed: {scan_error[:100]}")
                    attempts_log.append({
                        "attempt": attempt,
                        "sparql": sparql,
                        "scan_status": "SCAN_ERROR",
                        "result_text": "",
                        "error": scan_error,
                        "verdict": "MISMATCH",
                    })
                    continue

                result_text = format_result_for_grading(scan_result)
                scan_row_count = scan_result.get("row_count", 0)
                print(f"    ✓ Execution succeeded: {scan_row_count} rows returned.")

                # ── STEP 4: LLM GRADER ──
                print(f"    → Grading via {GRADER_MODEL}...")
                scan_raw_rows_json = json.dumps(scan_result.get("data", []), ensure_ascii=False)
                try:
                    grade_result = llm_grade(
                        query=query,
                        scan_raw_rows=scan_raw_rows_json,
                        ground_truth=ground_truth,
                        client=grader_client,
                        model=GRADER_MODEL,
                    )
                except Exception as grade_err:
                    if is_quota_exhaustion_error(grade_err):
                        raise
                    print(f"    ✗ Grading failed: {grade_err}")
                    attempts_log.append({
                        "attempt": attempt,
                        "sparql": sparql,
                        "scan_status": "success",
                        "scan_row_count": scan_row_count,
                        "result_text": result_text,
                        "error": f"Grading error: {grade_err}",
                        "verdict": "MISMATCH",
                    })
                    continue

                verdict = grade_result.get("verdict", "MISMATCH")
                reason = grade_result.get("reason", "")
                print(f"    → Verdict: {verdict} — {reason[:80]}")

                attempts_log.append({
                    "attempt": attempt,
                    "sparql": sparql,
                    "scan_status": "success",
                    "scan_row_count": scan_row_count,
                    "result_text": result_text,
                    "error": "" if verdict == "MATCH" else reason,
                    "verdict": verdict,
                })

                # ── STEP 5: DECISION ──
                if verdict == "MATCH":
                    final_status = "SUCCESS"
                    final_result = result_text
                    final_sparql = sparql
                    final_verdict = verdict
                    final_reason = reason
                    final_scan_status = "success"
                    final_scan_row_count = str(scan_row_count)
                    final_scan_error = ""
                    print(f"  ✓ SUCCESS on attempt {attempt}!")
                    break
                else:
                    # ── STEP 6: RETRY ──
                    if attempt < MAX_RETRIES:
                        print(f"  ↻ Retrying... ({attempt}/{MAX_RETRIES} used)")
                    else:
                        # Exhausted all retries
                        final_status = "FAILURE"
                        final_result = result_text
                        final_sparql = sparql
                        final_verdict = verdict
                        final_reason = reason
                        final_scan_status = "success"
                        final_scan_row_count = str(scan_row_count)
                        final_scan_error = ""
                        print(f"  ✗ FAILURE after {MAX_RETRIES} attempts.")

            # If all attempts had errors (no successful scan at all)
            if not any(a.get("scan_status") == "success" for a in attempts_log):
                last = attempts_log[-1] if attempts_log else {}
                final_status = "FAILURE"
                final_result = f"All {MAX_RETRIES} attempts failed."
                final_sparql = last.get("sparql", "")
                final_scan_status = last.get("scan_status", "ERROR")
                final_scan_error = last.get("error", "")

        except Exception as e:
            elapsed = round(time.perf_counter() - query_start, 3)
            is_quota = is_quota_exhaustion_error(e)
            row_result = {
                "Pipeline Version": PIPELINE_VERSION,
                "Sample Row ID": sample_row_id,
                "Question": query,
                "Ground Truth": ground_truth,
                **row_metadata,
                "Pipeline Result": f"ERROR: {e}",
                "New Status": "QUOTA_EXHAUSTED" if is_quota else "CRASH",
                "Grader Verdict": "",
                "Grader Reason": "",
                "Attempts Used": attempts_used,
                "Generated SPARQL (Final)": final_sparql,
                "Scan Status": "",
                "Scan Row Count": "",
                "Scan Error": str(e),
                "All Attempts Log": json.dumps(attempts_log, ensure_ascii=False),
                "Started At": started_at,
                "Elapsed Seconds": elapsed,
            }
            results_list.append(row_result)
            save_report(results_list)
            if is_quota:
                print("[SYSTEM] Quota exhausted. Stopping run. Resume later.")
                break
            print(f"  ✗ CRASH: {e}")
            continue

        elapsed = round(time.perf_counter() - query_start, 3)
        row_result = {
            "Pipeline Version": PIPELINE_VERSION,
            "Sample Row ID": sample_row_id,
            "Question": query,
            "Ground Truth": ground_truth,
            **row_metadata,
            "Pipeline Result": final_result,
            "New Status": final_status,
            "Grader Verdict": final_verdict,
            "Grader Reason": final_reason,
            "Attempts Used": attempts_used,
            "Generated SPARQL (Final)": final_sparql,
            "Scan Status": final_scan_status,
            "Scan Row Count": final_scan_row_count,
            "Scan Error": final_scan_error,
            "All Attempts Log": json.dumps(attempts_log, ensure_ascii=False),
            "Started At": started_at,
            "Elapsed Seconds": elapsed,
        }
        results_list.append(row_result)

        print(
            f"  [{final_status}] {final_verdict} in {elapsed:.1f}s "
            f"({idx}/{len(pending_records)} this run, "
            f"{len(results_list)}/{len(test_records)} total)"
        )

        # Incremental save
        save_report(results_list)
        if idx % 10 == 0 or idx == len(pending_records):
            api_logger.save()

    # --- Final summary ---
    api_logger.save()
    wall_clock = time.perf_counter() - script_start_time

    elapsed_values = []
    for r in results_list:
        try:
            elapsed_values.append(float(r.get("Elapsed Seconds", 0) or 0))
        except (TypeError, ValueError):
            pass

    total_time = sum(elapsed_values)
    avg_time = total_time / len(elapsed_values) if elapsed_values else 0.0

    success_count = sum(1 for r in results_list if str(r.get("New Status", "")).upper() == "SUCCESS")
    failure_count = sum(1 for r in results_list if str(r.get("New Status", "")).upper() == "FAILURE")
    crash_count = sum(1 for r in results_list if str(r.get("New Status", "")).upper() == "CRASH")

    print(f"\n{'=' * 60}")
    print("  PIPELINE RUN COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Report:       {REPORT_FILE}")
    print(f"  Total rows:   {len(results_list)}")
    print(f"  SUCCESS:      {success_count} ({100 * success_count / max(len(results_list), 1):.1f}%)")
    print(f"  FAILURE:      {failure_count} ({100 * failure_count / max(len(results_list), 1):.1f}%)")
    print(f"  CRASH:        {crash_count}")
    print(f"  Avg time/q:   {avg_time:.2f}s")
    print(f"  Total time:   {total_time:.1f}s ({total_time / 60:.1f}min)")
    print(f"  Wall clock:   {wall_clock:.1f}s ({wall_clock / 60:.1f}min)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
