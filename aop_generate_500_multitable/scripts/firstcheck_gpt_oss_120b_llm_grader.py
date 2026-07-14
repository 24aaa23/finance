import unicodedata
import re
import json
import difflib
import networkx as nx
from typing import Dict, Any
from openai import OpenAI as LLMClient
import pandas as pd
import os
import rdflib
import concurrent.futures
import time
import threading
import datetime
import random
import multiprocessing
import queue


def load_local_env_file() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_candidates = [
        os.path.join(script_dir, ".env"),
        os.path.join(os.path.dirname(script_dir), ".env"),
        os.path.join("/DATAAMAN/financial/aop_general_300_mismatch", ".env"),
    ]
    env_file = next((path for path in env_candidates if os.path.exists(path)), None)
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

os.environ.setdefault("QUERY_SHUFFLE_SEED", "4043113952")

DEFAULT_LLM_MODEL = "openai.gpt-oss-120b-1:0"
GPT_OSS_MODEL = os.getenv("BEDROCK_GPT_OSS_MODEL", DEFAULT_LLM_MODEL)
LOCAL_MODEL = GPT_OSS_MODEL
PLANNER_MODEL = GPT_OSS_MODEL
REFINE_MODEL = GPT_OSS_MODEL
VALIDATE_MODEL = GPT_OSS_MODEL
EXPLAIN_MODEL = GPT_OSS_MODEL
SPARQL_GENERATION_MODEL = GPT_OSS_MODEL
PIPELINE_VERSION = os.getenv("GPT_OSS_LLM_GRADER_PIPELINE_VERSION", "aop-general-gpt-oss-120b-llm-grader-v1")
# Full GPT-OSS retest defaults: running this file directly processes the 300-query window.
TEST_QUERY_LIMIT = int(os.getenv("TEST_QUERY_LIMIT", "300"))
TEST_QUERY_OFFSET = int(os.getenv("TEST_QUERY_OFFSET", "0"))
TEST_MAX_WORKERS = int(os.getenv("TEST_MAX_WORKERS", "1"))
SPARQL_SCAN_TIMEOUT_SECONDS = max(0.0, float(os.getenv("SPARQL_SCAN_TIMEOUT_SECONDS", "60")))
SPARQL_SCAN_MAX_RETRIES = max(1, int(os.getenv("SPARQL_SCAN_MAX_RETRIES", "3")))
SPARQL_SCAN_PROCESS_START_METHOD = os.getenv("SPARQL_SCAN_PROCESS_START_METHOD", "spawn")
BASE_DIR = r"C:\Users\AMAN KUMAR SINGH\Desktop\financial"
EXPERIMENT_DIR = os.path.join(BASE_DIR, "aop_generate_500_multitable")
OUTPUT_DIR = os.path.join(EXPERIMENT_DIR, "pipeline_output")
SCHEMA_FILE = os.path.join(BASE_DIR, "kg_output_fixed", "wealth_management_diverse_schema.ttl")
INSTANCE_FILE = os.path.join(BASE_DIR, "kg_output_fixed", "wealth_management_diverse_kg.ttl")
INPUT_SAMPLE_FILE = os.path.join(BASE_DIR, "dataset_new", "wealth_management_all_benchmark_questions_combined_shuffled_seed4043113952.csv")
# Default output for the full 300-query GPT-OSS run with LLM-only final grading.
REPORT_FILE = os.getenv("GPT_OSS_LLM_GRADER_REPORT_FILE", os.path.join(OUTPUT_DIR, "Pipeline_Retest_Report_gpt_oss_120b_llm_grader_newkg_300.csv"))
ALIAS_MAP_FILE = os.getenv("RDF_ALIAS_MAP_FILE", os.path.join(EXPERIMENT_DIR, "rdf_id_alias_map.json"))
RDF_ID_ALIAS_MAP = {}



def build_bedrock_gpt_oss_client():
    """Build the Bedrock OpenAI-compatible client used by every LLM role."""
    api_key = (
        os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not api_key:
        raise RuntimeError(
            "AWS_BEDROCK_API_KEY is required for the GPT-OSS 120B Bedrock pipeline."
        )

    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError(
                "BEDROCK_REGION is required for the GPT-OSS 120B Bedrock endpoint "
                "(for example: BEDROCK_REGION=us-east-1)."
            )
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"

    return LLMClient(api_key=api_key, base_url=base_url)


def build_llm_client():
    return build_bedrock_gpt_oss_client()


def build_openai_sparql_client():
    return build_bedrock_gpt_oss_client()


def build_openai_planner_client():
    return build_bedrock_gpt_oss_client()


os.makedirs(OUTPUT_DIR, exist_ok=True)

class APILogger:
    def __init__(self):
        self.lock = threading.Lock()
        self.query_logs = {}
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Save directly to the new organized folder
        self.log_file = os.path.join(OUTPUT_DIR, f"api_usage_log_{timestamp}.json")

    def log_call(self, query, function_name):
        with self.lock:
            q_key = query if query else "Unknown_Query"
            if q_key not in self.query_logs:
                self.query_logs[q_key] = {"total_calls": 0, "functions": {}}

            self.query_logs[q_key]["total_calls"] += 1
            self.query_logs[q_key]["functions"][function_name] = self.query_logs[q_key]["functions"].get(function_name, 0) + 1

    def save(self):
        with self.lock:
            with open(self.log_file, "w") as f:
                json.dump(self.query_logs, f, indent=4)

api_logger = APILogger()





def load_rdf_knowledge_graph(schema_file: str, instance_file: str) -> Dict[str, Any]:
    """
    Loads RDF files and extracts a dictionary of classes and their dynamic properties.
    Basically, provides the schema of metadata and allows the LLM to understand the graph data structure

    Args:
        schema_file (str): Path to the RDF schema/linkage file.
        instance_file (str): Path to the Turtle (.ttl) instance data file.

    Returns:
        Dict[str, Any]: A dictionary mapping class names to their properties and descriptions.
    """

    #Parsing the files
    print("[SYSTEM] Loading RDF Knowledge Graph...")
    g = rdflib.Graph()
    g.parse(schema_file, format="turtle")
    g.parse(instance_file, format="turtle")

    WM = rdflib.Namespace("http://www.semanticweb.org/openai/ontologies/2026/4/wealth-management/v3#")

    kg_metadata = {}

    #Find all Classes in the schema
    for s, p, o in g.triples((None, rdflib.RDF.type, rdflib.OWL.Class)):
        class_name = local_name(s)

        #Exclude internal/hidden classes containing double underscores
        if "__" not in class_name:
            label = str(g.value(s, rdflib.RDFS.label)) if g.value(s, rdflib.RDFS.label) else class_name
            kg_metadata[class_name] = {
                "name": label,
                "description": "",
                "columns": set(),
                "property_datatypes": {} # ADDED: Tracks if fields are numeric vs string (Fix E-05)
            }

    #Extract properties directly from the INSTANCES!
    for s, p, o in g:
        # Ignore standard w3 metadata properties immediately to save time
        if "www.w3.org" in str(p):
            continue

        # O(1) direct lookup for the subject's type
        for s_type in g.objects(subject=s, predicate=rdflib.RDF.type):
            class_name = local_name(s_type)

            if class_name in kg_metadata:
                prop_name = local_name(p)
                kg_metadata[class_name]["columns"].add(prop_name)

                # --- DATATYPE & EDGE EXTRACTION ---
                if isinstance(o, rdflib.Literal):
                    # Check if the literal is a number
                    if o.datatype and ("decimal" in str(o.datatype).lower() or "integer" in str(o.datatype).lower() or "float" in str(o.datatype).lower()):
                        kg_metadata[class_name]["property_datatypes"][prop_name] = "numeric"
                    else:
                        kg_metadata[class_name]["property_datatypes"][prop_name] = "categorical_string"

                elif isinstance(o, rdflib.URIRef):
                    # --- NEW GRAPH TRAVERSAL FIX ---
                    # Instead of just saying "object_reference", tell the LLM exactly which Class this links to!
                    target_classes = list(g.objects(subject=o, predicate=rdflib.RDF.type))
                    if target_classes:
                        target_class_name = local_name(target_classes[0])
                        kg_metadata[class_name]["property_datatypes"][prop_name] = f"object_reference (points to: {target_class_name})"
                    else:
                        kg_metadata[class_name]["property_datatypes"][prop_name] = "object_reference"
                    # ---------------------------------------------

    #Convert sets back to structured lists for the JSON output
    for class_name in kg_metadata:

        # --- ADDED: TAXONOMY LABELS WARNING (FIX E-04) ---
        taxonomy_classes = ["InvestmentType", "Sector", "RiskToleranceContext", "InvestmentRiskCategory", "AssetClass"]
        if class_name in taxonomy_classes:
            kg_metadata[class_name]["CRITICAL_label_property"] = "rdfs:label (or domain-specific name property like wm:investmentTypeName)"
            kg_metadata[class_name]["usage_note"] = "Always SELECT ?label via this property. NEVER return the raw node IRI."
        # -------------------------------------------------

        # Format columns list to include the extracted datatypes
        formatted_columns = []
        for prop in kg_metadata[class_name]["columns"]:
            dtype = kg_metadata[class_name]["property_datatypes"].get(prop, "unknown")
            formatted_columns.append({"name": prop, "type": "Property", "datatype": dtype})

        kg_metadata[class_name]["columns"] = formatted_columns

    print(f"[SYSTEM] Successfully loaded {len(kg_metadata)} classes with dynamic properties.")
    return kg_metadata

def get_lightweight_table_index(kg_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Passes class names and their columns so Retrieve knows exactly where data lives."""
    index = {}
    for table, data in kg_metadata.items():
        # Extract just the column names so the LLM can search them
        index[table] = [col["name"] for col in data.get("columns", [])]
    return index


def add_cardinality_hints(kg_metadata: Dict[str, Any], rdf_graph: rdflib.Graph) -> Dict[str, Any]:
    """
    Infer generic join-risk hints from the data itself.
    No class or property names are hardcoded: repeated literal values indicate a
    property can create many-to-many expansion when used as a join key.
    """
    class_uri_by_name = {}
    for _, _, type_uri in rdf_graph.triples((None, rdflib.RDF.type, None)):
        class_uri_by_name.setdefault(local_name(type_uri), type_uri)

    for class_name, meta in kg_metadata.items():
        class_uri = class_uri_by_name.get(class_name)
        if class_uri is None:
            continue

        subjects = set(rdf_graph.subjects(rdflib.RDF.type, class_uri))
        subject_count = len(subjects)
        if not subject_count:
            continue

        cardinality_hints = {}
        for prop in meta.get("columns", []):
            prop_name = prop.get("name")
            if not prop_name:
                continue

            matching_predicates = {
                predicate
                for subject in subjects
                for predicate, obj in rdf_graph.predicate_objects(subject)
                if local_name(predicate) == prop_name and isinstance(obj, rdflib.Literal)
            }
            if not matching_predicates:
                continue

            value_to_subjects = {}
            subjects_with_value = set()
            for subject in subjects:
                for predicate in matching_predicates:
                    for value in rdf_graph.objects(subject, predicate):
                        if isinstance(value, rdflib.Literal):
                            value_text = str(value)
                            value_to_subjects.setdefault(value_text, set()).add(str(subject))
                            subjects_with_value.add(str(subject))

            if not value_to_subjects:
                continue

            subjects_per_value = [len(value_subjects) for value_subjects in value_to_subjects.values()]
            max_subjects_per_value = max(subjects_per_value)
            avg_subjects_per_value = sum(subjects_per_value) / len(subjects_per_value)
            coverage = len(subjects_with_value) / subject_count
            distinct_ratio = len(value_to_subjects) / max(len(subjects_with_value), 1)
            join_cardinality = "many_per_value" if max_subjects_per_value > 1 else "unique_per_value"

            cardinality_hints[prop_name] = {
                "subject_count": subject_count,
                "subjects_with_value": len(subjects_with_value),
                "distinct_values": len(value_to_subjects),
                "coverage": round(coverage, 3),
                "distinct_ratio": round(distinct_ratio, 3),
                "max_subjects_per_value": max_subjects_per_value,
                "avg_subjects_per_value": round(avg_subjects_per_value, 3),
                "join_cardinality": join_cardinality,
                "join_warning": (
                    "A flat join through this literal property can expand rows if the other "
                    "class also has many_per_value behavior for the same value domain. Prefer "
                    "direct object predicates or pre-aggregate before joining."
                    if join_cardinality == "many_per_value"
                    else "This literal property is unique per value within this class."
                ),
            }

        if cardinality_hints:
            meta["cardinality_hints"] = cardinality_hints

    return kg_metadata


def setup_rdf_graph(instance_file: str) -> rdflib.Graph:
    """Loads the RDF instance data into an executable graph database."""
    print("[SYSTEM] Loading RDF Instance Graph for SPARQL queries...")
    g = rdflib.Graph()
    g.parse(instance_file, format="turtle") #or "xml" depending on the file. Change it accordingly
    global RDF_ID_ALIAS_MAP
    RDF_ID_ALIAS_MAP = load_rdf_id_alias_map(ALIAS_MAP_FILE)
    if RDF_ID_ALIAS_MAP:
        print(f"[SYSTEM] Loaded RDF ID alias map with {len(RDF_ID_ALIAS_MAP)} normalized keys.")
    else:
        print(f"[WARN] RDF ID alias map not found or empty: {ALIAS_MAP_FILE}")
    return g






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


# SEMANTIC OPERATORS

#General structure of semantic operators :
#Input consists of queries and the  Knowledge Graph schema metadata (ontology classes and dynamic properties)
#and  structured as Python dictionaries.
#For PROCESSING: The operators use highly structured natural language prompts
# to direct an LLM (the Agent) to perform specific reasoning tasks
#(e.g., ontology retrieval, SPARQL generation, logical validation).
#After performing the specified task through LLM, the output is generally produced in a json format and subsequently stored in the form of dictionaries so that it can be used as input to the next operator


# The retrieve operation takes in the query and the schemas of tables and finds the relevant tables for further processing

def semantic_retrieve(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Retrieve
    Purpose: Analyzes the user query against a lightweight index of the Knowledge Graph
             to identify the relevant ontology classes needed for the query.
    Inputs: 'query', 'table_index'
    Outputs: 'retrieved_tables' (List of class names)

    The reason for using lightweight index is to reduce the number of tokens sent to the LLM.

    """

    table_index = inputs.get('table_index', {})
    prompt = f"""
You are the Retrieve operator. Select relevant ontology class names for the user query.

User Query: {inputs.get('query')}
Available Classes (Index): {json.dumps(table_index, indent=2)}

Return ONLY a JSON array of exact class names from Available Classes.
Do not write Python code.
Do not explain.
Example output: ["InvestorProfile", "PortfolioHolding"]
"""

    api_logger.log_call(inputs.get('query'), "Retrieve")
    # The response is collected for the above prompts and input
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    #the result is stored after cleaning the response from the LLM and in the form of json object
    result = response.choices[0].message.content
    retrieved_tables = parse_llm_json(result, [], "Retrieve")
    if not isinstance(retrieved_tables, list):
        retrieved_tables = []
    retrieved_tables = [table for table in retrieved_tables if table in table_index]
    if not retrieved_tables:
        print("[WARN] Retrieve returned no valid classes; Generate will use the full dynamic schema.")
    return {"retrieved_tables": retrieved_tables}



def semantic_generate_sparql(inputs: Dict[str, Any], client: Any, model: str) -> Dict[str, Any]:
    """
    Operator: Generate
    Purpose: Dynamically writes an executable SPARQL query based on the specific
             classes retrieved and the strict rules of the target ontology. The rules are specified
             by us and can be changed as per our needs. In case the KG is modified, these need to be changed as well

    Inputs: 'query', 'retrieved_tables', 'global_schema'
    Outputs: 'sparql' (Executable query string)
    """

    #the data from KG
    retrieved_classes = inputs.get('retrieved_tables', [])
    global_schema = inputs.get('global_schema', {})

    print(f"\n[DEBUG] Retrieve passed these classes: {retrieved_classes}")

    pruned_schema = {cls: global_schema[cls] for cls in retrieved_classes if cls in global_schema}
    if not pruned_schema:
        print("[DEBUG] Target Classes empty/invalid. Passing full dynamic schema to Generate.")
        pruned_schema = global_schema
    schema_generation_rules = build_schema_generation_rules(pruned_schema)

    # || Adding these feedback and failed query to correct regeneration
    logic_feedback = inputs.get('logic_feedback', '')
    failed_sparql = inputs.get('sparql', '')
    retry_context = ""
    if logic_feedback and failed_sparql:
        retry_context = f"""
        WARNING: You are in a self-healing retry loop. Your previous SPARQL query failed.
        Previous Failed SPARQL: {failed_sparql}
        Error Report & Actual Database Properties (JSON): {logic_feedback}
        You MUST rewrite the query differently. Read the JSON report above carefully. You must specifically use the exact properties listed in the 'actual_properties_on_node' field and follow the instructions in the 'hint' field. Do not guess or hallucinate property names.
        """
    # || Updated the prompt with feedback and failed query
    prompt = f"""
You are the Generate operator. Write one executable SPARQL query for the RDF graph.

User Query: "{inputs.get('query')}"
Target Classes: {retrieved_classes}
Schema Details: {json.dumps(pruned_schema, indent=2)}
Dynamic Schema Rules:
{schema_generation_rules}
{retry_context}

Return ONLY raw SPARQL text. Do not explain. Do not include <reasoning>, <think>, markdown, comments, or prose.
The first non-whitespace characters in your response must be PREFIX or SELECT.
Do not invent example people such as John Doe.

RDF VOCABULARY RULES:
- Use only classes, predicates, and resources that appear in Schema Details or the RDF graph.
- Do NOT use schema-linkage attribute names as rdf:type classes unless they are real RDF classes.
- Do NOT invent object properties for joins. Prefer listed relationship predicates/direct object references over shared literal-value joins.
- Do NOT use schema1: properties in executable graph patterns. Use wm: properties.
- Never invent repeated properties such as `wm:nameLiteralLiteral`.
- If the user mentions a resource ID with punctuation, normalize cautiously but still use only identifiers visible in the graph.

JOIN SAFETY RULES:
- Use cardinality_hints from Schema Details when joining classes through literal properties.
- Do not create a flat join between two classes through a literal property when both sides show many_per_value behavior for the joined values.
- A many_per_value to many_per_value flat join can multiply rows, distort SUM/AVG results, and time out.
- If such a join is truly needed, first aggregate each class separately in subqueries, then join the smaller grouped results.
- If no direct relationship or safe cardinality exists, answer from the most relevant class instead of forcing a join.
- Timeout feedback means the query plan is too large; rewrite the graph pattern structurally, not cosmetically.

CRITICAL RULE 1 (PREFIXES): You MUST include these exact prefixes:
    PREFIX wm: <https://wealth.example.org/ontology/>
    PREFIX kg: <https://wealth.example.org/kg/>
    PREFIX wmmeta: <https://wealth.example.org/metadata/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX schema1: <http://schema.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

CRITICAL RULE 2 (MATH & AGGREGATION): RDF stores values as strings. For aggregations (SUM, AVG) or math, MUST cast variables to decimal: e.g., SUM(xsd:decimal(?value)).
Never put aggregate functions like SUM, AVG, COUNT, MIN, or MAX inside BIND or OPTIONAL blocks. Put aggregate expressions in SELECT, for example `(SUM(xsd:decimal(?amount)) AS ?totalAmount)`, and use GROUP BY for non-aggregated selected variables.

CRITICAL RULE 3 (CASE-INSENSITIVE FILTERS): When filtering by text or IDs, you MUST use lowercase comparison.
Example: `FILTER(CONTAINS(LCASE(STR(?id)), "inv-001"))`.

CRITICAL RULE 4 (NEGATION): If the user query contains words like "never", "not", "excluding", "without", or "no X", you MUST use `FILTER NOT EXISTS {{ }}` or `MINUS {{ }}` to ensure those records are excluded.

CRITICAL RULE 5 (LABELS OVER IRIs): For any controlled-vocabulary class (InvestmentType, Sector, Segment, RiskCategory), always follow the label property to get the human-readable string.


"""

    api_logger.log_call(inputs.get('query'), "Generate")
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    result = response.choices[0].message.content.strip()

    # UI-SAFE SPARQL EXTRACTOR
    #since the sparql query generated is sometimes in the form of markdown, in order to maintain uniformity
    # we extract only the useful part in a fixed format
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

    return {"sparql": repair_sparql_for_query(sparql_query, inputs.get("query", ""))}


# Sometimes, the LLM might commit errors in generating the SPARQL query (wrong column/operation name, etc.)
# Upon getting an error, this operator analyses the error and the wrong query and generates the corrected version
def semantic_refine(inputs: Dict[str, Any], client: Any, model: str) -> Dict[str, Any]:
    """
    Operator: Refine
    Purpose: Acts as the self-reflection and self-healing mechanism to fix broken
             SPARQL queries based on database execution errors.
    Inputs: 'failed_sparql', 'error_message', 'schema_details', 'logic_feedback'
    Outputs: 'sparql' (Corrected query string)
    """
    schema_details = inputs.get('schema_details') or inputs.get('global_schema', {})
    prompt = f"""
    The next operator is Refine.
    Analyze the SPARQL error and provide a corrected raw SPARQL query.

    User Query: {inputs.get('query')}
    Failed SPARQL: {inputs.get('failed_sparql')}
    Database Error: {inputs.get('error_message')}
    Logic Feedback: {inputs.get('logic_feedback', 'None')}
    Schema Details: {json.dumps(schema_details, indent=2)}

    CRITICAL RULE 1: Include these exact prefixes:
    PREFIX wm: <https://wealth.example.org/ontology/>
    PREFIX kg: <https://wealth.example.org/kg/>
    PREFIX wmmeta: <https://wealth.example.org/metadata/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX schema1: <http://schema.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    CRITICAL RULE 2: If the error involves aggregation/math, remember you MUST cast strings to numbers: e.g., SUM(xsd:decimal(?value)) and ensure there is a GROUP BY. Never put aggregate functions like SUM, AVG, COUNT, MIN, or MAX inside BIND or OPTIONAL blocks; aggregate in SELECT instead.

    CRITICAL RULE 3: Use only classes, predicates, and resources visible in Schema Details or explicitly listed in Logic Feedback. Do not invent replacement names.

    CRITICAL RULE 4: If Logic Feedback contains unknown_terms and suggestions, replace invalid terms with the closest valid schema term only when it fits the user's question. Otherwise rewrite the graph pattern using valid schema relationships.

    JOIN SAFETY RULES:
    - Use cardinality_hints from Schema Details when joining classes through literal properties.
    - Do not create a flat join between two classes through a literal property when both sides show many_per_value behavior for the joined values.
    - A many_per_value to many_per_value flat join can multiply rows, distort SUM/AVG results, and time out.
    - If such a join is truly needed, first aggregate each class separately in subqueries, then join the smaller grouped results.
    - If no direct relationship or safe cardinality exists, answer from the most relevant class instead of forcing a join.
    - Timeout feedback means the query plan is too large; rewrite the graph pattern structurally, not cosmetically.

    Output strictly the corrected raw SPARQL text without explanations, reasoning tags, prose, comments, or markdown formatting.
    The first non-whitespace characters in your response must be PREFIX or SELECT.
    """

    api_logger.log_call(inputs.get('query'), "Refine")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    result = response.choices[0].message.content.strip()

    #UI-SAFE SPARQL EXTRACTOR
    ##since the output is sometimes in the form of markdown, in order to maintain uniformity
    # we extract only the useful part in a fixed format
    if "```" in result:
        parts = result.split("```")
        if len(parts) >= 3:
            code_block = parts[1]
            if code_block.lower().startswith("sparql"):
                code_block = code_block[6:]
            sparql = code_block.strip()
        else:
            sparql = result.replace("```sparql", "").replace("```SPARQL", "").replace("```", "").strip()
    else:
        sparql = result.strip()

    return {"sparql": repair_sparql_for_query(sparql, inputs.get("query", ""))}

# After the data is retrieved, the natural language query and the final output is given as input to the LLM agent , which checks for the Semantic Alignment. It checks for missing or wrong columns names, ignored constrained,etc.
# Gives boolean output
#Can be improved further after providing a set of basic laws to the LLM for validation

#|| Cahnged vaidation so that it not only checks for ewmptiness, but also the column names, cluases, etc.
def semantic_validate(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    print(f"\n[DEBUG] --- Executing semantic_validate ---")
    data = inputs.get('data', [])
    print(f"[DEBUG] Validating {len(data)} rows for query.")
    if not data:
        val_dict = {"is_valid": False, "reason": "Data Results are empty. Query failed to retrieve necessary facts."}
        print(f"[DEBUG] Output Validation Result: {val_dict}")
        return {"validation": val_dict, "data": data}

    # Extract the column names (keys) from the first row of data to help the LLM verify fields
    returned_fields = list(data[0].keys()) if data and isinstance(data, list) else []

    # Cap the data sample at 10 rows to prevent blowing up the LLM context window during validation
    data_sample = data[:10] if isinstance(data, list) else data
    generated_sparql = inputs.get("sparql", "")

    prompt = f"""
    The next operator is Validate.
    Assess if the following data results successfully answer the user's original query.
    Use the generated SPARQL as part of the evidence. Do not judge only by row count.

    User Query: "{inputs.get('query')}"
    Generated SPARQL:
    {generated_sparql}
    Returned Column Names: {returned_fields}
    Data Results (Sample): {json.dumps(data_sample, indent=2)}

    CRITICAL RULE 1 (EMPTY DATA): If the Data Results are empty (e.g., [] or None), you MUST output "is_valid": false. Empty data means the query failed to retrieve the necessary facts.

    CRITICAL RULE 2 (SCHEMA & FIELD MATCH - FIX E-02): Beyond checking if data is non-empty, you MUST verify:
    1. Do the returned column names logically match what the query asked for? (e.g., if asking for "sector and allocation", both fields MUST be present).
    2. If the query asked for a specific investor/entity filter, does the data reflect only that entity? Or did it return data for everyone?
    3. If the query asked for an aggregation (MAX/MIN/SUM/AVG/COUNT), did the SPARQL and returned fields reflect the requested aggregate, or did it return raw unaggregated rows?
    4. If the query asks for a top/bottom, highest/lowest, maximum/minimum, largest/smallest, best/worst, or ranking-style result, inspect the SPARQL ranking logic.

    CRITICAL RULE 3 (RANKED AGGREGATION): For superlative or ranking questions, a single returned row can be fully valid when the SPARQL intentionally reduces the result:
    - GROUP BY plus an aggregate expression plus ORDER BY plus LIMIT 1 is a valid way to return one top or bottom group.
    - ORDER BY ASC with LIMIT 1 supports lowest/minimum/smallest/bottom questions.
    - ORDER BY DESC with LIMIT 1 supports highest/maximum/largest/top questions.
    - Do NOT require all groups to be returned when ORDER BY and LIMIT already select the final ranked answer.

    If ANY of these logic checks fail, you MUST output "is_valid": false and provide specific, detailed feedback in the "reason" field about which columns/aggregations are wrong.

    Output strictly a JSON object: {{"is_valid": true/false, "reason": "why"}}
    """

    api_logger.log_call(inputs.get('query'), "Validate")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )

    result = response.choices[0].message.content
    val_dict = parse_llm_json(
        result,
        {
            "is_valid": bool(data),
            "reason": "Validator did not return valid JSON; using row-presence fallback.",
        },
        "Validate",
    )
    if not isinstance(val_dict, dict):
        val_dict = {
            "is_valid": bool(data),
            "reason": "Validator returned a non-object response; using row-presence fallback.",
        }

    print(f"[DEBUG] Output Validation Result: {val_dict}")
    return {"validation": val_dict, "data": data}

# Format the output generated into human readable form, since we require a variety of formatting based on datasets, we use LLM agent here.
def semantic_explain_results(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Explain
    Purpose: Takes raw data output and translates it into a polished, human-readable
             financial advisory summary.
    Inputs: 'query', 'data'
    Outputs: 'final_answer' (String)
    """

    # --- FIX: Instant Bypass for Short-Circuits ---
    if "context" in inputs and not inputs.get("data"):
        return {"final_answer": inputs.get("context")}
    # ----------------------------------------------
    raw_data = inputs.get('data', [])

    prompt = f"""
    The next operator is Explain.
    Translate the raw data results into a direct, concise answer to the user's original query.
    Use only the facts present in Raw Data Results. Do not add caveats such as "discrepancy",
    "not enough information", or "unable to determine" when rows are present. Preserve all
    returned categories, IDs, names, counts, and numeric values.

    Original Query: "{inputs.get('query')}"
    Raw Data Results: {json.dumps(raw_data)}

    If Raw Data Results contains one or more rows, you MUST answer from those rows.
    Only say no data was found when Raw Data Results is exactly empty.

    Answer style rules:
    - Return ONLY the final answer. Do not include reasoning, analysis, hidden thoughts, XML tags, <reasoning>, <think>, markdown, or code fences.
    - Keep the answer short, usually one sentence for one-row results.
    - Do not use bold text, bullets, or long explanations unless multiple rows must be listed.
    - Preserve exact labels, IDs, and numeric strings from Raw Data Results. Do not add commas to numbers and do not reformat IDs.
    - Include all returned rows and all important returned values needed to answer the query.

    Output the final natural language response directly. No JSON formatting.
    """

    api_logger.log_call(inputs.get('query'), "Explain")
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
    )
    answer = strip_llm_reasoning_blocks(response.choices[0].message.content).strip()
    answer = re.sub(r"(?is)<(?:reasoning|think)>.*", "", answer).strip()
    no_data_phrases = [
        "no data", "no results", "not available", "unable to determine",
        "not determinable", "unknown", "nothing was found"
    ]
    if raw_data and any(phrase in answer.lower() for phrase in no_data_phrases):
        answer = f"Result from retrieved rows: {json.dumps(raw_data, ensure_ascii=False)}"
    return {"final_answer": answer}


# MINOR SEMANTIC OPERATORS (Filters, Classification, Link)

def semantic_link(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Link
    Purpose: Identifies how two or more graph classes should be connected via Object Properties.
    """
    prompt = f"""
    The next operator is Link.
    Identify the relational paths (Object Properties) between the retrieved classes based on their schema.

    Retrieved Classes: {inputs.get('retrieved_tables')}
    Schema Details: {json.dumps(inputs.get('schema_details', {}), indent=2)}

    Output strictly a JSON object detailing the link conditions.
    Example: {{"joins": [{{"class_1": "Investor", "class_2": "Portfolio", "property": "hasPortfolio"}}]}}
    """

    api_logger.log_call(inputs.get('query'), "Link")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    result = response.choices[0].message.content
    return {"join_conditions": parse_llm_json(result, {"joins": []}, "Link")}



# THis operator identifies the context words in the natural language query, for e.g., in the query "What is the average portfolio health for conservative investors?", the filter will contain words such as
# risk_tolerance : conservative and the aggregation will have AVG(portfolio)
# Basically, it extracts the key operative terms from the natural language query, alongwith the specified aggregation functions
# This is a semantic operator and uses LLM instead of being a pre-programmed operator because the natural language query can have synonyms,etc.
def semantic_filter_aggregate(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Filter & Aggregate
    Purpose: Extracts specific WHERE conditions and aggregation functions (AVG, SUM) from the query.
    Expected inputs: 'query', 'schema_details'.
    """
    prompt = f"""
    The next operator is Filter and Aggregate.
    Identify the WHERE clause conditions and aggregations needed for the query.

    Query: {inputs.get('query')}
    Schema: {json.dumps(inputs.get('schema_details', {}), indent=2)}

    Output strictly a JSON object: {{"filters": ["condition 1"], "aggregations": ["aggregation 1"]}}
    """

    api_logger.log_call(inputs.get('query'), "Filter_Aggregate")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    result = response.choices[0].message.content
    return {"logic_components": parse_llm_json(result, {"filters": [], "aggregations": []}, "Filter_Aggregate")}


def semantic_classify_query(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    print(f"\n[DEBUG] --- Executing semantic_classify_query ---")

    # We now pull the schema so the LLM can check datatypes
    schema_details = inputs.get('schema_details', {})

    prompt = f"""
    The next operator is Classify.
    Analyze the user query and classify its primary analytical intent.

    User Query: "{inputs.get('query')}"
    Schema & Datatypes: {json.dumps(schema_details, indent=2)}

    CRITICAL RULE (DATATYPE CHECK):
    If the user is asking for a mathematical calculation (Average, Sum, Min, Max) on a specific field, check the Schema to see whether that exact field is numeric.
    If that exact field is explicitly a 'categorical_string', the requested calculation is mathematically unsupported.
    In that case, you MUST classify the intent strictly as "out_of_domain_unanswerable".
    Never infer the target field from an example or another query. If the field cannot be identified in the schema, use "aggregation_numeric" and schema_datatype "unknown" so later operators can validate it.

    WARNING: Do NOT abort simple retrieval or lookup queries. A categorical string can still be retrieved and displayed.
    ONLY return out_of_domain_unanswerable if the user explicitly asks to perform MATHEMATICAL AGGREGATION (Average, Sum, Math) on a field that is listed as a 'categorical_string'.

    Possible Intents:
    - "point_lookup" (Fetching facts for a specific entity)
    - "aggregation_numeric" (Valid math on numeric fields)
    - "out_of_domain_unanswerable" (Attempting math on text fields)
    - "boolean_comparison" (Yes/No questions)
    - "taxonomic_reasoning" (Grouping by categories)

    Output strictly a JSON object:
    {{"intent": "intent_name", "confidence": 0.0_to_1.0, "target_field": "exact field requested by the user", "schema_datatype": "numeric|categorical_string|unknown", "reason": "brief schema-grounded explanation"}}
    """


    api_logger.log_call(inputs.get('query'), "Classify")
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
    )
    result = response.choices[0].message.content

    parsed_classification = parse_llm_json(
        result,
        {"intent": "point_lookup", "confidence": 0.0, "reason": "Classifier did not return valid JSON."},
        "Classify",
    )
    final_result = {"classification": normalize_classification(parsed_classification, inputs.get("query", ""))}
    print(f"[DEBUG] Output Classification: {final_result}")
    return final_result

# A finance domain specific operator, needs to be developed further
def semantic_extract_entities(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Extract
    Purpose: Extracts specific financial entities (e.g., Investor IDs, Sectors, Asset Classes)
             from natural language to use as exact WHERE clause filters.
    Expected inputs: 'query'
    """
    prompt = f"""
    The next operator is Extract.
    Extract all financial entities, IDs, and categorical filters from the query.

    User Query: "{inputs.get('query')}"

    Output strictly a JSON object mapping entity types to their values.
    Example: {{"investor_ids": ["INV001"], "sectors": ["Technology"], "time_horizons": []}}
    """

    api_logger.log_call(inputs.get('query'), "Extract")
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
    )
    result = response.choices[0].message.content
    return {"extracted_entities": parse_llm_json(result, {}, "Extract")}

# This operator identifies the qualititative words in the natural language query and converts them into quantitative words. It essentially translates ohrases like "Best performing investments" to "Top 5 investments", etc.
# Also sets the direction (ascending or descending) for ordering
# Useful in case the Planner module decides to use python libraries like Pandas to generate output isteas of the Generate operator
def semantic_order_by(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Semantic OrderBy
    Purpose: Translates qualitative sorting requests (e.g., "best performing", "safest")
             into physical column sorts and directions.
    Expected inputs: 'query', 'schema_details'
    """
    prompt = f"""
    The next operator is Semantic OrderBy.
    Translate the qualitative sorting request in the query into physical columns and directions.

    User Query: "{inputs.get('query')}"
    Schema Details: {json.dumps(inputs.get('schema_details', {}))}

    Output strictly a JSON object. Example: {{"order_by": "annual_return_pct", "direction": "DESC", "limit": 5}}
    """

    api_logger.log_call(inputs.get('query'), "Order_By")
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
    )
    result = response.choices[0].message.content
    return {"sorting_logic": parse_llm_json(result, {"order_by": None, "direction": "DESC", "limit": None}, "Order_By")}



#When the DAG splits into parallel branches (e.g., Branch 1 looks up the investor's health score, and Branch 2 checks their rebalancing actions), this operator waits for both to finish,
#reads the outputs from both branches, and uses the LLM to cross-reference them into a single, cohesive answer.
def semantic_integrate(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Integrate
    Purpose: Merges the results of parallel DAG branches into a single, cohesive final output.
    """
    prompt = f"""
    The next operator is Integrate.
    You are receiving data from multiple parallel execution branches. Your task is to synthesize
    this information to answer the original user query.

    User Query: "{inputs.get('query')}"

    Branch 1 Data: {json.dumps(inputs.get('branch_1_output', {}))}
    Branch 2 Data: {json.dumps(inputs.get('branch_2_output', {}))}

    Cross-reference the data from both branches and output the final, integrated answer.
    """

    api_logger.log_call(inputs.get('query'), "Integrate")
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0.2
    )
    return {"integrated_result": response.choices[0].message.content.strip()}




# PRE-PROGRAMMED OPERATORS

def _sparql_query_worker(instance_file: str, sparql_query: str, result_queue: Any) -> None:
    """Run rdflib query work in a killable process."""
    try:
        rdf_graph = rdflib.Graph()
        rdf_graph.parse(instance_file, format="turtle")
        results = rdf_graph.query(sparql_query)
        data = []
        for row in results:
            row_dict = {str(var): str(val) for var, val in zip(results.vars, row)}
            data.append(row_dict)

        result_queue.put({
            "status": "success",
            "data": data,
            "row_count": len(data),
            "sparql": sparql_query
        })
    except Exception as e:
        result_queue.put({
            "status": "error",
            "error_message": str(e),
            "failed_sparql": sparql_query
        })


def execute_sparql_with_timeout(
    rdf_graph: rdflib.Graph,
    sparql_query: str,
    timeout_seconds: float,
    instance_file: str = INSTANCE_FILE,
) -> Dict[str, Any]:
    """
    Execute SPARQL in a subprocess so a stuck rdflib query can be terminated.
    Python threads cannot safely interrupt a CPU-bound or blocked graph query.
    """
    if timeout_seconds <= 0:
        try:
            results = rdf_graph.query(sparql_query)
            data = []
            for row in results:
                row_dict = {str(var): str(val) for var, val in zip(results.vars, row)}
                data.append(row_dict)
            return {
                "status": "success",
                "data": data,
                "row_count": len(data),
                "sparql": sparql_query
            }
        except Exception as e:
            return {
                "status": "error",
                "error_message": str(e),
                "failed_sparql": sparql_query
            }

    try:
        ctx = multiprocessing.get_context(SPARQL_SCAN_PROCESS_START_METHOD)
    except ValueError:
        ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue(maxsize=1)
    process = ctx.Process(
        target=_sparql_query_worker,
        args=(instance_file, sparql_query, result_queue),
    )
    process.daemon = True
    process.start()

    deadline = time.monotonic() + timeout_seconds
    while process.is_alive():
        try:
            result = result_queue.get_nowait()
            process.join(timeout=1)
            return result
        except queue.Empty:
            pass

        if time.monotonic() >= deadline:
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            return {
                "status": "error",
                "error_message": f"SPARQL execution timed out after {timeout_seconds:g} seconds.",
                "failed_sparql": sparql_query,
                "timeout_seconds": timeout_seconds,
            }

        time.sleep(0.05)

    try:
        return result_queue.get(timeout=1)
    except queue.Empty:
        return {
            "status": "error",
            "error_message": f"SPARQL worker exited without returning a result (exitcode={process.exitcode}).",
            "failed_sparql": sparql_query,
        }


#the actual SPARQL query execution takes place through this operator
#since no intervention from human/LLM is required in executing the SPARQL query, this is made as a pre-programmed operator
def pre_programmed_scan(inputs: Dict[str, Any], rdf_graph: rdflib.Graph) -> Dict[str, Any]:
    """
    Operator: Scan
    Purpose: Executes the LLM-generated SPARQL query deterministically against
             the RDF Knowledge Graph and parses the output.
    Inputs: 'sparql'
    Outputs: 'data' (List of Dicts), 'row_count'
    """
    sparql_query = repair_sparql_query(inputs.get("sparql", ""))
    print(f"\n[DEBUG SPARQL EXECUTED]\n{sparql_query}\n")
    if not sparql_query:
        return {"status": "error", "error_message": "No SPARQL provided to Scan operator."}

    term_check = validate_sparql_terms(sparql_query, rdf_graph)
    if not term_check["is_valid"]:
        return {
            "status": "error",
            "error_message": "SPARQL uses terms that do not exist in the RDF graph.",
            "failed_sparql": sparql_query,
            "unknown_terms": term_check["unknown_terms"],
            "term_suggestions": term_check["suggestions"],
        }

    try:
        return execute_sparql_with_timeout(
            rdf_graph,
            sparql_query,
            SPARQL_SCAN_TIMEOUT_SECONDS,
        )
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "failed_sparql": sparql_query
        }

# Acts as a pre-execution safety check by verifying that the prefixes and syntax
# written in the generated SPARQL actually exist in the database.
def pre_programmed_check_schema(inputs: Dict[str, Any], rdf_graph: rdflib.Graph) -> Dict[str, Any]:
    """
    Operator: Schema Validation
    Purpose: Acts as a pre-execution safety check to ensure SPARQL queries
             contain the required prefixes and syntax before execution.
    """
    sparql = inputs.get("sparql", "")
    issues = []

    if "PREFIX wm: <https://wealth.example.org/ontology/>" not in sparql:
         issues.append("Missing the required 'wm:' prefix.")

    #Check for basic SPARQL keywords
    if "SELECT" not in sparql.upper() and "ASK" not in sparql.upper():
         issues.append("Query does not contain a SELECT or ASK statement.")

    if issues:
        return {"is_valid": False, "schema_errors": issues}
    return {"is_valid": True, "sparql_to_execute": sparql}


# Uses Pandas to calculate basic statistical operations (sum, average, percentage difference)
# directly on raw data arrays without needing to write or execute SPARQL.
#also, first converting the kg columns from strings to numbers for math operations
def pre_programmed_math_compute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Math Compute
    Purpose: Performs standard financial calculations (sum, average, percentage_diff)
             on extracted DataFrames without needing backend SQL/SPARQL aggregations.
    """
    df = pd.DataFrame(inputs.get("data", []))
    if df.empty:
        return {"computed_value": None, "error": "Empty dataset provided."}

    operation = inputs.get("operation", "").lower()
    col = inputs.get("target_column")

    try:
        #Force the SPARQL string outputs into numeric values
        df[col] = pd.to_numeric(df[col], errors='coerce')

        if operation == "sum":
            result = df[col].sum()
        elif operation == "avg":
            result = df[col].mean()
        elif operation == "percentage_diff" and 'base_col' in inputs:
            base_col = inputs.get('base_col')
            df[base_col] = pd.to_numeric(df[base_col], errors='coerce')
            df['pct_diff'] = ((df[col] - df[base_col]) / df[base_col]) * 100
            result = df.to_dict(orient='records')
        else:
            result = "Unsupported mathematical operation."

        return {"computed_result": result}
    except KeyError:
        return {"error": f"Column {col} not found in data."}


def pre_programmed_set_intersect(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Set (Intersection)
    Purpose: Intersects two lists of data (e.g., finding investor_ids that appear in both lists).
    Expected inputs: 'list_a' (list of dicts), 'list_b' (list of dicts), 'join_key' (str).
    """
    list_a = inputs.get("list_a", [])
    list_b = inputs.get("list_b", [])
    join_key = inputs.get("join_key", "investor_id")

    # Extract keys
    keys_a = {item[join_key] for item in list_a if join_key in item}
    keys_b = {item[join_key] for item in list_b if join_key in item}

    # Intersect
    intersected_keys = keys_a.intersection(keys_b)

    # Filter original items based on intersection
    result = [item for item in list_a if item.get(join_key) in intersected_keys]

    return {"intersected_data": result, "count": len(result)}


# Merges two separate datasets into a single combined list while
# automatically identifying and removing any duplicate records.
def pre_programmed_union(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Set Union
    Purpose: Combines two data arrays and drops exact duplicates.
    Expected inputs: 'list_a' (list of dicts), 'list_b' (list of dicts)
    """
    df_a = pd.DataFrame(inputs.get("list_a", []))
    df_b = pd.DataFrame(inputs.get("list_b", []))

    # Concat and drop exact duplicates
    df_union = pd.concat([df_a, df_b]).drop_duplicates().reset_index(drop=True)
    return {"union_data": df_union.to_dict(orient='records'), "count": len(df_union)}


# Compares two datasets and returns only the unique records from the
# first list that do *not* appear in the second list.
def pre_programmed_difference(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Set Difference
    Purpose: Finds records in List A that are NOT in List B based on a specific key.
    Expected inputs: 'list_a', 'list_b', 'join_key' (e.g., 'investor_id')
    """
    list_a = inputs.get("list_a", [])
    list_b = inputs.get("list_b", [])
    join_key = inputs.get("join_key", "investor_id")

    keys_b = {item[join_key] for item in list_b if join_key in item}

    # Keep items in A where the key is NOT in B
    result = [item for item in list_a if item.get(join_key) not in keys_b]
    return {"difference_data": result, "count": len(result)}





class AdvancedAOPPlanner:

    """
    Acts as the reasoning engine of the Agent-Oriented Pipeline.
    Generates multiple candidate execution paths(set to 3), converts them to Directed Acyclic Graphs (DAGs)
    for parallel execution, and evaluates them using a Reward Model to find the optimal path.
    """

    def __init__(self, llm_client, operator_registry: Dict[str, Any], model: str = LOCAL_MODEL):
        self.client = llm_client
        self.registry = operator_registry
        self.model = model

        #Heuristic Costs for the DAG evaluation
        # Pre-programmed operators (Python/Graph) are cheap and fast.
        # Semantic operators (LLM calls) are expensive and slow.
        #Below numerics based on time-efficiency only
        #This score is used later to prevent lengthy routes
        #Can be further analysed and changed (heavily depends on the model that is being used)
        self.operator_costs = {
            "Retrieve": 2,
            "Check_Schema": 1,
            "Link": 2,
            "Extract": 2,
            "Generate": 5,
            "Refine": 4,
            "Scan": 1,
            "Validate": 3,
            "Math_Compute": 1,
            "Set_Intersect": 1,
            "Set_Union": 1,
            "Set_Difference": 1,
            "Classify": 2,
            "Filter_Aggregate": 3,
            "Order_By": 2,
            "Integrate": 6,
            "Explain": 8
        }

    def _planner_completion(
        self,
        prompt: str,
        temperature: float | None = None,
        json_output: bool = False,
    ):
        request = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None and not self.model.lower().startswith("gpt-5"):
            request["temperature"] = temperature
        return self.client.chat.completions.create(**request)

    #This function generates (using randomness of the LLM), evaluates(above cost heuristics and a separate evaluator
    #where the LLM acts as  judge based on certain laws specified by us (discussed later)), and selects the most
    #efficient one
    def plan_optimal_dag(
        self,
        query: str,
        num_candidates: int = 3,
        planning_round: int = 1,
    ) -> nx.DiGraph:
        """Generates, evaluates, and selects the most efficient execution DAG."""
        if os.getenv("DAG_PLANNER_MODE", "multi_candidate").strip().lower() == "one_shot":
            return self._plan_one_shot_best_dag(query, num_candidates=num_candidates)

        max_planning_rounds = int(os.getenv("DAG_PLANNER_MAX_ROUNDS", "3"))
        print(
            f"--- Planning Round {planning_round}/{max_planning_rounds}: "
            f"Generating {num_candidates} Candidate Paths ---"
        )

        candidate_chains = []

        #Threaded Generation of initial chains
        #temperature is non zero so as to encourage creativity and generation of multiple distinct paths
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_candidates) as chain_runner:
            chains = list(chain_runner.map(lambda _: self._generate_linear_chain(query, temperature=0.3), range(num_candidates)))
            for chain in chains:
                if chain not in candidate_chains:
                    candidate_chains.append(chain)

        print(f"Generated {len(candidate_chains)} unique linear plans.")

        # Thread Worker Function
        #Checks if it is actually a DAG
        def process_candidate(chain_data):
            idx, chain = chain_data
            try:
                dag_data = self._rewrite_to_dag(chain, query, temperature=0.0)
                dag = self._build_networkx_dag(dag_data)

                is_valid, reason = self._validate_planned_dag(dag, query)
                if not is_valid:
                    print(f"\n   -> Evaluating Path {idx + 1}... [REJECTED BY PYTHON: {reason}]")
                    return None

                print(f"\n   -> Evaluating Path {idx + 1}...")
                reward_score = self._evaluate_dag_reward(dag_data, query)  #here we are using the evaluator function defined later where LLM as a judge rates our DAG
                cost = self._calculate_dag_cost(dag)

                print(f"      [System] Path {idx + 1} Final Metrics -> Reward: {reward_score} | Cost: {cost}")
                return (dag, reward_score, cost)
            except Exception as e:
                print(f"   -> Path {idx + 1} failed DAG compilation: {e}")
                return None

        #Threaded Evaluation of DAGs
        evaluated_dags = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_candidates) as executor:
            results = list(executor.map(process_candidate, enumerate(candidate_chains)))
            evaluated_dags = [res for res in results if res is not None]

        if not evaluated_dags:
            if planning_round < max_planning_rounds:
                print("[WARN] No valid dynamic DAGs. Replanning with new candidates.")
                return self.plan_optimal_dag(
                    query,
                    num_candidates=num_candidates,
                    planning_round=planning_round + 1,
                )
            raise RuntimeError("The planner did not produce any valid DAG.")

        highly_rated_dags = [d for d in evaluated_dags if d[1] >= 0.9]

        if highly_rated_dags:
            best_dag_tuple = min(highly_rated_dags, key=lambda x: (x[2], -x[1]))
            print(f"\n--- Selected Optimal DAG (Reward: {best_dag_tuple[1]} | Lowest Cost: {best_dag_tuple[2]}) ---")
            best_dag = best_dag_tuple[0]
        else:
            best_dag_tuple = max(evaluated_dags, key=lambda x: x[1])

            if best_dag_tuple[1] == 0.0:
                if planning_round < max_planning_rounds:
                    print("[WARN] All evaluated DAGs scored 0.0. Replanning with new candidates.")
                    return self.plan_optimal_dag(
                        query,
                        num_candidates=num_candidates,
                        planning_round=planning_round + 1,
                    )
                raise RuntimeError("All dynamically planned DAGs were rejected by the evaluator.")
            else:
                print(f"\n--- Selected Highest Reward Dynamic DAG (Reward: {best_dag_tuple[1]} | Cost: {best_dag_tuple[2]}) ---")
                best_dag = best_dag_tuple[0]

        return best_dag

    def _query_requires_classify(self, query: str) -> bool:
        return bool(re.search(
            r"\b(average|avg|sum|total|min|max|minimum|maximum|count|how many|"
            r"highest|lowest|largest|smallest)\b",
            query,
            flags=re.I,
        ))

    def _operator_position(self, dag: nx.DiGraph, ordered_nodes: list, operator: str) -> int | None:
        for position, node in enumerate(ordered_nodes):
            if dag.nodes[node].get("operator") == operator:
                return position
        return None

    def _validate_planned_dag(self, dag: nx.DiGraph, query: str) -> tuple[bool, str]:
        if not nx.is_directed_acyclic_graph(dag):
            return False, "planned graph contains a cycle"

        ordered_nodes = list(nx.topological_sort(dag))
        operators = [dag.nodes[node].get("operator") for node in ordered_nodes]
        required = ["Retrieve", "Generate", "Scan", "Validate", "Explain"]
        missing = [operator for operator in required if operator not in operators]
        if missing:
            return False, f"missing required operators: {missing}"

        retrieve_pos = self._operator_position(dag, ordered_nodes, "Retrieve")
        classify_pos = self._operator_position(dag, ordered_nodes, "Classify")
        generate_pos = self._operator_position(dag, ordered_nodes, "Generate")
        scan_pos = self._operator_position(dag, ordered_nodes, "Scan")
        validate_pos = self._operator_position(dag, ordered_nodes, "Validate")
        explain_pos = self._operator_position(dag, ordered_nodes, "Explain")

        if not (retrieve_pos < generate_pos < scan_pos < validate_pos < explain_pos):
            return False, "operator order must be Retrieve -> Generate -> Scan -> Validate -> Explain"
        if classify_pos is not None and classify_pos > generate_pos:
            return False, "Classify must run before Generate when present"
        if operators[-1] != "Explain":
            return False, "Explain must be the final operator"
        if self._query_requires_classify(query) and classify_pos is None:
            return False, "math/aggregation query should include Classify before Generate"

        required_dependencies = [
            (ordered_nodes[retrieve_pos], ordered_nodes[generate_pos], "Retrieve -> Generate"),
            (ordered_nodes[generate_pos], ordered_nodes[scan_pos], "Generate -> Scan"),
            (ordered_nodes[scan_pos], ordered_nodes[validate_pos], "Scan -> Validate"),
            (ordered_nodes[validate_pos], ordered_nodes[explain_pos], "Validate -> Explain"),
        ]
        if classify_pos is not None:
            required_dependencies.append(
                (ordered_nodes[classify_pos], ordered_nodes[generate_pos], "Classify -> Generate")
            )
        for source, target, dependency_name in required_dependencies:
            if not nx.has_path(dag, source, target):
                return False, f"missing dependency path: {dependency_name}"

        return True, "valid"

    def _plan_one_shot_best_dag(self, query: str, num_candidates: int = 3) -> nx.DiGraph:
        print(f"--- One-shot DAG planning: internally selecting best of {num_candidates} candidates ---")
        prompt = f"""
You are the one-shot DAG planner for an Agent-Oriented Pipeline.

User Query: "{query}"
Available Operators (use exact names only): {list(self.registry.keys())}

Your internal task:
1. Create {num_candidates} candidate execution chains for the query.
2. Rewrite each candidate chain into a DAG.
3. Evaluate each DAG for correctness and cost.
4. Select the single best DAG.

Planning laws:
- Retrieve must happen before Generate.
- If the query asks for math, aggregation, or a numeric superlative using words like average, sum, min, max, count, how many, highest, lowest, largest, or smallest, include Classify before Generate.
- Do not use Classify for simple lookup/listing questions.
- Generate must happen before Scan.
- Scan must happen before Validate.
- Explain must be the final operator.
- Do not include Refine in the planned DAG; runtime self-healing handles refinement only when Scan fails.
- Avoid unnecessary operators such as Link, Extract, Filter_Aggregate, Order_By, Integrate, and set operators unless they are truly required by the question.
- Prefer the lowest-cost valid DAG.

Return ONLY one JSON object for the selected best DAG using this schema:
{{
  "nodes": [
    {{"id": "unique node id", "operator": "one available operator", "inputs": {{}}}}
  ],
  "edges": [
    {{"source": "upstream node id", "target": "downstream node id"}}
  ],
  "selected_reason": "short reason"
}}
"""
        try:
            api_logger.log_call(query, "Planner_OneShot_Best_DAG")
            response = self._planner_completion(
                prompt,
                temperature=0.2,
                json_output=True,
            )
            result = response.choices[0].message.content
            dag_data = parse_llm_json(result, {}, "Planner_OneShot_Best_DAG")
            if not dag_data.get("nodes"):
                raise ValueError("Planner returned no DAG nodes.")
            dag = self._build_networkx_dag(dag_data)
            is_valid, reason = self._validate_planned_dag(dag, query)
            if not is_valid:
                raise ValueError(f"One-shot DAG rejected by Python validator: {reason}")

            sequence = " -> ".join(dag.nodes[node].get("operator", "") for node in nx.topological_sort(dag))
            cost = self._calculate_dag_cost(dag)
            print(f"--- Selected One-Shot DAG | Cost: {cost} | Sequence: {sequence} ---")
            return dag
        except Exception as e:
            raise RuntimeError(f"One-shot planner failed without using a manual DAG: {e}") from e

    #responsible for first making the linear chains that will later be converted to DAGs based on the ability
    #to make the flow parallel , if feasible
    #this improved efficiency manifolds
    def _generate_linear_chain(self, query: str, temperature: float) -> str:
        prompt = f"""
        Write a step-by-step, linear execution plan to answer this query using ONLY the provided operators.
        Query: "{query}"

        AVAILABLE OPERATORS (EXACT MATCH ONLY): {list(self.registry.keys())}

        CRITICAL LAWS OF EXECUTION (YOU MUST FOLLOW THIS CHRONOLOGY):
        1. You must start by finding the ontology classes. Use 'Retrieve'.
        2. CRITICAL: Use 'Classify' for math, aggregation, or numeric-superlative words such as 'Average', 'Sum', 'Min', 'Max', 'Count', 'Highest', 'Lowest', 'Largest', or 'Smallest'. If the query is only a simple lookup/listing question, go straight from 'Retrieve' to 'Generate'.
        3. If querying the knowledge graph, 'Generate' (writing SPARQL) must happen AFTER 'Classify' (or 'Retrieve').
        4. 'Scan' (executing Graph query) must happen immediately AFTER 'Generate'.
        5. 'Validate' (checking data) must happen AFTER 'Scan'.
        6. 'Explain' (talking to the user) MUST be the absolute final step.

        CRITICAL RULE: Do NOT invent new operators. You must use the EXACT string names listed above.
        For example, use "Retrieve", do not use "RetrieveDataset" or "Retrieve_Classes".

        Output ONLY the numbered steps.
        """

        api_logger.log_call(query, "Planner_Generate_Chain")
        response = self._planner_completion(prompt, temperature=temperature)
        return response.choices[0].message.content.strip()

    def _rewrite_to_dag(self, linear_chain: str, query: str, temperature: float) -> Dict:
        classify_rule = (
            "Classify is REQUIRED and must have a directed path to Generate."
            if self._query_requires_classify(query)
            else "Classify is optional for this query."
        )
        prompt = f"""
        Rewrite this linear plan into a Directed Acyclic Graph (DAG).
        Preserve all mandatory execution dependencies. Parallelize only genuinely independent optional work.

        User Query: {query}
        Linear Plan: {linear_chain}

        AVAILABLE OPERATORS: {list(self.registry.keys())}
        CRITICAL: Under the 'operator' key in your JSON, you MUST use the exact operator names listed above. Do not invent names.

        MANDATORY DIRECTED DEPENDENCY PATHS:
        - Retrieve -> Generate
        - Generate -> Scan
        - Scan -> Validate
        - Validate -> Explain
        - Explain must be the final sink node.
        - {classify_rule}
        - Never place Scan before Generate.
        - Never remove a mandatory dependency merely to create parallelism.

        Output strictly a JSON object with 'nodes' (id, operator, inputs) and 'edges' (source, target).
        """

        api_logger.log_call(query, "Planner_Rewrite_DAG")
        response = self._planner_completion(
            prompt,
            temperature=temperature,
            json_output=True,
        )
        result = response.choices[0].message.content
        dag_data = parse_llm_json(result, {}, "Planner_Rewrite_DAG")
        if not dag_data.get("nodes"):
            raise ValueError("DAG rewrite returned no nodes.")
        return dag_data

    def _build_networkx_dag(self, dag_data: Dict) -> nx.DiGraph:
        dag = nx.DiGraph()
        for node in dag_data.get("nodes", []):
            operator = node.get("operator")
            if operator not in self.registry:
                raise ValueError(f"Unknown operator in planned DAG: {operator}")
            dag.add_node(node["id"], operator=operator, explicit_inputs=node.get("inputs", {}))
        for edge in dag_data.get("edges", []):
            dag.add_edge(edge["source"], edge["target"])
        return dag

    #The main judge function
    #We instruct the LLM to judge our DAGs based on a set of LAWS (can be changed as per our needs) and provide a score
    def _evaluate_dag_reward(self, dag_data: Dict, query: str) -> float:
        """Use Python for structural validity and the LLM only for semantic efficiency."""
        try:
            temp_dag = self._build_networkx_dag(dag_data)
            is_valid, validation_reason = self._validate_planned_dag(temp_dag, query)
            if not is_valid:
                print(f"      [Python Validator] Rejected DAG: {validation_reason}")
                return 0.0
            ordered_nodes = list(nx.topological_sort(temp_dag))
            sequence_str = " -> ".join([temp_dag.nodes[n]["operator"] for n in ordered_nodes])
            optional_operators = [
                temp_dag.nodes[node]["operator"]
                for node in ordered_nodes
                if temp_dag.nodes[node]["operator"]
                not in {"Retrieve", "Classify", "Generate", "Scan", "Validate", "Explain"}
            ]
        except Exception:
            return 0.0

        prompt = f"""
        You are evaluating the semantic efficiency of a Python-validated AOP DAG.
        Assign a Reward Score between 0.0 and 1.0.

        User Query: "{query}"
        Python-validated Execution Sequence: {sequence_str}
        Optional Operators: {optional_operators}

        Important facts already verified by Python:
        - Retrieve is before Generate.
        - Generate is before Scan.
        - Scan is before Validate.
        - Validate is before Explain.
        - Explain is final.
        - Classify is before Generate whenever the query requires it.
        - Retrieve, Generate, Scan, Validate, and Explain are mandatory core operators.
        Do not dispute these facts and do not penalize mandatory core operators.

        Score only whether any optional operators are useful for this specific query:
        - 1.0: efficient and semantically appropriate.
        - 0.5: valid but contains unnecessary optional operators.
        - 0.0: optional operators make the plan semantically unsuitable.

        Output strictly a JSON object: {{"reward_score": 0.0, "reasoning": "Brief explanation"}}
        """
        try:

            api_logger.log_call(query, "Planner_Evaluate_DAG")
            response = self._planner_completion(
                prompt,
                temperature=0.0,
                json_output=True,
            )
            result = response.choices[0].message.content
            evaluation = parse_llm_json(
                result,
                {"reward_score": 0.0, "reasoning": "Evaluator did not return valid JSON."},
                "Planner_Evaluate_DAG",
            )
            if isinstance(evaluation, list):
                evaluation = next((item for item in evaluation if isinstance(item, dict)), {})
            if not isinstance(evaluation, dict):
                evaluation = {
                    "reward_score": 0.0,
                    "reasoning": "Evaluator returned a non-object response.",
                }

            raw_score = max(0.0, min(1.0, float(evaluation.get("reward_score", 0.0))))
            adjusted_score = max(0.5, raw_score)
            print(
                f"      [Evaluator] Semantic Score: {raw_score} | "
                f"Adjusted Valid-DAG Score: {adjusted_score} | "
                f"Reason: {evaluation.get('reasoning')}"
            )
            return adjusted_score
        except Exception as e:
            print(f"      [Evaluator] Semantic scoring failed: {e}. Using valid-DAG score 0.5.")
            return 0.5

    def _calculate_dag_cost(self, dag: nx.DiGraph) -> int:
        """
        Calculates the heuristic cost of the DAG.
        Cost = Sum of all operator base costs + Depth Penalty (latency).
        """
        total_cost = 0

        # Sum base costs
        for node in dag.nodes:
            op_name = dag.nodes[node]["operator"]
            total_cost += self.operator_costs.get(op_name, 5) # Default penalty if unknown

        # Add penalty for critical path length (latency)
        critical_path_length = nx.dag_longest_path_length(dag)
        total_cost += (critical_path_length * 2)

        return total_cost
    



def get_actual_properties_for_failed_query(failed_sparql: str, rdf_graph) -> list:
    """
    Extracts the entity string from a failed SPARQL query, queries the graph
    for that entity, and returns the actual property URIs that exist on it.
    """
    if not rdf_graph:
        return []

    # 1. Extract potential string literals from the failed query (e.g., "INV003" or "INV-003")
    literals = re.findall(r'["\']([^"\']+)["\']', failed_sparql)

    actual_props = set()
    for literal in literals:
        # Skip small/generic strings
        if len(literal) < 3:
            continue

        # 2. Search the physical graph for ANY node that contains this string
        # (Using LCASE to catch "inv003" vs "INV-003" mismatches)
        query = f"""
        SELECT DISTINCT ?p WHERE {{
          ?s ?p ?o .
          FILTER(CONTAINS(LCASE(STR(?o)), "{literal.lower()}"))
        }}
        """
        try:
            for row in rdf_graph.query(query):
                # Clean up the URI to match how the LLM writes prefixes (wm:property)
                prop = str(row[0]).replace("https://wealth.example.org/ontology/", "wm:")
                actual_props.add(prop)
        except Exception:
            continue

        if actual_props:
            break # We found the real properties! Stop searching.

    return list(actual_props)





class AOPExecutor:

    """
    Executes the generated DAG topologically. Manages state transitions,
    the Global Data Bus (context preservation), and the Self-Healing validation loops.
    """
    def __init__(self, operator_registry: Dict[str, Any], rdf_graph: rdflib.Graph):
        self.registry = operator_registry
        self.rdf_graph = rdf_graph

    def execute_dag(self, dag: nx.DiGraph, initial_query: str) -> Any:
        print("\n--- Starting DAG Execution ---")
        results_cache = {"global_query": initial_query}
        trace = {
            "operator_sequence": [],
            "retrieved_classes": [],
            "generated_sparql": "",
            "scan_status": "",
            "scan_row_count": "",
            "scan_error": "",
            "scan_raw_rows": "",
            "unknown_terms": [],
            "term_suggestions": {},
            "refine_reason": "",
            "validation_is_valid": "",
            "validation_reason": "",
            "self_heal_attempts": 0,
            "short_circuit_stage": "",
            "failure_stage": "",
        }

        for node in nx.topological_sort(dag):
            node_data = dag.nodes[node]
            op_name = node_data["operator"]
            trace["operator_sequence"].append(op_name)
            print(f"Executing: [{op_name}] at Node '{node}'...")

            raw_inputs = node_data.get("explicit_inputs", {})
            if not isinstance(raw_inputs, dict):
                raw_inputs = {}

            inputs = raw_inputs.copy()
            inputs["query"] = initial_query

            #Standard Flow: Get inputs from direct predecessors
            for i, pred in enumerate(dag.predecessors(node)):
                inputs[f"branch_{i+1}_output"] = results_cache[pred]
                if isinstance(results_cache[pred], dict):
                    inputs.update(results_cache[pred])

            # THE GLOBAL DATA BUS FIX
            #Ensures intermediate routing nodes don't drop the 'retrieved_tables' context
            for past_node, past_result in results_cache.items():
                if isinstance(past_result, dict) and "retrieved_tables" in past_result:
                    if "retrieved_tables" not in inputs:
                        inputs["retrieved_tables"] = []
                    # Safely merge tables without duplicates
                    for tbl in past_result["retrieved_tables"]:
                        if tbl not in inputs["retrieved_tables"]:
                            inputs["retrieved_tables"].append(tbl)
                if isinstance(past_result, dict) and past_result.get("data") and "data" not in inputs:
                    inputs["data"] = past_result["data"]
                if isinstance(past_result, dict) and past_result.get("sparql") and "sparql" not in inputs:
                    inputs["sparql"] = past_result["sparql"]

            # Operator execution & self-healing routing
            if op_name not in self.registry:
                raise ValueError(f"Operator {op_name} not found in registry!")

            operator_func = self.registry[op_name]

            # THE SELF-HEALING LOOP (Syntax & DB Errors)
            #max number of retires can be changed as per needs
            if op_name == "Scan":
                max_retries = SPARQL_SCAN_MAX_RETRIES
                attempt = 0
                while attempt < max_retries:
                    result = operator_func(inputs)

                    if result.get("status") == "error":
                        attempt += 1
                        print(f"   [!] SPARQL Error Caught: {result.get('error_message')}")
                        trace["scan_status"] = "error"
                        trace["scan_error"] = result.get("error_message", "")
                        trace["unknown_terms"] = result.get("unknown_terms", trace["unknown_terms"])
                        trace["term_suggestions"] = result.get("term_suggestions", trace["term_suggestions"])
                        if result.get("unknown_terms"):
                            trace["refine_reason"] = "Unknown RDF terms before Scan"
                        if attempt == max_retries:
                            print("   [!] Max retries reached for Scan. Short-circuiting directly to Explain.")
                            trace["short_circuit_stage"] = "Scan"
                            trace["failure_stage"] = "Scan"
                            explain_inputs = {
                                "query": initial_query,
                                "data": [],
                                "context": "A database error prevented data retrieval."
                            }
                            final_result = self.registry["Explain"](explain_inputs)
                            if isinstance(final_result, dict):
                                final_result["trace"] = trace
                            print("--- Execution Complete (Short-circuited) ---")
                            return final_result

                        if not result.get("failed_sparql"):
                            print(f"   [+] No SPARQL was available. Triggering [Generate] again (Attempt {attempt}/{max_retries})...")
                            trace["self_heal_attempts"] += 1
                            regenerate_result = self.registry["Generate"](inputs)
                            inputs["sparql"] = regenerate_result.get("sparql", "")
                            trace["generated_sparql"] = inputs["sparql"]
                            continue

                        print(f"   [+] Triggering [Refine] Operator (Attempt {attempt}/{max_retries})...")
                        trace["self_heal_attempts"] += 1
                        is_timeout = "timed out" in str(result.get("error_message", "")).lower()
                        logic_feedback = {
                            "unknown_terms": result.get("unknown_terms", []),
                            "suggestions": result.get("term_suggestions", {}),
                            "error_type": "timeout" if is_timeout else "sparql_error",
                            "hint": (
                                "The previous SPARQL timed out. Treat this as a query-plan problem, "
                                "not a syntax problem. Do not produce the same WHERE pattern. Use "
                                "cardinality_hints to avoid flat joins between classes through literal "
                                "properties that are many_per_value on both sides. Prefer direct object "
                                "relationships, fewer classes, or subqueries/pre-aggregation before joining."
                                if is_timeout
                                else "Rewrite using only valid RDF graph terms. Do not invent predicates or classes."
                            )
                        }
                        refine_inputs = {
                            "failed_sparql": result.get("failed_sparql"),
                            "error_message": result.get("error_message"),
                            "logic_feedback": json.dumps(logic_feedback, indent=2),
                            "query": initial_query,
                        }
                        refine_result = self.registry["Refine"](refine_inputs)
                        new_sparql = refine_result.get("sparql", "")
                        if is_timeout and sparql_too_similar(result.get("failed_sparql", ""), new_sparql):
                            print("   [!] Refined SPARQL is too similar to the timed-out query. Forcing Generate with stronger feedback.")
                            inputs["logic_feedback"] = json.dumps({
                                "error_type": "similar_timeout_rewrite",
                                "failed_sparql": result.get("failed_sparql", ""),
                                "hint": (
                                    "The previous rewrite was too similar to a timed-out query. Produce a "
                                    "structurally different SPARQL query. Use cardinality_hints to avoid "
                                    "flat many_per_value joins through shared literal properties. Use "
                                    "subqueries/pre-aggregation, direct object relationships, or fewer classes."
                                )
                            }, indent=2)
                            regenerate_result = self.registry["Generate"](inputs)
                            new_sparql = regenerate_result.get("sparql", "")
                        inputs["sparql"] = new_sparql
                        trace["generated_sparql"] = inputs["sparql"]
                        print(f"   [+] SPARQL Refined. Retrying [Scan]...")
                    else:
                        break

            # THE LOGIC VALIDATION LOOP (Semantic Errors)

            #|| Making validation loop for max_retires
            # THE LOGIC VALIDATION LOOP
            elif op_name == "Validate":
                max_logic_retries = 3
                attempt = 0

                while attempt < max_logic_retries:
                    result = operator_func(inputs)
                    is_valid = result.get("validation", {}).get("is_valid", False)
                    reason = result.get("validation", {}).get("reason", "")

                    if not is_valid:
                        attempt += 1
                        print(f"   [!] Validation Failed: {reason}")
                        failed_sparql = inputs.get("sparql", "")

                        if not failed_sparql:
                            print("   [-] No SPARQL found to refine. Skipping self-healing.")
                            result = {"data": inputs.get("data", [])}
                            break

                        if attempt == max_logic_retries:
                            print("   [!] Max logic retries reached. Short-circuiting directly to Explain.")
                            trace["short_circuit_stage"] = "Validate"
                            trace["failure_stage"] = "Validate"
                            if inputs.get("data"):
                                explain_inputs = {
                                    "query": initial_query,
                                    "data": inputs.get("data", []),
                                }
                            else:
                                explain_inputs = {
                                    "query": initial_query,
                                    "data": [],
                                    "context": "No data was found in the knowledge graph. The requested entity may not exist."
                                }
                            final_result = self.registry["Explain"](explain_inputs)
                            if isinstance(final_result, dict):
                                final_result["trace"] = trace
                            print("--- Execution Complete (Short-circuited) ---")
                            return final_result

                        print(f"   [+] Fetching actual properties from KG for failed query...")
                        actual_props = get_actual_properties_for_failed_query(failed_sparql, self.rdf_graph)

                        logic_feedback = {
                            "error": "empty result - you hallucinated a property or used exact case-matching",
                            "actual_properties_on_node": actual_props if actual_props else "Unknown - ensure you are using exact prefixes and LCASE()",
                            "hint": "Do NOT guess property names. Use ONLY the listed properties above."
                        }
                        trace["refine_reason"] = "Validation failed or zero rows"

                        print(f"   [+] Triggering [Generate] to rewrite logic (Attempt {attempt}/{max_logic_retries})...")

                        # Pass the rich JSON feedback back to Generate
                        inputs["logic_feedback"] = json.dumps(logic_feedback, indent=2)

                        # Generate new SPARQL with awareness of the actual properties
                        trace["self_heal_attempts"] += 1
                        new_sparql_result = self.registry["Generate"](inputs)
                        inputs["sparql"] = new_sparql_result["sparql"]
                        trace["generated_sparql"] = inputs["sparql"]

                        print(f"   [+] Rerunning [Scan] with updated logic...")
                        scan_result = self.registry["Scan"]({"sparql": new_sparql_result["sparql"]})
                        inputs["data"] = scan_result.get("data", [])
                        trace["scan_status"] = scan_result.get("status", trace["scan_status"])
                        trace["scan_row_count"] = scan_result.get("row_count", trace["scan_row_count"])
                        trace["scan_error"] = scan_result.get("error_message", trace["scan_error"])
                        trace["scan_raw_rows"] = json.dumps(scan_result.get("data", []), ensure_ascii=False)
                        trace["unknown_terms"] = scan_result.get("unknown_terms", trace["unknown_terms"])
                        trace["term_suggestions"] = scan_result.get("term_suggestions", trace["term_suggestions"])
                    else:
                        print("   [+] Validation Passed.")
                        break

            # THE ILLEGAL MATH SHORT-CIRCUIT
            elif op_name == "Classify":
                result = operator_func(inputs)
                classification = normalize_classification(result.get("classification", {}), initial_query)
                result["classification"] = classification
                intent = classification.get("intent", "")
                reason = classification.get("reason", "")

                if intent == "out_of_domain_unanswerable":
                    print(f"   [!] Classify caught unanswerable math logic: {reason}. Short-circuiting to Explain.")
                    trace["short_circuit_stage"] = "Classify"
                    explain_inputs = {
                        "query": initial_query,
                        "data": [],
                        "context": f"The query asks for a mathematical calculation on a text field, which is not supported by the data model. Reason: {reason}"
                    }
                    final_result = self.registry["Explain"](explain_inputs)
                    if isinstance(final_result, dict):
                        final_result["trace"] = trace
                    print("--- Execution Complete (Short-circuited) ---")
                    return final_result
            # Standard Execution for all other operators
            else:
                result = operator_func(inputs)

            # Store Result in Memory
            if isinstance(result, dict):
                if "retrieved_tables" in result:
                    trace["retrieved_classes"] = result.get("retrieved_tables", [])
                if "sparql" in result:
                    trace["generated_sparql"] = result.get("sparql", "")
                if op_name == "Scan":
                    trace["scan_status"] = result.get("status", "")
                    trace["scan_row_count"] = result.get("row_count", "")
                    trace["scan_error"] = result.get("error_message", "")
                    trace["scan_raw_rows"] = json.dumps(result.get("data", []), ensure_ascii=False)
                    trace["unknown_terms"] = result.get("unknown_terms", trace["unknown_terms"])
                    trace["term_suggestions"] = result.get("term_suggestions", trace["term_suggestions"])
                    if result.get("status") == "error":
                        trace["failure_stage"] = "Scan"
                if op_name == "Validate":
                    validation = result.get("validation", {})
                    trace["validation_is_valid"] = validation.get("is_valid", "")
                    trace["validation_reason"] = validation.get("reason", "")
                    if validation and not validation.get("is_valid", False):
                        trace["failure_stage"] = "Validate"
            results_cache[node] = result
            print(f" {op_name} completed.")

        last_node = list(nx.topological_sort(dag))[-1]
        print("--- Execution Complete ---")
        final_result = results_cache[last_node]
        if isinstance(final_result, dict):
            final_result["trace"] = trace
        return final_result
    


    

def main():
    print("\n" + "="*50)
    print("INITIALIZING AOP PIPELINE")
    print("="*50)

    #CONFIGURATION & API SETUP

    generalist_client = build_llm_client()
    planner_client = build_openai_planner_client()
    sparql_generation_client = build_openai_sparql_client()
    print(f"[SYSTEM] Bedrock region: {os.getenv('BEDROCK_REGION') or os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION')}")
    print(f"[SYSTEM] GPT-OSS model: {GPT_OSS_MODEL}")
    print(f"[SYSTEM] Default model: {LOCAL_MODEL}")
    print(f"[SYSTEM] Planner model: {PLANNER_MODEL}")
    print(f"[SYSTEM] Refine model: {REFINE_MODEL}")
    print(f"[SYSTEM] Generate model: {SPARQL_GENERATION_MODEL}")
    print(f"[SYSTEM] Validate model: {VALIDATE_MODEL}")
    print(f"[SYSTEM] Explain model: {EXPLAIN_MODEL}")
    print(f"[SYSTEM] DAG planner mode: {os.getenv('DAG_PLANNER_MODE', 'multi_candidate')}")
    print(f"[SYSTEM] Report file: {REPORT_FILE}")
    script_start_time = time.perf_counter()



    # LOAD RDF KNOWLEDGE GRAPH
    schema_file = SCHEMA_FILE
    instance_file = INSTANCE_FILE

    kg_metadata = load_rdf_knowledge_graph(schema_file, instance_file)
    rdf_graph = setup_rdf_graph(instance_file)
    kg_metadata = add_cardinality_hints(kg_metadata, rdf_graph)

    if not kg_metadata:
        print("[!] ERROR: Could not load Knowledge Graph. Please check RDF files.")
        return

    # Create the token-saving index
    lightweight_index = get_lightweight_table_index(kg_metadata)




    #INITIALIZE OPERATOR REGISTRY

    operator_registry = {
        # Retrieval & Generation
        # Pass the full schema as 'global_schema' so Generate/Refine can prune it dynamically
        "Retrieve": lambda inputs: semantic_retrieve({**inputs, "table_index": lightweight_index}, generalist_client, LOCAL_MODEL),
        "Generate": lambda inputs: semantic_generate_sparql(
            {**inputs, "global_schema": kg_metadata},
            sparql_generation_client,
            SPARQL_GENERATION_MODEL,
        ),
        "Refine": lambda inputs: semantic_refine({**inputs, "global_schema": kg_metadata}, generalist_client, REFINE_MODEL),

        # Execution & Validation
        "Scan": lambda inputs: pre_programmed_scan(inputs, rdf_graph),
        "Validate": lambda inputs: semantic_validate(inputs, generalist_client, VALIDATE_MODEL),
        "Explain": lambda inputs: semantic_explain_results(inputs,generalist_client, EXPLAIN_MODEL),
        "Check_Schema": lambda inputs: pre_programmed_check_schema(inputs, rdf_graph),

        # Mathematical & Set Operations
        "Math_Compute": lambda inputs: pre_programmed_math_compute(inputs),
        "Set_Intersect": lambda inputs: pre_programmed_set_intersect(inputs),
        "Set_Union": lambda inputs: pre_programmed_union(inputs),
        "Set_Difference": lambda inputs: pre_programmed_difference(inputs),

        # Logic & Routing
        "Classify": lambda inputs: semantic_classify_query({**inputs, "schema_details": kg_metadata}, generalist_client, LOCAL_MODEL),
        "Filter_Aggregate": lambda inputs: semantic_filter_aggregate({**inputs, "schema_details": kg_metadata}, generalist_client, LOCAL_MODEL),
        "Order_By": lambda inputs: semantic_order_by({**inputs, "schema_details": kg_metadata}, generalist_client, LOCAL_MODEL),
        "Integrate": lambda inputs: semantic_integrate(inputs, generalist_client, LOCAL_MODEL),
        "Link": lambda inputs: semantic_link({**inputs, "schema_details": kg_metadata}, generalist_client, LOCAL_MODEL),
        "Extract": lambda inputs: semantic_extract_entities(inputs, generalist_client, LOCAL_MODEL)
    }

    planner = AdvancedAOPPlanner(planner_client, operator_registry, model=PLANNER_MODEL)
    executor = AOPExecutor(operator_registry, rdf_graph)



# === 1. LOAD AND FILTER FAILED QUERIES ===

    # Updated to point to your new Excel file
    sample_file = INPUT_SAMPLE_FILE

    try:
        print(f"\n[SYSTEM] Loading {sample_file}...")

        df_all = pd.read_csv(sample_file)

        if {"question", "ground_truth_answer"}.issubset(df_all.columns):
            normalized_records = pd.DataFrame({
                "Sample Row ID": df_all.get("global_question_id", pd.Series(range(1, len(df_all) + 1))).astype(str),
                "Question": df_all["question"].astype(str),
                "Ground Truth": df_all["ground_truth_answer"].astype(str),
                "Status": "NEW_BENCHMARK",
            })
            test_records = normalized_records.iloc[TEST_QUERY_OFFSET:TEST_QUERY_OFFSET + TEST_QUERY_LIMIT].to_dict(orient='records')
            print(f"[SYSTEM] Query window offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT}.")
            print(f"[SYSTEM] Successfully loaded {len(test_records)} benchmark queries from the new dataset.")
        else:
            if "Sample Row ID" not in df_all.columns:
                df_all.insert(0, "Sample Row ID", range(1, len(df_all) + 1))
            if "Status" in df_all.columns:
                df_failed = df_all[df_all['Status'].astype(str).str.strip().str.lower() == 'mismatch'].copy()
            else:
                df_failed = df_all.copy()
            test_records = df_failed.iloc[TEST_QUERY_OFFSET:TEST_QUERY_OFFSET + TEST_QUERY_LIMIT].to_dict(orient='records')
            print(f"[SYSTEM] Query window offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT}.")
            print(f"[SYSTEM] Successfully loaded {len(test_records)} queries.")

    except Exception as e:
        print(f"\n[!] ERROR loading Excel file: {e}")
        return

    def run_single_test(record):
        query_start_time = time.perf_counter()
        started_at = datetime.datetime.now().isoformat(timespec="seconds")
        time.sleep(2)
        query = record.get('Question', '')
        ground_truth = str(record.get('Ground Truth', ''))
        old_status = record.get('Status', '')
        sample_row_id = record.get('Sample Row ID', '')
        trace = {}
        dag_sequence = ""

        try:
            # Sanitize and Execute
            safe_query = preprocess_user_query(query)
            dag = planner.plan_optimal_dag(safe_query)
            dag_sequence = " -> ".join(dag.nodes[node].get("operator", "") for node in nx.topological_sort(dag))
            result = executor.execute_dag(dag, safe_query)
            trace = result.get("trace", {}) if isinstance(result, dict) else {}
            new_output = result.get('final_answer', json.dumps(result))

            trace_fields = {
                "DAG Sequence": dag_sequence,
                "AOP Operator Sequence": " -> ".join(trace.get("operator_sequence", [])),
                "Retrieved Classes": json.dumps(trace.get("retrieved_classes", []), ensure_ascii=False),
                "Generated SPARQL": trace.get("generated_sparql", ""),
                "Scan Status": trace.get("scan_status", ""),
                "Scan Row Count": trace.get("scan_row_count", ""),
                "Scan Error": trace.get("scan_error", ""),
                "Scan Raw Rows": trace.get("scan_raw_rows", ""),
                "Unknown Terms": json.dumps(trace.get("unknown_terms", []), ensure_ascii=False),
                "Term Suggestions": json.dumps(trace.get("term_suggestions", {}), ensure_ascii=False),
                "Refine Reason": trace.get("refine_reason", ""),
                "Validation Is Valid": trace.get("validation_is_valid", ""),
                "Validation Reason": trace.get("validation_reason", ""),
                "Self Heal Attempts": trace.get("self_heal_attempts", 0),
                "Short Circuit Stage": trace.get("short_circuit_stage", ""),
                "Failure Stage": trace.get("failure_stage", ""),
            }

            # === LLM-ONLY EVALUATOR ===
            eval_prompt = f"""
            You are a strict grading assistant.
            Did the Pipeline output successfully answer the user's question based on the Ground Truth?

            Question: {query}
            Ground Truth: {ground_truth}
            Pipeline Output: {new_output}

            Rules:
            1. Treat the Ground Truth as the authoritative answer.
            2. If Ground Truth contains a concrete number, JSON value, category, investor ID, or name, the Pipeline Output must contain the same facts. If it says "No data found", "database error", or gives a different number such as 0, mark MISMATCH.
            3. Only mark "No data found" as MATCH when Ground Truth explicitly says no rows/no data/no business rule.
            4. If Ground Truth is JSON, all important values in the JSON must appear in the Pipeline Output. Missing values are PARTIAL or MISMATCH, not MATCH.
            5. If the Pipeline Output gives 0 but Ground Truth is a nonzero number, mark MISMATCH.
            6. For yes/no or comparison questions, the Pipeline Output must explicitly answer yes/no or include all compared facts needed to prove the answer. If it only returns an intermediate row or one side of the comparison, mark MISMATCH.
            7. If the Pipeline Output is just "Result from retrieved rows" and does not directly answer the user's question, mark MISMATCH unless those rows alone fully contain the requested final answer.
            8. Ignore superficial formatting. Check the facts, not presentation.
            9. Treat IDs with punctuation differences as equivalent when the letters and digits match. Examples: INV-001 = INV001, INV_001 = INV001, inv 001 = INV001.
            10. Treat comma-formatted and unformatted numbers as equivalent. Examples: 601,230 = 601230 and 9,192 = 9192.
            11. Ignore markdown, bold text, bullets, extra whitespace, and reasoning/thinking tags such as <reasoning>...</reasoning> or <think>...</think>.
            12. Treat minor spelling variations or obvious database label typos as equivalent when they clearly refer to the same value. Example: Coporate Bond = Corporate Bond. Do not use this rule for genuinely different categories or names.
            13. If the Ground Truth lists multiple tied correct answers and the Pipeline Output returns only one of them, mark PARTIAL, not MATCH.

            Examples:
            - Ground Truth: 1; Pipeline Output: 0 => MISMATCH.
            - Ground Truth: {{"sector": "Private Equity", "allocation_pct": 42}}; Pipeline Output: No data found => MISMATCH.
            - Ground Truth: No; Pipeline Output only shows {{"sectorName": "Private Equity"}} without the stated sector focus => MISMATCH.
            - Ground Truth: {{"investor_id": "INV-001"}}; Pipeline Output: "INV001" => MATCH.
            - Ground Truth: {{"investment_type": "Corporate Bond"}}; Pipeline Output: "Coporate Bond" => MATCH.
            - Ground Truth: {{"amount": 601230}}; Pipeline Output: "601,230" => MATCH.

            Output ONLY the word MATCH, PARTIAL, or MISMATCH.
            """

            api_logger.log_call(query, "Final_Result_Grader")
            eval_response = generalist_client.chat.completions.create(
                model=LOCAL_MODEL, messages=[{"role": "user", "content": eval_prompt}], temperature=0.0
            )
            raw_status = eval_response.choices[0].message.content.strip()
            status_match = re.search(r"\b(MATCH|PARTIAL|MISMATCH)\b", raw_status, flags=re.I)
            new_status = status_match.group(1).upper() if status_match else raw_status
            comments = "Evaluated via LLM-only final grader."

            elapsed_seconds = round(time.perf_counter() - query_start_time, 3)
            return {
                "Pipeline Version": PIPELINE_VERSION,
                "Sample Row ID": sample_row_id,
                "Question": query,
                "Ground Truth": ground_truth,
                "Old Status": old_status,
                "New Pipeline Result": new_output,
                "New Status": new_status,
                "Comparison / Comments": comments,
                "Started At": started_at,
                "Elapsed Seconds": elapsed_seconds,
                **trace_fields,
            }

        except Exception as e:
            elapsed_seconds = round(time.perf_counter() - query_start_time, 3)
            return {
                "Pipeline Version": PIPELINE_VERSION,
                "Sample Row ID": sample_row_id,
                "Question": query,
                "Ground Truth": ground_truth,
                "Old Status": old_status,
                "New Pipeline Result": f"ERROR: {str(e)}",
                "New Status": "CRASH",
                "Comparison / Comments": "Pipeline threw a fatal exception.",
                "Started At": started_at,
                "Elapsed Seconds": elapsed_seconds,
                "DAG Sequence": dag_sequence,
                "AOP Operator Sequence": " -> ".join(trace.get("operator_sequence", [])) if trace else "",
                "Retrieved Classes": json.dumps(trace.get("retrieved_classes", []), ensure_ascii=False) if trace else "[]",
                "Generated SPARQL": trace.get("generated_sparql", "") if trace else "",
                "Scan Status": trace.get("scan_status", "") if trace else "",
                "Scan Row Count": trace.get("scan_row_count", "") if trace else "",
                "Scan Error": trace.get("scan_error", "") if trace else "",
                "Scan Raw Rows": trace.get("scan_raw_rows", "") if trace else "",
                "Unknown Terms": json.dumps(trace.get("unknown_terms", []), ensure_ascii=False) if trace else "[]",
                "Term Suggestions": json.dumps(trace.get("term_suggestions", {}), ensure_ascii=False) if trace else "{}",
                "Refine Reason": trace.get("refine_reason", "") if trace else "",
                "Validation Is Valid": trace.get("validation_is_valid", "") if trace else "",
                "Validation Reason": trace.get("validation_reason", "") if trace else "",
                "Self Heal Attempts": trace.get("self_heal_attempts", 0) if trace else 0,
                "Short Circuit Stage": trace.get("short_circuit_stage", "") if trace else "",
                "Failure Stage": trace.get("failure_stage", "Exception") if trace else "Exception",
            }


    print("\n[SYSTEM] Running pipeline on failed queries. Saving incrementally...")
    output_filename = REPORT_FILE
    report_columns = [
        "Pipeline Version",
        "Sample Row ID",
        "Question",
        "Ground Truth",
        "New Pipeline Result",
        "New Status",
        "Old Status",
        "Comparison / Comments",
        "Started At",
        "Elapsed Seconds",
        "DAG Sequence",
        "AOP Operator Sequence",
        "Retrieved Classes",
        "Generated SPARQL",
        "Scan Status",
        "Scan Row Count",
        "Scan Error",
        "Scan Raw Rows",
        "Unknown Terms",
        "Term Suggestions",
        "Refine Reason",
        "Validation Is Valid",
        "Validation Reason",
        "Self Heal Attempts",
        "Short Circuit Stage",
        "Failure Stage",
    ]

    def save_report(rows):
        df_report = pd.DataFrame(rows)
        for column in report_columns:
            if column not in df_report.columns:
                df_report[column] = ""
        df_report = df_report[report_columns]
        temporary_file = f"{output_filename}.tmp"
        df_report.to_csv(temporary_file, index=False)
        os.replace(temporary_file, output_filename)

    results_list = []
    completed_row_ids = set()
    if os.path.exists(output_filename):
        try:
            existing_report = pd.read_csv(output_filename)
            if "Sample Row ID" not in existing_report.columns:
                print("[WARN] Existing report has no Sample Row ID, so it cannot safely resume duplicate questions. Starting a fresh report.")
            else:
                if "Pipeline Version" in existing_report.columns:
                    stale_mask = existing_report["Pipeline Version"].astype(str).ne(PIPELINE_VERSION)
                else:
                    stale_mask = pd.Series(True, index=existing_report.index)
                crash_mask = existing_report.get("New Status", "").astype(str).str.upper().eq("CRASH")
                retry_mask = stale_mask | crash_mask
                retry_count = int(retry_mask.sum())
                existing_report = existing_report[~retry_mask].copy()
                results_list = existing_report.to_dict(orient="records")
                completed_row_ids = set(existing_report["Sample Row ID"].astype(str))
                print(f"[SYSTEM] Resume enabled: found {len(results_list)} completed rows in {output_filename}.")
                if retry_count:
                    print(f"[SYSTEM] Retrying {retry_count} stale-version or previous CRASH rows.")
        except Exception as e:
            print(f"[WARN] Could not read existing report for resume: {e}. Starting fresh.")
            results_list = []
            completed_row_ids = set()

    pending_records = []
    for record in test_records:
        row_id = str(record.get("Sample Row ID", ""))
        if row_id in completed_row_ids:
            continue
        pending_records.append(record)
    skipped_count = len(test_records) - len(pending_records)
    if skipped_count:
        print(f"[SYSTEM] Skipping {skipped_count} already completed queries.")
    print(f"[SYSTEM] Pending queries this run: {len(pending_records)}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=TEST_MAX_WORKERS) as test_runner:
        futures = [test_runner.submit(run_single_test, rec) for rec in pending_records]

        for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
            res = future.result()
            results_list.append(res)
            print(
                f"Processed {idx}/{len(pending_records)} this run "
                f"({len(results_list)}/{len(test_records)} total window): "
                f"{res['New Status']} in {res.get('Elapsed Seconds', '')}s"
            )


            save_report(results_list)

            if idx % 10 == 0 or idx == len(pending_records):
                api_logger.save()

    if not pending_records and results_list:
        save_report(results_list)

    completed_elapsed_values = []
    for row in results_list:
        try:
            completed_elapsed_values.append(float(row.get("Elapsed Seconds", 0) or 0))
        except (TypeError, ValueError):
            pass
    total_query_generation_seconds = sum(completed_elapsed_values)
    wall_clock_seconds = time.perf_counter() - script_start_time
    avg_query_seconds = total_query_generation_seconds / len(completed_elapsed_values) if completed_elapsed_values else 0.0

    api_logger.save()
    print(f"\n[SUCCESS] Final report successfully saved to {output_filename}.")
    print(f"[TIME] Completed query rows in report: {len(results_list)}")
    print(f"[TIME] Total per-query generation time: {total_query_generation_seconds:.2f} seconds ({total_query_generation_seconds / 60:.2f} minutes)")
    print(f"[TIME] Average per-query time: {avg_query_seconds:.2f} seconds")
    print(f"[TIME] Wall-clock time for this run: {wall_clock_seconds:.2f} seconds ({wall_clock_seconds / 60:.2f} minutes)")

if __name__ == "__main__":
    main()
