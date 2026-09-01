"""Canonical shared SQL/KG pipeline orchestration entry point."""

import re
import json
import networkx as nx
from typing import Dict, Any
from openai import OpenAI as LLMClient
import os
import sqlite3
import rdflib
import concurrent.futures
import time
import threading
import datetime
import random
import multiprocessing
import queue
import socket
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from script_diff_llm.backends.kg import (
    check_fuseki_health,
    get_lightweight_table_index,
    load_rdf_knowledge_graph,
)
from script_diff_llm.backends import sql as sql_pipeline
from script_diff_llm.config.runtime import load_local_env_file, load_runtime_config
from script_diff_llm.evaluation.benchmark_io import (
    load_input_samples,
    normalize_benchmark_records,
    run_single_benchmark_record,
)
from script_diff_llm.evaluation.reporting import (
    REPORT_COLUMNS,
    compute_pending_records,
    load_resume_state,
    save_report,
)
from script_diff_llm.llm.clients import (
    build_model_client,
    supports_temperature,
)
from script_diff_llm.pipeline.dag.executor import AOPExecutor
from script_diff_llm.pipeline.dag.planner import AdvancedAOPPlanner
from script_diff_llm.pipeline.decomposition import semantic_decompose as semantic_decompose_operator
from script_diff_llm.pipeline.explanation import semantic_explain_results as semantic_explain_results_operator
from script_diff_llm.pipeline.kg_pipeline import (
    load_rdf_id_alias_map,
    pre_programmed_scan as pre_programmed_scan_operator,
    preprocess_user_query,
    semantic_generate_sparql as semantic_generate_sparql_operator,
    semantic_pre_scan_validate as semantic_pre_scan_validate_operator,
    semantic_refine as semantic_refine_operator,
    semantic_retrieve as semantic_retrieve_operator,
    strip_llm_reasoning_blocks,
)
from script_diff_llm.pipeline.operators import (
    pre_programmed_difference,
    pre_programmed_math_compute,
    pre_programmed_set_intersect,
    pre_programmed_union,
)
from script_diff_llm.pipeline.registry import build_operator_registry
from script_diff_llm.pipeline.specification import semantic_build_query_spec as semantic_build_query_spec_operator

load_local_env_file()
CONFIG = load_runtime_config()

SCRIPT_DIR = CONFIG.script_dir
SCRIPT_DIFF_ROOT = CONFIG.script_diff_root
SCRIPT_BASE_DIR = CONFIG.script_base_dir
PRIMARY_MODEL = CONFIG.primary_model
LOCAL_MODEL = CONFIG.local_model
RAG_MODEL = CONFIG.rag_model
PLANNER_MODEL = CONFIG.planner_model
QUERY_SPEC_MODEL = CONFIG.query_spec_model
REFINE_MODEL = CONFIG.refine_model
VALIDATE_MODEL = CONFIG.validate_model
EXPLAIN_MODEL = CONFIG.explain_model
SPARQL_GENERATION_MODEL = CONFIG.sparql_generation_model
LLM_GRADER_MODEL = CONFIG.llm_grader_model
DETERMINISTIC_EXPLAIN = CONFIG.deterministic_explain
PIPELINE_VERSION = CONFIG.pipeline_version
TEST_QUERY_LIMIT = CONFIG.test_query_limit
TEST_QUERY_OFFSET = CONFIG.test_query_offset
TEST_MAX_WORKERS = CONFIG.test_max_workers
SPARQL_SCAN_TIMEOUT_SECONDS = CONFIG.sparql_scan_timeout_seconds
FUSEKI_ENDPOINT = CONFIG.fuseki_endpoint
FUSEKI_SCAN_TIMEOUT_SECONDS = CONFIG.fuseki_scan_timeout_seconds
FUSEKI_METADATA_TIMEOUT_SECONDS = CONFIG.fuseki_metadata_timeout_seconds
SPARQL_SCAN_MAX_RETRIES = CONFIG.sparql_scan_max_retries
PRE_SCAN_VALIDATE_MAX_RETRIES = CONFIG.pre_scan_validate_max_retries
POST_SCAN_VALIDATE_MAX_RETRIES = CONFIG.post_scan_validate_max_retries
SCAN_REFINE_MAX_RETRIES = CONFIG.scan_refine_max_retries
SPARQL_SCAN_PROCESS_START_METHOD = CONFIG.sparql_scan_process_start_method
BASE_DIR = CONFIG.base_dir
OUTPUT_DIR = CONFIG.output_dir
SCHEMA_FILE = CONFIG.schema_file
INSTANCE_FILE = CONFIG.instance_file
INPUT_SAMPLE_FILE = CONFIG.input_sample_file
INPUT_SAMPLE_SHEET = CONFIG.input_sample_sheet
DEFAULT_SQLITE_DB_PATH = CONFIG.default_sqlite_db_path
SQLITE_DB_PATH = CONFIG.sqlite_db_path

print(f"[SYSTEM] SQLite DB: {SQLITE_DB_PATH}")
print(f"[SYSTEM] SQLite DB exists: {os.path.exists(SQLITE_DB_PATH)}")
REPORT_FILE = CONFIG.report_file
ALIAS_MAP_FILE = CONFIG.alias_map_file
RDF_ID_ALIAS_MAP = {}


def load_sqlite_schema(db_path: str) -> Dict[str, Any]:
    """Load the physical SQLite schema used by SQL DAG nodes."""
    if not db_path:
        raise ValueError("SQLITE_DB_PATH is empty; SQL nodes require a real SQLite database path.")
    if db_path == ":memory:":
        raise ValueError("SQLITE_DB_PATH resolved to :memory:; SQL nodes require the physical wealth database.")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"SQLite database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
        table_names = [row[0] for row in cursor.fetchall()]
        schema: Dict[str, Any] = {}
        for table_name in table_names:
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns = []
            for cid, name, col_type, notnull, default_value, pk in cursor.fetchall():
                columns.append({
                    "name": name,
                    "type": col_type or "",
                    "notnull": bool(notnull),
                    "default": default_value,
                    "pk": bool(pk),
                    "ordinal": cid,
                })
            schema[table_name] = {
                "table_name": table_name,
                "columns": columns,
                "column_names": [column["name"] for column in columns],
            }
        print(f"[SQL SCHEMA] Loaded {len(schema)} tables from {db_path}")
        return schema
    finally:
        conn.close()

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)

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


def setup_rdf_graph(instance_file: str) -> Any:
    """Prepare lightweight local RDF helpers; the full instance graph lives in Fuseki."""
    print("[SYSTEM] Using Apache Jena Fuseki as the RDF instance graph. Skipping rdflib instance load.")
    global RDF_ID_ALIAS_MAP
    RDF_ID_ALIAS_MAP = load_rdf_id_alias_map(ALIAS_MAP_FILE)
    if RDF_ID_ALIAS_MAP:
        print(f"[SYSTEM] Loaded RDF ID alias map with {len(RDF_ID_ALIAS_MAP)} normalized keys.")
    else:
        print(f"[WARN] RDF ID alias map not found or empty: {ALIAS_MAP_FILE}")
    return None

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

# After the data is retrieved, the natural language query and the final output is given as input to the LLM agent , which checks for the Semantic Alignment. It checks for missing or wrong columns names, ignored constrained,etc.
# Gives boolean output
#Can be improved further after providing a set of basic laws to the LLM for validation

def empty_answer_can_be_valid(query: str, query_spec: Dict[str, Any]) -> bool:
    q = normalize_for_compare(query)
    qtype = str(query_spec.get("query_type", "")).lower()

    list_like = any(phrase in q for phrase in [
        "which", "show", "list", "identify", "find", "investors who",
        "holdings that", "records where"
    ])
    numeric_required = any(phrase in q for phrase in [
        "count", "how many", "average", "avg", "sum", "total",
        "highest", "lowest", "maximum", "minimum"
    ])

    return list_like and not numeric_required and qtype in {
        "set_logic", "point_lookup", "ranking", "comparative", "aggregation"
    }


def is_quota_exhaustion_error(error: Any) -> bool:
    text = str(error or "").lower()
    return (
        "insufficient_quota" in text
        or "exceeded your current quota" in text
        or ("error code: 429" in text and "quota" in text)
    )


#|| Cahnged vaidation so that it not only checks for ewmptiness, but also the column names, cluases, etc.
def semantic_validate(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    print(f"\n[DEBUG] --- Executing semantic_validate ---")
    data = inputs.get('data', [])
    print(f"[DEBUG] Validating {len(data)} rows for query.")
    if not data:
        query_spec = inputs.get("query_spec", {})
        if empty_answer_can_be_valid(inputs.get("query", ""), query_spec):
            val_dict = {
                "is_valid": True,
                "reason": "Empty result is valid for this filtered/list-style query.",
            }
        else:
            val_dict = {"is_valid": False, "reason": "Data Results are empty. Query failed to retrieve necessary facts."}
        print(f"[DEBUG] Output Validation Result: {val_dict}")
        return {"validation": val_dict, "data": data}

    # Extract the column names (keys) from the first row of data to help the LLM verify fields
    returned_fields = list(data[0].keys()) if data and isinstance(data, list) else []

    # Cap the data sample at 10 rows to prevent blowing up the LLM context window during validation
    data_sample = data[:10] if isinstance(data, list) else data
    generated_sparql = inputs.get("sparql", "")
    query_spec = inputs.get("query_spec", {})

    prompt = f"""
    The next operator is Validate.
    Assess if the following data results successfully answer the user's original query.
    Use the generated SPARQL as part of the evidence. Do not judge only by row count.

    User Query: "{inputs.get('query')}"
    Query Spec:
    {json.dumps(query_spec, indent=2)}
    Generated SPARQL:
    {generated_sparql}
    Returned Column Names: {returned_fields}
    Data Results (Sample): {json.dumps(data_sample, indent=2)}

    CRITICAL RULE 1 (EMPTY DATA):
    Empty data is handled before this prompt. For the current validation, inspect only the non-empty returned data sample.

    CRITICAL RULE 2 (SCHEMA & FIELD MATCH - FIX E-02): Beyond checking if data is non-empty, you MUST verify:
    1. Do the returned column names logically match what the query asked for? (e.g., if asking for "sector and allocation", both fields MUST be present).
    2. If the query asked for a specific investor/entity filter, does the data reflect only that entity? Or did it return data for everyone?
    3. If the query asked for an aggregation (MAX/MIN/SUM/AVG/COUNT), did the SPARQL and returned fields reflect the requested aggregate, or did it return raw unaggregated rows?
    4. If the query asks for a top/bottom, highest/lowest, maximum/minimum, largest/smallest, best/worst, or ranking-style result, inspect the SPARQL ranking logic.
    5. If Query Spec has output_schema, do the returned column names satisfy that expected answer shape?
    6. For entity/list questions, verify the SPARQL anchors the returned entity with `rdf:type` for the requested base entity or required class. If it only uses an ID-like literal property, mark invalid because different classes can share identifier literals.
    7. For missing-required-field questions, rows with null/None values in requested display fields are a strong sign the query matched the wrong class; mark invalid unless the user explicitly asked for those display fields to be missing.

    CRITICAL RULE 3 (RANKED AGGREGATION): For superlative or ranking questions, a single returned row can be fully valid when the SPARQL intentionally reduces the result:
    - GROUP BY plus an aggregate expression plus ORDER BY plus LIMIT 1 is a valid way to return one top or bottom group.
    - ORDER BY ASC with LIMIT 1 supports lowest/minimum/smallest/bottom questions.
    - ORDER BY DESC with LIMIT 1 supports highest/maximum/largest/top questions.
    - Do NOT require all groups to be returned when ORDER BY and LIMIT already select the final ranked answer.

    If ANY of these logic checks fail, you MUST output "is_valid": false and provide specific, detailed feedback in the "reason" field about which columns/aggregations are wrong.

    Output strictly a JSON object: {{"is_valid": true/false, "reason": "why"}}
    """

    api_logger.log_call(inputs.get('query'), "Validate")
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if supports_temperature(model):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

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

def _run_kg_scan(inputs: Dict[str, Any], rdf_graph: rdflib.Graph, known_terms_cache: Dict[str, Any]) -> Dict[str, Any]:
    result, known_terms_cache["value"] = pre_programmed_scan_operator(
        inputs,
        rdf_graph,
        rdf_id_alias_map=RDF_ID_ALIAS_MAP,
        known_terms_cache=known_terms_cache.get("value"),
        fuseki_endpoint=FUSEKI_ENDPOINT,
        fuseki_scan_timeout_seconds=FUSEKI_SCAN_TIMEOUT_SECONDS,
        fuseki_metadata_timeout_seconds=FUSEKI_METADATA_TIMEOUT_SECONDS,
        logger=print,
    )
    return result

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

def main():
    print("\n" + "="*50)
    print("INITIALIZING AOP PIPELINE")
    print("="*50)

    #CONFIGURATION & API SETUP
    print("[SYSTEM] Scan backend: Apache Jena Fuseki")
    print(f"[SYSTEM] Fuseki endpoint: {FUSEKI_ENDPOINT}")
    print(f"[SYSTEM] Fuseki scan timeout: {FUSEKI_SCAN_TIMEOUT_SECONDS:g} seconds")
    print(f"[SYSTEM] Experiment config: {CONFIG.experiment_config_path}")
    print(f"[SYSTEM] Model config: {CONFIG.model_config_path}")
    print(f"[SYSTEM] SQL asset: {CONFIG.sql_asset_file}")
    check_fuseki_health()

    primary_client = build_model_client(
        provider=CONFIG.model_provider,
        api_key_envs=CONFIG.api_key_envs,
        base_url_env=CONFIG.base_url_env,
        region_envs=CONFIG.region_envs,
    )
    retrieve_client = primary_client
    planner_client = primary_client
    query_spec_client = primary_client
    sparql_generation_client = primary_client
    validate_client = primary_client
    refine_client = primary_client
    explain_client = primary_client
    print(f"[SYSTEM] Model provider: {CONFIG.model_provider}")
    print(f"[SYSTEM] Model endpoint env: {CONFIG.base_url_env}")
    print(f"[SYSTEM] Primary model: {PRIMARY_MODEL}")
    print(f"[SYSTEM] RAG/Retrieve model: {RAG_MODEL}")
    print(f"[SYSTEM] Planner model: {PLANNER_MODEL}")
    print(f"[SYSTEM] Query_Spec model: {QUERY_SPEC_MODEL}")
    print(f"[SYSTEM] Refine model: {REFINE_MODEL}")
    print(f"[SYSTEM] Generate model: {SPARQL_GENERATION_MODEL}")
    print(f"[SYSTEM] Validate model: {VALIDATE_MODEL}")
    print(f"[SYSTEM] Explain model: {EXPLAIN_MODEL}")
    print("[SYSTEM] Grading: disabled in pipeline runner; use separate grade_*.py")
    print(f"[SYSTEM] DAG planner mode: {os.getenv('DAG_PLANNER_MODE', 'multi_candidate')}")
    print(f"[SYSTEM] Report file: {REPORT_FILE}")
    script_start_time = time.perf_counter()



    # LOAD RDF KNOWLEDGE GRAPH
    schema_file = SCHEMA_FILE
    instance_file = INSTANCE_FILE

    kg_metadata = load_rdf_knowledge_graph(
        schema_file,
        FUSEKI_ENDPOINT,
        FUSEKI_METADATA_TIMEOUT_SECONDS,
    )
    rdf_graph = setup_rdf_graph(instance_file)

    if not kg_metadata:
        print("[!] ERROR: Could not load Knowledge Graph. Please check RDF files.")
        return

    sql_schema = load_sqlite_schema(SQLITE_DB_PATH)

    # Create the token-saving index
    lightweight_index = get_lightweight_table_index(kg_metadata)
    known_terms_cache: dict[str, set[str] | None] = {"value": None}

    operator_registry = build_operator_registry(
        lightweight_index=lightweight_index,
        kg_metadata=kg_metadata,
        rdf_graph=rdf_graph,
        retrieve_client=retrieve_client,
        query_spec_client=query_spec_client,
        sparql_generation_client=sparql_generation_client,
        validate_client=validate_client,
        refine_client=refine_client,
        explain_client=explain_client,
        rag_model=RAG_MODEL,
        query_spec_model=QUERY_SPEC_MODEL,
        sparql_generation_model=SPARQL_GENERATION_MODEL,
        validate_model=VALIDATE_MODEL,
        refine_model=REFINE_MODEL,
        explain_model=EXPLAIN_MODEL,
        semantic_retrieve=lambda inputs, client, model: semantic_retrieve_operator(
            inputs,
            client,
            model,
            parse_json_fn=parse_llm_json,
            log_call_fn=api_logger.log_call,
        ),
        semantic_build_query_spec=lambda inputs, client, model: semantic_build_query_spec_operator(
            inputs,
            client,
            model,
            parse_json_fn=parse_llm_json,
            normalize_for_compare_fn=normalize_for_compare,
            log_call_fn=api_logger.log_call,
        ),
        semantic_generate_sparql=lambda inputs, client, model: semantic_generate_sparql_operator(
            inputs,
            client,
            model,
            rdf_id_alias_map=RDF_ID_ALIAS_MAP,
            log_call_fn=api_logger.log_call,
        ),
        semantic_pre_scan_validate=lambda inputs, client, model: semantic_pre_scan_validate_operator(
            inputs,
            client,
            model,
            parse_json_fn=parse_llm_json,
            log_call_fn=api_logger.log_call,
        ),
        semantic_refine=lambda inputs, client, model: semantic_refine_operator(
            inputs,
            client,
            model,
            rdf_id_alias_map=RDF_ID_ALIAS_MAP,
            log_call_fn=api_logger.log_call,
            supports_temperature_fn=supports_temperature,
        ),
        pre_programmed_scan=lambda inputs, rdf_graph: _run_kg_scan(
            inputs,
            rdf_graph,
            known_terms_cache,
        ),
        semantic_explain_results=lambda inputs, client, model: semantic_explain_results_operator(
            inputs,
            client,
            model,
            deterministic_explain=DETERMINISTIC_EXPLAIN,
            log_call_fn=api_logger.log_call,
            supports_temperature_fn=supports_temperature,
        ),
        pre_programmed_math_compute=pre_programmed_math_compute,
        pre_programmed_set_intersect=pre_programmed_set_intersect,
        pre_programmed_union=pre_programmed_union,
        pre_programmed_difference=pre_programmed_difference,
    )

    planner = AdvancedAOPPlanner(
        planner_client,
        operator_registry,
        decompose_fn=lambda inputs, client, model: semantic_decompose_operator(
            inputs,
            client,
            model,
            parse_json_fn=parse_llm_json,
        ),
        model=PLANNER_MODEL,
    )
    print(f"[DEBUG] SQLITE_DB_PATH = {SQLITE_DB_PATH}")
    print(f"[DEBUG] DB exists = {os.path.exists(SQLITE_DB_PATH)}")
    print(f"[DEBUG] DB absolute = {os.path.abspath(SQLITE_DB_PATH)}")
    executor = AOPExecutor(
        operator_registry=operator_registry,
        rdf_graph=rdf_graph,
        llm_client=primary_client,
        kg_metadata=kg_metadata,
        db_path=SQLITE_DB_PATH,
        sql_schema=sql_schema,
        pre_scan_validate_max_retries=PRE_SCAN_VALIDATE_MAX_RETRIES,
        post_scan_validate_max_retries=POST_SCAN_VALIDATE_MAX_RETRIES,
        scan_refine_max_retries=SCAN_REFINE_MAX_RETRIES,
    )



# === 1. LOAD AND FILTER FAILED QUERIES ===

    # Updated to point to your new Excel file
    sample_file = INPUT_SAMPLE_FILE

    try:
        print(f"\n[SYSTEM] Loading {sample_file}...")

        df_all = load_input_samples(sample_file, INPUT_SAMPLE_SHEET)
        test_records, benchmark_mode = normalize_benchmark_records(
            df_all,
            offset=TEST_QUERY_OFFSET,
            limit=TEST_QUERY_LIMIT,
        )
        print(f"[SYSTEM] Query window offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT}.")
        if benchmark_mode == "new_benchmark":
            print(f"[SYSTEM] Successfully loaded {len(test_records)} benchmark queries from the new dataset.")
        else:
            print(f"[SYSTEM] Successfully loaded {len(test_records)} queries.")

    except Exception as e:
        print(f"\n[!] ERROR loading Excel file: {e}")
        return

    print("\n[SYSTEM] Running raw pipeline. Saving incrementally...")
    output_filename = REPORT_FILE
    report_columns = REPORT_COLUMNS
    results_list = []
    completed_row_ids = set()
    if os.path.exists(output_filename):
        try:
            resume_state = load_resume_state(output_filename, PIPELINE_VERSION)
            if not resume_state.resume_enabled:
                print("[WARN] Existing report has no Sample Row ID, so it cannot safely resume duplicate questions. Starting a fresh report.")
            else:
                results_list = resume_state.results_list
                completed_row_ids = resume_state.completed_row_ids
                print(f"[SYSTEM] Resume enabled: found {len(results_list)} completed rows in {output_filename}.")
                if resume_state.retry_count:
                    print(f"[SYSTEM] Retrying {resume_state.retry_count} stale-version, previous CRASH, or quota-exhausted rows.")
        except Exception as e:
            print(f"[WARN] Could not read existing report for resume: {e}. Starting fresh.")
            results_list = []
            completed_row_ids = set()

    pending_records, skipped_count = compute_pending_records(test_records, completed_row_ids)
    if skipped_count:
        print(f"[SYSTEM] Skipping {skipped_count} already completed queries.")
    print(f"[SYSTEM] Pending queries this run: {len(pending_records)}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=TEST_MAX_WORKERS) as test_runner:
        futures = [
            test_runner.submit(
                run_single_benchmark_record,
                rec,
                preprocess_user_query=lambda query: preprocess_user_query(query, RDF_ID_ALIAS_MAP),
                planner=planner,
                executor=executor,
                pipeline_version=PIPELINE_VERSION,
                is_quota_exhaustion_error=is_quota_exhaustion_error,
            )
            for rec in pending_records
        ]

        for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
            res = future.result()
            if str(res.get("New Status", "")).upper() == "QUOTA_EXHAUSTED":
                print("[SYSTEM] OpenAI quota exhausted. Cancelling unscheduled work and preserving remaining rows for resume.")
                for pending_future in futures:
                    pending_future.cancel()
                break
            results_list.append(res)
            print(
                f"Processed {idx}/{len(pending_records)} this run "
                f"({len(results_list)}/{len(test_records)} total window): "
                f"{res['New Status']} in {res.get('Elapsed Seconds', '')}s"
            )


            save_report(results_list, output_filename, report_columns)

            if idx % 10 == 0 or idx == len(pending_records):
                api_logger.save()

    if not pending_records and results_list:
        save_report(results_list, output_filename, report_columns)

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
