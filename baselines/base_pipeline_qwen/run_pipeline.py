"""
Base Text-to-SPARQL Pipeline — GPT-OSS 120B, single-shot, ungraded, concurrent
================================================================================

Simplified pipeline for later offline grading:
  1. INPUT      — Query + Schema
  2. GENERATE   — LLM produces SPARQL from query + schema (single attempt, no retry)
  3. EXECUTE    — Run SPARQL against Fuseki triplestore
  4. STORE      — Save full raw result rows + timing/token metrics; no grading here

Model: openai.gpt-oss-120b-1:0 (via Bedrock)

Questions are processed concurrently (bounded thread pool) since there is no
grading call and no retry loop to serialize against.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import pandas as pd
import rdflib
from openai import OpenAI as LLMClient


# ---------------------------------------------------------------------------
# 0. ENVIRONMENT
# ---------------------------------------------------------------------------

def load_local_env_file() -> None:
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
            os.environ.setdefault(key.strip(), value)


load_local_env_file()

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASELINES_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(BASELINES_ROOT, ".."))
SCRIPT_DIFF_ROOT = os.path.join(REPO_ROOT, "script_diff_llm")

TARGET_MODEL = os.getenv("TARGET_MODEL", "openai.gpt-oss-120b-1:0")
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION", "base-pipeline-qwen-dir-gpt-oss-120b-single-shot-ungraded-v1")
TEST_QUERY_LIMIT = int(os.getenv("TEST_QUERY_LIMIT", "0"))  # 0 = all
TEST_QUERY_OFFSET = int(os.getenv("TEST_QUERY_OFFSET", "0"))
PIPELINE_WORKERS = int(os.getenv("PIPELINE_WORKERS", "8"))

FUSEKI_ENDPOINT = os.getenv("FUSEKI_ENDPOINT", "http://127.0.0.1:3030/wealth/query")
FUSEKI_SCAN_TIMEOUT_SECONDS = max(0.0, float(os.getenv("FUSEKI_SCAN_TIMEOUT_SECONDS", "60")))
FUSEKI_METADATA_TIMEOUT_SECONDS = max(0.0, float(os.getenv("FUSEKI_METADATA_TIMEOUT_SECONDS", "60")))

SCHEMA_FILE = os.getenv(
    "SCHEMA_FILE",
    os.path.join(SCRIPT_DIFF_ROOT, "kg", "wealth_management_diverse_schema.ttl"),
)
INPUT_SAMPLE_FILE = os.getenv(
    "INPUT_SAMPLE_FILE",
    os.path.join(BASELINES_ROOT, "dataset", "wealth_management_1000_questions.csv"),
)
OUTPUT_DIR = os.getenv("PIPELINE_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "output"))
REPORT_FILE = os.getenv(
    "REPORT_FILE",
    os.path.join(OUTPUT_DIR, f"base_pipeline_sparql_{TARGET_MODEL.replace('.', '_').replace('-', '_').replace(':', '_')}_ungraded.csv"),
)

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)


# ---------------------------------------------------------------------------
# 2. API CLIENT
# ---------------------------------------------------------------------------

def build_bedrock_runtime_client() -> LLMClient:
    """Bedrock OpenAI-compatible client (GPT-OSS 120B)."""
    api_key = (
        os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not api_key:
        raise RuntimeError("AWS_BEDROCK_API_KEY is required for the Bedrock endpoint.")
    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError("BEDROCK_REGION is required (e.g. us-east-1).")
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"
    return LLMClient(api_key=api_key, base_url=base_url, timeout=180, max_retries=1)


def build_bedrock_mantle_client() -> LLMClient:
    """Bedrock Mantle OpenAI-compatible client (non-GPT-OSS target models)."""
    api_key = (
        os.getenv("BEDROCK_MANTLE_API_KEY")
        or os.getenv("AWS_BEDROCK_API_KEY")
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
    return LLMClient(api_key=api_key, base_url=base_url, timeout=180, max_retries=1)


def build_target_client(model: str) -> LLMClient:
    if model.lower().startswith("openai.gpt-oss"):
        return build_bedrock_runtime_client()
    return build_bedrock_mantle_client()


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
    normalized = unicodedata.normalize("NFKD", raw_query).encode("ascii", "ignore").decode("utf-8")
    cleaned = re.sub(r"[^\x20-\x7E]", "", normalized)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else "Invalid Query"


def local_name(uri: Any) -> str:
    text = str(uri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rstrip("/").rsplit("/", 1)[-1]


def strip_llm_reasoning_blocks(text: str) -> str:
    cleaned = re.sub(r"(?is)<reasoning>.*?</reasoning>", "", text or "")
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
    sparql_start = re.search(r"(?im)^\s*(PREFIX|SELECT|ASK|CONSTRUCT|DESCRIBE)\b", cleaned)
    if sparql_start:
        cleaned = cleaned[sparql_start.start():]
    return cleaned.strip()


def repair_sparql_query(sparql: str, schema_namespaces: Dict[str, str]) -> str:
    """Normalize only namespace bindings supplied by the active RDF schema."""
    normalized = (sparql or "").strip()
    if not normalized:
        return ""
    normalized = strip_llm_reasoning_blocks(normalized)
    normalized = re.sub(r"^\s*```(?:sparql)?\s*|\s*```\s*$", "", normalized, flags=re.IGNORECASE | re.MULTILINE).strip()
    declarations = []
    for alias, iri in sorted(schema_namespaces.items()):
        prefix_token = f"{alias}:" if alias else ":"
        declaration = f"PREFIX {prefix_token} <{iri}>"
        declaration_pattern = rf"(?im)^\s*PREFIX\s+{re.escape(alias)}\s*:\s*<[^>]*>\s*$"
        usage_pattern = rf"(?<![A-Za-z0-9_-]){re.escape(prefix_token)}[A-Za-z_]"
        if re.search(declaration_pattern, normalized):
            normalized = re.sub(declaration_pattern, declaration, normalized)
        elif re.search(usage_pattern, normalized):
            declarations.append(declaration)
    if declarations:
        normalized = "\n".join(declarations + [normalized])
    return normalized


def is_quota_exhaustion_error(error: Any) -> bool:
    msg = str(error).lower()
    return any(marker in msg for marker in ("rate limit", "ratelimit", "quota", "throttl", "429", "too many requests"))


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
    """Read generic RDF/OWL range declarations when the TTL provides them."""
    datatypes: Dict[str, str] = {}
    for property_uri, _, range_uri in g.triples((None, rdflib.RDFS.range, None)):
        datatype = normalize_schema_attribute_type(range_uri)
        if datatype == "unknown":
            continue
        datatypes[schema_datatype_key(local_name(property_uri))] = datatype
    return datatypes


def schema_qname(graph: rdflib.Graph, uri: Any) -> str:
    """Return a schema-qualified RDF term, preserving the TTL namespace map."""
    text = str(uri or "")
    if not text:
        return ""
    try:
        prefix, _, local = graph.namespace_manager.compute_qname(text, generate=True)
        return f"{prefix}:{local}" if prefix else f":{local}"
    except Exception:
        return f"<{text}>"


def load_rdf_knowledge_graph(schema_file: str) -> tuple[Dict[str, Any], Dict[str, str]]:
    print("[SYSTEM] Loading RDF Knowledge Graph metadata from schema + Fuseki...")
    g = rdflib.Graph()
    g.parse(schema_file, format="turtle")
    schema_datatypes_by_property = extract_schema_datatypes_by_property(g)

    kg_metadata: Dict[str, Any] = {}
    for s, p, o in g.triples((None, rdflib.RDF.type, rdflib.OWL.Class)):
        class_uri = str(s)
        class_name = local_name(s)
        if "__" not in class_name:
            label = str(g.value(s, rdflib.RDFS.label)) if g.value(s, rdflib.RDFS.label) else class_name
            kg_metadata[class_uri] = {
                "name": label,
                "term": schema_qname(g, s),
                "columns": set(),
                "property_datatypes": {},
            }

    class_values = " ".join(f"<{uri}>" for uri in sorted(kg_metadata))
    metadata_query = f"""
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT DISTINCT ?class ?p ?datatype ?targetClass
WHERE {{
  VALUES ?class {{ {class_values} }}
  ?s rdf:type ?class .
  ?s ?p ?o .
  FILTER(?p != rdf:type)
  OPTIONAL {{ FILTER(isLiteral(?o)) BIND(DATATYPE(?o) AS ?datatype) }}
  OPTIONAL {{
    FILTER(isIRI(?o)) ?o rdf:type ?targetClass .
  }}
}}
"""
    metadata_result = execute_sparql_on_fuseki(metadata_query, FUSEKI_ENDPOINT, FUSEKI_METADATA_TIMEOUT_SECONDS)
    if metadata_result.get("status") != "success":
        print(f"[WARN] Fuseki metadata extraction failed: {metadata_result.get('error_message')}")
        print("[WARN] Continuing with schema classes only.")
    else:
        for row in metadata_result.get("data", []):
            class_uri = str(row.get("class", ""))
            class_name = local_name(class_uri)
            if class_uri not in kg_metadata:
                kg_metadata[class_uri] = {
                    "name": class_name,
                    "term": schema_qname(g, class_uri),
                    "columns": set(),
                    "property_datatypes": {},
                }
            prop_uri = str(row.get("p", ""))
            prop_name = local_name(prop_uri)
            if not prop_uri or not prop_name:
                continue
            kg_metadata[class_uri]["columns"].add(prop_uri)
            schema_datatype = schema_datatypes_by_property.get(schema_datatype_key(prop_name))
            datatype = str(row.get("datatype", "") or "").lower()
            target_class = row.get("targetClass", "")
            if target_class:
                kg_metadata[class_uri]["property_datatypes"][prop_uri] = (
                    f"object_reference (points to: {schema_qname(g, target_class)})"
                )
            elif schema_datatype:
                kg_metadata[class_uri]["property_datatypes"][prop_uri] = schema_datatype
            elif any(m in datatype for m in ("decimal", "integer", "float", "double")):
                kg_metadata[class_uri]["property_datatypes"][prop_uri] = "numeric"
            else:
                kg_metadata[class_uri]["property_datatypes"][prop_uri] = "categorical_string"

    for class_uri in kg_metadata:
        formatted_columns = []
        for prop_uri in kg_metadata[class_uri]["columns"]:
            dtype = kg_metadata[class_uri]["property_datatypes"].get(prop_uri, "unknown")
            formatted_columns.append({
                "name": schema_qname(g, prop_uri),
                "uri": prop_uri,
                "type": "Property",
                "datatype": dtype,
            })
        kg_metadata[class_uri]["columns"] = formatted_columns

    print(f"[SYSTEM] Successfully loaded {len(kg_metadata)} classes with Fuseki dynamic properties.")
    schema_namespaces = {
        str(prefix or ""): str(namespace)
        for prefix, namespace in g.namespaces()
    }
    return kg_metadata, schema_namespaces


# ---------------------------------------------------------------------------
# 6. FUSEKI SPARQL EXECUTION
# ---------------------------------------------------------------------------

def parse_fuseki_sparql_json(payload: Dict[str, Any]) -> list:
    if "boolean" in payload:
        return [{"boolean": str(bool(payload.get("boolean"))).lower()}]
    vars_order = payload.get("head", {}).get("vars", [])
    bindings = payload.get("results", {}).get("bindings", [])
    data = []
    for binding in bindings:
        row_dict = {}
        for var in vars_order:
            value = binding.get(var, {})
            row_dict[str(var)] = str(value.get("value", "")) if isinstance(value, dict) else ""
        data.append(row_dict)
    return data


def execute_sparql_on_fuseki(
    sparql_query: str,
    endpoint: str = FUSEKI_ENDPOINT,
    timeout_seconds: float = FUSEKI_SCAN_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
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
        return {"status": "success", "data": data, "row_count": len(data), "sparql": sparql_query}
    except socket.timeout:
        return {"status": "error", "error_message": f"Fuseki SPARQL execution timed out after {timeout_seconds:g} seconds.", "failed_sparql": sparql_query}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"status": "error", "error_message": f"Fuseki HTTP {e.code}: {error_body[:500] or str(e)}", "failed_sparql": sparql_query}
    except urllib.error.URLError as e:
        return {"status": "error", "error_message": f"Fuseki connection error: {e.reason}", "failed_sparql": sparql_query}
    except json.JSONDecodeError as e:
        return {"status": "error", "error_message": f"Fuseki returned non-JSON SPARQL results: {e}", "failed_sparql": sparql_query}
    except Exception as e:
        return {"status": "error", "error_message": str(e), "failed_sparql": sparql_query}


def check_fuseki_health(endpoint: str = FUSEKI_ENDPOINT) -> None:
    result = execute_sparql_on_fuseki("ASK { ?s ?p ?o . }", endpoint, 10.0)
    if result.get("status") == "success":
        print("[SYSTEM] Fuseki health check passed.")
        return
    raise RuntimeError(f"Fuseki is not reachable. Endpoint: {endpoint}. Error: {result.get('error_message')}. Start Fuseki first.")


# ---------------------------------------------------------------------------
# 7. BUILD SCHEMA TEXT FOR LLM PROMPT
# ---------------------------------------------------------------------------

def build_schema_text(kg_metadata: Dict[str, Any], schema_namespaces: Dict[str, str]) -> str:
    used_prefixes = set()
    for details in kg_metadata.values():
        terms = [str(details.get("term", ""))]
        for col in details.get("columns", []):
            if isinstance(col, dict):
                terms.extend((str(col.get("name", "")), str(col.get("datatype", ""))))
        for term in terms:
            used_prefixes.update(re.findall(r"(?<![A-Za-z0-9_-])([A-Za-z][\w-]*):[A-Za-z_]", term))

    lines = ["Namespace bindings:"]
    for prefix in sorted(used_prefixes):
        iri = schema_namespaces.get(prefix)
        if iri:
            lines.append(f"PREFIX {prefix}: <{iri}>")
    lines.append("")

    sorted_classes = sorted(
        kg_metadata.values(), key=lambda details: str(details.get("term", details.get("name", "")))
    )
    for details in sorted_classes:
        if not isinstance(details, dict):
            continue
        columns = details.get("columns", [])
        if not columns:
            continue
        lines.append(f"Class: {details.get('term', details.get('name', '?'))}")
        for col in sorted(columns, key=lambda value: str(value.get("name", "")) if isinstance(value, dict) else str(value)):
            if isinstance(col, dict):
                lines.append(f"  - {col.get('name', '?')} ({col.get('datatype', 'unknown')})")
            else:
                lines.append(f"  - {col}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 8. GENERATE SPARQL (single attempt, no retry context)
# ---------------------------------------------------------------------------

def generate_sparql(
    query: str,
    schema_text: str,
    schema_namespaces: Dict[str, str],
    client: LLMClient,
    model: str,
) -> Dict[str, Any]:
    prompt = f"""RDF schema:
{schema_text}

Question:
{query}

Return only the SPARQL query. Do not include reasoning, explanations, markdown,
comments, or prose.
"""

    api_logger.log_call(query, "Generate")
    request_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.lower().startswith("gpt-5"):
        request_kwargs["temperature"] = 0.0

    t0 = time.perf_counter()
    response = client.chat.completions.create(**request_kwargs)
    latency = time.perf_counter() - t0
    result = response.choices[0].message.content.strip()
    usage = getattr(response, "usage", None)

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

    return {
        "sparql": repair_sparql_query(sparql_query, schema_namespaces),
        "latency": latency,
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
    }


# ---------------------------------------------------------------------------
# 9. RESULT SERIALIZATION (complete, never truncated — grading happens later)
# ---------------------------------------------------------------------------

def serialize_rows(rows: List[Dict[str, Any]]) -> str:
    return json.dumps(rows, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 10. DATASET LOADING
# ---------------------------------------------------------------------------

def load_input_samples(sample_file: str) -> pd.DataFrame:
    extension = os.path.splitext(sample_file)[1].lower()
    if extension in {".xlsx", ".xls"}:
        return pd.read_excel(sample_file)
    return pd.read_csv(sample_file)


REPORT_COLUMNS = [
    "Pipeline Version",
    "Sample Row ID",
    "Question",
    "Ground Truth",
    "Difficulty",
    "Category",
    "Query Type",
    "Source CSV",
    "New Status",
    "Generated SPARQL",
    "Scan Status",
    "Scan Row Count",
    "Scan Error",
    "Scan Raw Rows",
    "Target Model",
    "Generation Input Tokens",
    "Generation Output Tokens",
    "Generation Latency Seconds",
    "Execution Latency Seconds",
    "Started At",
    "Elapsed Seconds",
]


def process_question(
    record: Dict[str, Any],
    client: LLMClient,
    schema_text: str,
    schema_namespaces: Dict[str, str],
) -> Dict[str, Any]:
    query_start = time.perf_counter()
    started_at = datetime.datetime.now().isoformat(timespec="seconds")
    query = sanitize_user_query(str(record.get("Question", "")))
    ground_truth = str(record.get("Ground Truth", ""))
    sample_row_id = record.get("Sample Row ID", "")
    row_metadata = {
        "Difficulty": record.get("Difficulty", ""),
        "Category": record.get("Category", ""),
        "Query Type": record.get("Query Type", ""),
        "Source CSV": record.get("Source CSV", ""),
    }

    base_row = {
        "Pipeline Version": PIPELINE_VERSION,
        "Sample Row ID": sample_row_id,
        "Question": query,
        "Ground Truth": ground_truth,
        **row_metadata,
        "Target Model": TARGET_MODEL,
        "Started At": started_at,
    }

    try:
        gen = generate_sparql(
            query=query,
            schema_text=schema_text,
            schema_namespaces=schema_namespaces,
            client=client,
            model=TARGET_MODEL,
        )
    except Exception as gen_err:
        if is_quota_exhaustion_error(gen_err):
            return {**base_row, "New Status": "QUOTA_EXHAUSTED", "Scan Error": str(gen_err),
                    "Generated SPARQL": "", "Scan Status": "GENERATE_ERROR", "Scan Row Count": "",
                    "Scan Raw Rows": "", "Generation Input Tokens": 0, "Generation Output Tokens": 0,
                    "Generation Latency Seconds": "", "Execution Latency Seconds": "",
                    "Elapsed Seconds": round(time.perf_counter() - query_start, 3)}
        return {**base_row, "New Status": "GENERATE_ERROR", "Scan Error": str(gen_err),
                "Generated SPARQL": "", "Scan Status": "GENERATE_ERROR", "Scan Row Count": "",
                "Scan Raw Rows": "", "Generation Input Tokens": 0, "Generation Output Tokens": 0,
                "Generation Latency Seconds": "", "Execution Latency Seconds": "",
                "Elapsed Seconds": round(time.perf_counter() - query_start, 3)}

    sparql = gen["sparql"]
    if not sparql.strip():
        return {**base_row, "New Status": "EMPTY_SPARQL", "Scan Error": "LLM returned empty SPARQL.",
                "Generated SPARQL": "", "Scan Status": "EMPTY_SPARQL", "Scan Row Count": "",
                "Scan Raw Rows": "", "Generation Input Tokens": gen["input_tokens"],
                "Generation Output Tokens": gen["output_tokens"],
                "Generation Latency Seconds": round(gen["latency"], 3), "Execution Latency Seconds": "",
                "Elapsed Seconds": round(time.perf_counter() - query_start, 3)}

    exec_t0 = time.perf_counter()
    scan_result = execute_sparql_on_fuseki(sparql, FUSEKI_ENDPOINT, FUSEKI_SCAN_TIMEOUT_SECONDS)
    exec_latency = time.perf_counter() - exec_t0
    scan_status = scan_result.get("status", "error")

    if scan_status != "success":
        return {**base_row, "New Status": "EXEC_ERROR", "Scan Error": scan_result.get("error_message", ""),
                "Generated SPARQL": sparql, "Scan Status": "EXEC_ERROR", "Scan Row Count": "",
                "Scan Raw Rows": "", "Generation Input Tokens": gen["input_tokens"],
                "Generation Output Tokens": gen["output_tokens"],
                "Generation Latency Seconds": round(gen["latency"], 3),
                "Execution Latency Seconds": round(exec_latency, 3),
                "Elapsed Seconds": round(time.perf_counter() - query_start, 3)}

    return {
        **base_row,
        "New Status": "OK",
        "Generated SPARQL": sparql,
        "Scan Status": "success",
        "Scan Row Count": scan_result.get("row_count", 0),
        "Scan Error": "",
        "Scan Raw Rows": serialize_rows(scan_result.get("data", [])),
        "Generation Input Tokens": gen["input_tokens"],
        "Generation Output Tokens": gen["output_tokens"],
        "Generation Latency Seconds": round(gen["latency"], 3),
        "Execution Latency Seconds": round(exec_latency, 3),
        "Elapsed Seconds": round(time.perf_counter() - query_start, 3),
    }


def main():
    print("\n" + "=" * 60)
    print("  BASE PIPELINE — SPARQL (GPT-OSS 120B, single-shot, ungraded)")
    print("=" * 60)
    print(f"[CONFIG] Target model: {TARGET_MODEL}")
    print(f"[CONFIG] Workers (concurrent questions): {PIPELINE_WORKERS}")
    print(f"[CONFIG] Pipeline version: {PIPELINE_VERSION}")
    print(f"[CONFIG] Fuseki endpoint: {FUSEKI_ENDPOINT}")
    print(f"[CONFIG] Query window: offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT or 'all'}")
    print(f"[CONFIG] Report file: {REPORT_FILE}")
    script_start_time = time.perf_counter()

    print("\n[SYSTEM] Checking Fuseki connectivity...")
    check_fuseki_health(FUSEKI_ENDPOINT)

    print("[SYSTEM] Building target client...")
    target_client = build_target_client(TARGET_MODEL)

    print(f"\n[STEP 1] Loading schema from {SCHEMA_FILE}...")
    kg_metadata, schema_namespaces = load_rdf_knowledge_graph(SCHEMA_FILE)
    schema_text = build_schema_text(kg_metadata, schema_namespaces)

    print(f"\n[STEP 1] Loading dataset from {INPUT_SAMPLE_FILE}...")
    df_all = load_input_samples(INPUT_SAMPLE_FILE)
    if not {"question", "ground_truth_answer"}.issubset(df_all.columns):
        print(f"[ERROR] Dataset must have 'question' and 'ground_truth_answer' columns. Found: {list(df_all.columns)}")
        return

    records = pd.DataFrame({
        "Sample Row ID": df_all.get("global_question_id", pd.Series(range(1, len(df_all) + 1))).astype(str),
        "Question": df_all["question"].astype(str),
        "Ground Truth": df_all["ground_truth_answer"].astype(str),
        "Difficulty": df_all.get("difficulty", pd.Series([""] * len(df_all))).astype(str),
        "Category": df_all.get("category", pd.Series([""] * len(df_all))).astype(str),
        "Query Type": df_all.get("query_type", pd.Series([""] * len(df_all))).astype(str),
        "Source CSV": df_all.get("source_csv", pd.Series([""] * len(df_all))).astype(str),
    })

    limit = TEST_QUERY_LIMIT if TEST_QUERY_LIMIT > 0 else len(records)
    test_records = records.iloc[TEST_QUERY_OFFSET: TEST_QUERY_OFFSET + limit].to_dict(orient="records")
    print(f"[STEP 1] Loaded {len(test_records)} queries for evaluation.")

    results_list: list = []
    completed_row_ids: set = set()
    if os.path.exists(REPORT_FILE):
        try:
            existing = pd.read_csv(REPORT_FILE)
            if "Sample Row ID" in existing.columns:
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

    results_lock = threading.Lock()

    def save_report():
        df_report = pd.DataFrame(results_list)
        for col in REPORT_COLUMNS:
            if col not in df_report.columns:
                df_report[col] = ""
        df_report = df_report[REPORT_COLUMNS]
        tmp_file = f"{REPORT_FILE}.tmp"
        df_report.to_csv(tmp_file, index=False)
        os.replace(tmp_file, REPORT_FILE)

    completed_count = 0
    total_pending = len(pending_records)
    quota_exhausted = threading.Event()

    def worker(record):
        if quota_exhausted.is_set():
            return None
        return process_question(record, target_client, schema_text, schema_namespaces)

    with ThreadPoolExecutor(max_workers=PIPELINE_WORKERS) as pool:
        futures = {pool.submit(worker, r): r for r in pending_records}
        for future in as_completed(futures):
            row = future.result()
            if row is None:
                continue
            with results_lock:
                results_list.append(row)
                completed_count += 1
                save_report()
                if completed_count % 10 == 0:
                    api_logger.save()
            status = row["New Status"]
            print(f"  [{completed_count}/{total_pending}] {row['Sample Row ID']}: {status} "
                  f"({row.get('Elapsed Seconds', '')}s)", flush=True)
            if status == "QUOTA_EXHAUSTED":
                print("[SYSTEM] Quota exhausted signal seen; not scheduling further new work.")
                quota_exhausted.set()

    api_logger.save()
    wall_clock = time.perf_counter() - script_start_time

    ok_count = sum(1 for r in results_list if str(r.get("New Status", "")).upper() == "OK")
    err_count = len(results_list) - ok_count

    print(f"\n{'=' * 60}")
    print("  PIPELINE RUN COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Report:       {REPORT_FILE}")
    print(f"  Total rows:   {len(results_list)}")
    print(f"  OK:           {ok_count}")
    print(f"  ERROR/OTHER:  {err_count}")
    print(f"  Wall clock:   {wall_clock:.1f}s ({wall_clock / 60:.1f}min)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
