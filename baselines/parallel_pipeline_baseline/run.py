"""Three-copy parallel Text-to-SPARQL ensemble baseline with inline grading.

For every benchmark question, each round runs three independent branches:

    Generate SPARQL -> Execute on Fuseki -> Grade against ground truth

The aggregator compares the branch result sets.  If a strict majority agrees,
that result is returned.  Otherwise, the complete three-branch round is retried.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import rdflib
from openai import OpenAI

from env import BASE_ENV, load_base_pipeline_env


load_base_pipeline_env()

HERE = Path(__file__).resolve().parent
BASELINES = HERE.parent
FINANCE = BASELINES.parent
SCRIPT_DIFF_ROOT = FINANCE / "script_diff_llm"

DOMAIN_INTRO_FILE = Path(os.getenv("DOMAIN_INTRO_FILE", BASELINES / "domain_intro.prompt"))
BUSINESS_RULES_FILE = Path(os.getenv("BUSINESS_RULES_FILE", BASELINES / "phase0_business_rules.md"))


def load_prompt_reference_context() -> str:
    sections = []
    for title, path in (
        ("Domain introduction", DOMAIN_INTRO_FILE),
        ("Phase 0 business rules", BUSINESS_RULES_FILE),
    ):
        sections.append(f"{title}:\n{path.read_text(encoding='utf-8').strip()}")
    return "\n\n".join(sections)


PROMPT_REFERENCE_CONTEXT = load_prompt_reference_context()

VERSION = "parallel-text-to-sparql-ensemble-v3.1"
DEFAULT_TARGET_MODEL = os.getenv("TARGET_MODEL", "qwen.qwen3-235b-a22b-2507")
DEFAULT_GRADER_MODEL = (
    os.getenv("INLINE_GRADER_MODEL")
    or os.getenv("GRADER_MODEL")
    or "gpt-5.6-terra"
)
DEFAULT_SCHEMA = SCRIPT_DIFF_ROOT / "kg" / "wealth_management_diverse_schema.ttl"
DEFAULT_BENCHMARK = (
    SCRIPT_DIFF_ROOT / "dataset" / "verification_results_v2_sql_correct_train.csv"
)
DEFAULT_FULL_GROUND_TRUTH = (
    FINANCE / "dataset_new"
    / "wealth_management_all_benchmark_questions_combined_shuffled_seed4043113952.csv"
)
DEFAULT_REPORT = HERE / "output" / "parallel_pipeline_v3_1_raw_graded.csv"
DEFAULT_FUSEKI_ENDPOINT = os.getenv(
    "FUSEKI_ENDPOINT", "http://127.0.0.1:3030/wealth/query"
)

FINAL_VERDICTS = {"MATCH", "PARTIAL", "MISMATCH", "OTHER"}
GRADER_FAILURE_STATUSES = {
    "MODEL_NOT_FOUND",
    "QUOTA_EXHAUSTED",
    "RATE_LIMIT_ERROR",
    "API_AUTH_ERROR",
    "TOKEN_OUTPUT_ERROR",
    "GRADER_API_ERROR",
}
FATAL_API_STATUSES = {
    "MODEL_NOT_FOUND",
    "QUOTA_EXHAUSTED",
    "RATE_LIMIT_ERROR",
    "API_AUTH_ERROR",
}

_csv_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_csv_limit)
        break
    except OverflowError:
        _csv_limit //= 10


REPORT_COLUMNS = [
    "Pipeline Version",
    "Run Config",
    "Sample Row ID",
    "Question",
    "Ground Truth",
    "Difficulty",
    "Category",
    "Query Type",
    "Source CSV",
    "Pipeline Status",
    "New Status",
    "Comparison / Comments",
    "Ensemble Result",
    "Processed Rows",
    "Consensus Achieved",
    "Consensus Size",
    "Winning Copies",
    "Rounds Used",
    "Retry Rounds Used",
    "Grade Verdict",
    "Grade Reason",
    "Grade Evidence",
    "Target Model",
    "Grader Model",
    "Generation Input Tokens",
    "Generation Output Tokens",
    "Grader Input Tokens",
    "Grader Output Tokens",
    "Final SPARQL",
    "Final Scan Row Count",
    "All Rounds Log",
    "Started At",
    "Elapsed Seconds",
]


class APILogger:
    """Thread-safe per-question API call counter."""

    def __init__(self, output_dir: Path):
        self._lock = threading.Lock()
        self._calls: dict[str, dict[str, Any]] = {}
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = output_dir / f"api_usage_log_{timestamp}.json"

    def log(self, question: str, operation: str) -> None:
        with self._lock:
            item = self._calls.setdefault(question or "Unknown_Query", {"total_calls": 0, "functions": {}})
            item["total_calls"] += 1
            item["functions"][operation] = item["functions"].get(operation, 0) + 1

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(self._calls, indent=2), encoding="utf-8")
            temporary.replace(self.path)


@dataclass
class GradeResult:
    verdict: str
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class BranchResult:
    copy_id: int
    round_number: int
    status: str
    sparql: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    result_fingerprint: str = ""
    grade: GradeResult = field(default_factory=lambda: GradeResult("OTHER"))
    error: str = ""
    generation_input_tokens: int = 0
    generation_output_tokens: int = 0
    elapsed_seconds: float = 0.0
    execution_attempts: list[dict[str, Any]] = field(default_factory=list)


def make_target_client(model: str) -> OpenAI:
    """Route GPT-OSS through Bedrock and Qwen/other target models through Mantle."""
    provider = os.getenv("TARGET_PROVIDER", "").strip().lower()
    if provider == "bedrock" or model.lower().startswith("openai.gpt-oss"):
        return make_bedrock_client()
    key = (
        os.getenv("BEDROCK_MANTLE_API_KEY")
        or os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not key:
        raise RuntimeError(f"A Bedrock API key is missing from the environment and {BASE_ENV}")
    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_MANTLE_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError("Set BEDROCK_REGION or BEDROCK_MANTLE_BASE_URL.")
        base_url = f"https://bedrock-mantle.{region}.api.aws/v1"
    return OpenAI(api_key=key, base_url=base_url, timeout=180, max_retries=1)


def make_bedrock_client() -> OpenAI:
    key = (
        os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("AWS_Bedrock_API_gpt_oss_120b")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not key:
        raise RuntimeError(f"A Bedrock API key is missing from the environment and {BASE_ENV}")
    region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    base_url = os.getenv("BEDROCK_BASE_URL")
    if not base_url:
        if not region:
            raise RuntimeError("Set BEDROCK_REGION or BEDROCK_BASE_URL.")
        base_url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1"
    return OpenAI(api_key=key, base_url=base_url, timeout=180, max_retries=1)


def make_grader_client(model: str) -> OpenAI:
    if model.lower().startswith(("gpt-4", "gpt-5")):
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(f"OPENAI_API_KEY is missing from the environment and {BASE_ENV}")
        options: dict[str, Any] = {"api_key": key, "timeout": 180, "max_retries": 2}
        if os.getenv("OPENAI_BASE_URL"):
            options["base_url"] = os.environ["OPENAI_BASE_URL"]
        return OpenAI(**options)
    return make_bedrock_client()


def local_name(uri: Any) -> str:
    text = str(uri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rstrip("/").rsplit("/", 1)[-1]


def normalize_schema_attribute_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if any(marker in normalized for marker in ("decimal", "integer", "float", "double", "numeric", "number")):
        return "numeric"
    if any(marker in normalized for marker in ("string", "text", "date", "categorical")):
        return "categorical_string"
    return "unknown"


def schema_datatype_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def parse_fuseki_sparql_json(payload: dict[str, Any]) -> list[dict[str, str]]:
    if "boolean" in payload:
        return [{"boolean": str(bool(payload.get("boolean"))).lower()}]
    variables = payload.get("head", {}).get("vars", [])
    rows = []
    for binding in payload.get("results", {}).get("bindings", []):
        rows.append({
            str(variable): str(binding.get(variable, {}).get("value", ""))
            for variable in variables
        })
    return rows


def execute_sparql(
    sparql: str,
    endpoint: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not sparql.strip():
        return {"status": "error", "data": [], "row_count": 0, "error_message": "Empty SPARQL query."}
    try:
        body = urllib.parse.urlencode({"query": sparql}).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        rows = parse_fuseki_sparql_json(payload)
        return {"status": "success", "data": rows, "row_count": len(rows)}
    except socket.timeout:
        message = f"Fuseki execution timed out after {timeout_seconds:g} seconds."
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = f"Fuseki HTTP {exc.code}: {detail[:500] or exc}"
    except urllib.error.URLError as exc:
        message = f"Fuseki connection error: {exc.reason}"
    except json.JSONDecodeError as exc:
        message = f"Fuseki returned non-JSON results: {exc}"
    except Exception as exc:  # noqa: BLE001 - report branch failures without killing peers
        message = f"{type(exc).__name__}: {exc}"
    return {"status": "error", "data": [], "row_count": 0, "error_message": message}


def check_fuseki(endpoint: str) -> None:
    result = execute_sparql("ASK { ?s ?p ?o . }", endpoint, 10.0)
    if result["status"] != "success":
        raise RuntimeError(f"Fuseki is not reachable at {endpoint}: {result.get('error_message')}")


def load_schema(schema_path: Path, endpoint: str, metadata_timeout: float) -> dict[str, Any]:
    graph = rdflib.Graph()
    graph.parse(schema_path, format="turtle")
    datatype_names = {
        rdflib.URIRef("https://wealth.example.org/ontology/attributeName"),
        rdflib.URIRef("https://wealth.example.org/ontology/derivedName"),
    }
    attribute_type = rdflib.URIRef("https://wealth.example.org/ontology/attributeType")
    datatype_by_property: dict[str, str] = {}
    for attribute, _, raw_type in graph.triples((None, attribute_type, None)):
        datatype = normalize_schema_attribute_type(raw_type)
        if datatype == "unknown":
            continue
        for name_predicate in datatype_names:
            name = graph.value(attribute, name_predicate)
            if name is not None:
                datatype_by_property[schema_datatype_key(name)] = datatype

    metadata: dict[str, Any] = {}
    for class_uri, _, _ in graph.triples((None, rdflib.RDF.type, rdflib.OWL.Class)):
        class_name = local_name(class_uri)
        if "__" not in class_name:
            metadata[class_name] = {"columns": {}, "name": str(graph.value(class_uri, rdflib.RDFS.label) or class_name)}

    metadata_query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT DISTINCT ?class ?p ?datatype ?targetClass WHERE {
  ?s rdf:type ?class . ?s ?p ?o .
  FILTER(STRSTARTS(STR(?class), "https://wealth.example.org/ontology/"))
  FILTER(?p != rdf:type)
  OPTIONAL { FILTER(isLiteral(?o)) BIND(DATATYPE(?o) AS ?datatype) }
  OPTIONAL {
    FILTER(isIRI(?o)) ?o rdf:type ?targetClass .
    FILTER(STRSTARTS(STR(?targetClass), "https://wealth.example.org/ontology/"))
  }
}
"""
    dynamic = execute_sparql(metadata_query, endpoint, metadata_timeout)
    if dynamic["status"] != "success":
        raise RuntimeError(f"Could not read dynamic schema from Fuseki: {dynamic.get('error_message')}")
    for row in dynamic["data"]:
        class_name = local_name(row.get("class", ""))
        property_uri = str(row.get("p", ""))
        property_name = schema_term(property_uri)
        if not class_name or not property_name:
            continue
        entry = metadata.setdefault(class_name, {"columns": {}, "name": class_name})
        if row.get("targetClass"):
            datatype = f"object_reference -> {local_name(row['targetClass'])}"
        else:
            raw_datatype = str(row.get("datatype", "")).lower()
            datatype = datatype_by_property.get(schema_datatype_key(local_name(property_uri)))
            if not datatype:
                datatype = "numeric" if any(value in raw_datatype for value in ("decimal", "integer", "float", "double")) else "categorical_string"
        entry["columns"][property_name] = datatype
    return metadata


def schema_term(uri: str) -> str:
    for prefix, namespace in (
        ("wm", "https://wealth.example.org/ontology/"),
        ("rdfs", "http://www.w3.org/2000/01/rdf-schema#"),
        ("schema1", "http://schema.org/"),
    ):
        if uri.startswith(namespace):
            return prefix + ":" + uri[len(namespace):]
    return "<" + uri + ">"


def build_schema_text(metadata: dict[str, Any]) -> str:
    lines: list[str] = []
    for class_name in sorted(metadata):
        columns = metadata[class_name].get("columns", {})
        lines.append(f"Class: wm:{class_name}")
        for property_name in sorted(columns):
            lines.append(f"  - {property_name} ({columns[property_name]})")
        lines.append("")
    return "\n".join(lines)


def validate_generated_sparql(sparql: str, schema_text: str) -> None:
    """Parse locally and reject unknown ontology terms before contacting Fuseki."""
    from rdflib.plugins.sparql.parser import parseQuery
    from rdflib.plugins.sparql.parserutils import CompValue
    from pyparsing import ParseResults

    parsed = parseQuery(sparql)
    prefixes = {str(p.prefix): str(p.iri) for p in parsed[0] if p.name == "PrefixDecl"}
    allowed = set(re.findall(r"\bwm:([A-Za-z_][\w-]*)", schema_text))
    unknown = set()

    def inspect(node):
        if isinstance(node, CompValue):
            if node.name == "pname":
                iri = prefixes.get(str(node.prefix), "") + str(node.localname)
                check_iri(iri)
            for value in node.values():
                inspect(value)
        elif isinstance(node, (list, tuple, ParseResults)):
            for value in node:
                inspect(value)
        elif isinstance(node, rdflib.URIRef):
            check_iri(str(node))

    def check_iri(iri):
        namespace = "https://wealth.example.org/ontology/"
        if iri.startswith(namespace) and iri[len(namespace):] not in allowed:
            unknown.add(iri[len(namespace):])

    inspect(parsed[1])
    if unknown:
        raise ValueError("Unknown schema terms: " + ", ".join(sorted(unknown)))

    # Check property ownership only where the same basic graph pattern explicitly
    # types the subject. Do not infer types across OPTIONAL or subquery scopes.
    from rdflib.plugins.sparql.algebra import translateQuery
    allowed_properties: dict[str, set[str]] = {}
    current = None
    for line in schema_text.splitlines():
        if line.startswith("Class: "):
            current = line[7:].strip()
            allowed_properties[current] = set()
        elif current and line.strip().startswith("- "):
            allowed_properties[current].add(line.strip()[2:].split(" (", 1)[0])

    def check_patterns(node):
        if isinstance(node, CompValue):
            if node.name == "BGP":
                triples = node["triples"]
                for subject, predicate, cls in triples:
                    if predicate != rdflib.RDF.type or not isinstance(cls, rdflib.URIRef):
                        continue
                    properties = allowed_properties.get(schema_term(str(cls)))
                    if properties is None:
                        continue
                    for s, p, _ in triples:
                        if s == subject and isinstance(p, rdflib.URIRef) and p != rdflib.RDF.type:
                            if schema_term(str(p)) not in properties:
                                raise ValueError(f"Property {schema_term(str(p))} is not listed for {schema_term(str(cls))}")
            for value in node.values():
                check_patterns(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                check_patterns(value)

    check_patterns(translateQuery(parsed).algebra)


def strip_reasoning_and_extract_sparql(raw: str) -> str:
    text = re.sub(r"(?is)<(?:reasoning|think)>.*?</(?:reasoning|think)>", "", raw or "").strip()
    blocks = re.findall(r"```(?:sparql)?\s*(.*?)```", text, flags=re.I | re.S)
    text = (blocks[-1] if blocks else text).strip()
    start = re.search(r"(?im)^\s*(?:PREFIX|SELECT|ASK)\b", text)
    return text[start.start():].strip() if start else text


def canonicalize_sparql_prefixes(sparql: str) -> str:
    """Install the graph's canonical namespaces even when a model omits/mangles them."""
    prefixes = {
        "wm": "https://wealth.example.org/ontology/",
        "kg": "https://wealth.example.org/kg/",
        "wmmeta": "https://wealth.example.org/metadata/",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "schema1": "http://schema.org/",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }
    normalized = sparql.strip()
    declarations: list[str] = []
    for alias, iri in prefixes.items():
        declaration = f"PREFIX {alias}: <{iri}>"
        pattern = rf"(?im)^\s*PREFIX\s+{re.escape(alias)}\s*:\s*<[^>]*>\s*$"
        if re.search(pattern, normalized):
            normalized = re.sub(pattern, declaration, normalized)
        else:
            declarations.append(declaration)
    return "\n".join(declarations + [normalized]).strip()


def generate_sparql(
    client: OpenAI,
    model: str,
    question: str,
    schema_text: str,
    copy_id: int,
    round_number: int,
    retry_feedback: str,
    temperature: float,
    api_logger: APILogger,
) -> tuple[str, int, int]:
    prompt = f"""Reference context:
{PROMPT_REFERENCE_CONTEXT}

RDF schema:
{schema_text}

Question:
{question}

Return only the SPARQL query. Do not include reasoning, explanations, markdown,
comments, or prose.
""".strip()
    request: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = temperature
    api_logger.log(question, f"Round_{round_number}_Copy_{copy_id}_Generate")
    response = client.chat.completions.create(**request)
    usage = getattr(response, "usage", None)
    return (
        canonicalize_sparql_prefixes(
            strip_reasoning_and_extract_sparql(response.choices[0].message.content or "")
        ),
        int(getattr(usage, "prompt_tokens", 0) or 0),
        int(getattr(usage, "completion_tokens", 0) or 0),
    )


def normalize_consensus_value(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NULL", "NONE", "NAN"}:
        return None
    try:
        number = Decimal(text)
        if number.is_finite():
            normalized = format(number.normalize(), "f")
            return "0" if normalized in {"-0", "-0.0"} else normalized
    except (InvalidOperation, ValueError):
        pass
    return re.sub(r"\s+", " ", text).casefold()


def question_requires_order(question: str) -> bool:
    """Conservatively preserve order when the question requests ranking or a sequence."""
    return bool(re.search(
        r"\b(top|bottom|highest|lowest|greatest|least|first|last|latest|earliest|"
        r"rank(?:ed|ing)?|order(?:ed)?|sort(?:ed)?|ascending|descending|chronological)\b",
        question, re.IGNORECASE,
    ))


def result_fingerprint(rows: list[dict[str, Any]], *, ordered: bool = False) -> str:
    """Retain case-sensitive column identities, duplicates, and requested row order."""
    normalized_rows = []
    for row in rows:
        normalized_rows.append(json.dumps(
            {str(key): normalize_consensus_value(value) for key, value in sorted(row.items())},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ))
    payload = json.dumps(normalized_rows if ordered else sorted(normalized_rows), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_for_grading(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_for_grading(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_for_grading(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.upper() in {"NULL", "NONE", "NAN"}:
            return None
        # Fuseki values arrive as lexical strings. Without datatype information,
        # converting them can erase leading zeros in IDs or round decimal values.
        # The grading rubric already accepts numeric strings as numbers.
    return value


def serialize_rows_for_grading(rows: list[dict[str, Any]], max_chars: int = 110_000) -> str:
    """Serialize every row; max_chars selects compact layout, never truncation."""
    normalized = normalize_for_grading(rows)
    serialized = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) <= max_chars:
        return serialized
    columns = list(dict.fromkeys(key for row in normalized for key in row))
    columnar = {
        "format": "columnar",
        "columns": columns,
        "rows": [[row.get(column) for column in columns] for row in normalized],
        "total_rows": len(normalized),
    }
    serialized = json.dumps(columnar, ensure_ascii=False, separators=(",", ":"))
    return serialized


def truncate_for_prompt(value: str, max_chars: int = 60_000) -> str:
    value = str(value or "")
    if len(value) <= max_chars:
        return value
    head = max_chars // 2
    return value[:head] + "\n...[TRUNCATED_FOR_PROMPT]...\n" + value[-(max_chars - head):]


def grader_prompt(question: str, ground_truth: str, processed_rows: str) -> str:
    return f"""
You are a strict but fair evaluator for a finance knowledge-graph QA benchmark.

You will receive:
1. The user question.
2. The SQL-derived ground truth JSON.
3. The pipeline processed rows JSON (post-filtering, post-grouping, post-aggregation).

Your task:
Decide whether the pipeline processed rows correctly answer the user question, using the ground truth as the reference.

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
- Empty results: If ground truth is empty and the question expects no matching records, an empty processed result can be MATCH. If ground truth is non-empty and processed result is empty, it is usually MISMATCH.
- Extra rows: Extra incorrect rows should reduce the grade. If the correct answer is present but extra wrong rows are included, use PARTIAL unless the extras do not affect the requested answer.
- Field-name differences: Do not require identical field names when the meaning and values clearly correspond.
- Numeric formatting: Treat numeric strings and numbers as equivalent when values are materially the same.
- Numeric tolerance: If the ground truth contains numeric value X, treat the scan value as correct when it is between X - 1.5 and X + 1.5, unless the question explicitly requires exact precision.
- Column resolution: Do not require identical column names. Resolve meaning semantically from the question, ground truth fields, and scan fields. For example, investor id, investor profile, group labels, percentages, averages, totals, and counts may use different aliases if the required meaning is present.

Label definitions:
MATCH:
Use MATCH when the processed rows completely answer what the question asks. The answer must have the required rows/entities, values, filters, grouping, aggregation, and ranking/order when applicable. All values required by the question must be semantically equal to the ground truth values. Missing unused ground-truth fields or extra harmless columns are okay.

PARTIAL:
Use PARTIAL when the processed rows answer part of the question correctly, but some required information is missing, incomplete, extra, or wrong. Examples: some correct rows but missing others, correct grouping but one metric wrong/missing, correct entities but wrong aggregation, correct top results but wrong order, correct values for some but not all groups, or correct answer plus extra wrong rows.

MISMATCH:
Use MISMATCH when the processed rows do not answer the question, are mostly wrong, use wrong filters/entities, use wrong aggregation/ranking, return empty when the ground truth has required results, have required values that conflict with the ground truth, or are unrelated to the ground truth.

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
{question}

Ground Truth JSON:
{ground_truth}

Pipeline Processed Rows (post-filtering/aggregation):
{processed_rows}
""".strip()


def parse_grade(raw: str) -> GradeResult:
    text = (raw or "").replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        verdict = str(parsed.get("status", "OTHER")).upper()
        if verdict not in FINAL_VERDICTS:
            verdict = "OTHER"
        return GradeResult(verdict, str(parsed.get("reason", "")), parsed.get("evidence", {}) or {})
    raise ValueError("Inline grader returned no valid verdict JSON.")


def classify_grader_exception(exc: Exception) -> str:
    combined = f"{getattr(exc, 'code', '')} {exc}".lower()
    if "model_not_found" in combined or "does not exist or you do not have access" in combined:
        return "MODEL_NOT_FOUND"
    if any(marker in combined for marker in ("insufficient_quota", "credit_balance_exhausted", "no credits remaining")):
        return "QUOTA_EXHAUSTED"
    if "rate_limit" in combined or "rate limit" in combined or "429" in combined:
        return "RATE_LIMIT_ERROR"
    if any(marker in combined for marker in ("authentication", "invalid api key", "access denied", "access_denied", "401")):
        return "API_AUTH_ERROR"
    if any(marker in combined for marker in ("context_length_exceeded", "maximum context length", "finish_reason=length")):
        return "TOKEN_OUTPUT_ERROR"
    return "GRADER_API_ERROR"


def grade_rows(
    client: OpenAI,
    model: str,
    question: str,
    ground_truth: str,
    rows: list[dict[str, Any]],
    operation: str,
    api_logger: APILogger,
) -> GradeResult:
    if "[TRUNCATED_FOR_PROMPT]" in ground_truth or '"truncated": true' in ground_truth:
        return GradeResult("OTHER", "Ground truth is explicitly truncated; complete evaluation is unavailable.")
    try:
        ground_truth = json.dumps(json.loads(ground_truth), ensure_ascii=False, separators=(",", ":"))
    except (ValueError, TypeError):
        pass
    api_logger.log(question, operation)
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
            {"role": "user", "content": grader_prompt(question, ground_truth, serialize_rows_for_grading(rows))},
        ],
    )
    if not response.choices:
        raise ValueError("Inline grader returned no choices.")
    if str(response.choices[0].finish_reason or "").lower() == "length":
        raise ValueError("Inline grader output was truncated: finish_reason=length.")
    grade = parse_grade(response.choices[0].message.content or "")
    usage = getattr(response, "usage", None)
    grade.input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    grade.output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    return grade


def run_branch(
    *,
    copy_id: int,
    round_number: int,
    question: str,
    ground_truth: str,
    schema_text: str,
    target_client: OpenAI,
    target_model: str,
    grader_client: OpenAI,
    grader_model: str,
    endpoint: str,
    scan_timeout: float,
    temperature: float,
    retry_feedback: str,
    api_logger: APILogger,
) -> BranchResult:
    started = time.perf_counter()
    branch = BranchResult(copy_id=copy_id, round_number=round_number, status="STARTED")
    try:
        # Repairs use only the query, schema and execution diagnostics. The
        # reference answer and grade are never passed to the generator.
        feedback = retry_feedback
        for attempt in range(1, 4):
            sparql, input_tokens, output_tokens = generate_sparql(
                target_client, target_model, question, schema_text, copy_id,
                round_number, feedback, temperature, api_logger,
            )
            branch.sparql = sparql
            branch.generation_input_tokens += input_tokens
            branch.generation_output_tokens += output_tokens
            try:
                validate_generated_sparql(sparql, schema_text)
            except Exception as exc:
                scan = {"status": "error", "error_message": f"Pre-execution validation: {exc}"}
            else:
                scan = execute_sparql(sparql, endpoint, scan_timeout)
            branch.execution_attempts.append({
                "attempt": attempt, "sparql": sparql, "status": scan["status"],
                "error": str(scan.get("error_message", "")),
            })
            if scan["status"] == "success":
                break
            feedback = json.dumps({
                "failed_sparql": sparql,
                "execution_error": scan.get("error_message", "Unknown execution error"),
                "instruction": "Repair this query using the schema. Use fresh BIND aliases and project grouped aliases in aggregate queries.",
            }, ensure_ascii=False)
        else:
            branch.status = "SCAN_ERROR"
            branch.error = str(scan.get("error_message", "Unknown Fuseki error"))
            branch.grade = GradeResult("MISMATCH", branch.error)
            return branch
        branch.rows = scan["data"]
        branch.row_count = scan["row_count"]
        branch.result_fingerprint = result_fingerprint(branch.rows, ordered=question_requires_order(question))
        try:
            branch.grade = grade_rows(
                grader_client,
                grader_model,
                question,
                ground_truth,
                branch.rows,
                f"Round_{round_number}_Copy_{copy_id}_Inline_Grade",
                api_logger,
            )
            branch.status = "COMPLETED"
        except Exception as exc:  # noqa: BLE001 - preserve usable execution result
            error_status = classify_grader_exception(exc)
            branch.status = error_status
            branch.error = f"{type(exc).__name__}: {exc}"[:500]
            branch.grade = GradeResult(error_status, branch.error)
        return branch
    except Exception as exc:  # noqa: BLE001 - one branch must not cancel its peers
        classified = classify_grader_exception(exc)
        branch.status = classified if classified in FATAL_API_STATUSES else "GENERATION_ERROR"
        branch.error = f"{type(exc).__name__}: {exc}"[:500]
        branch.grade = GradeResult("MISMATCH", branch.error)
        return branch
    finally:
        branch.elapsed_seconds = round(time.perf_counter() - started, 3)


def find_consensus(branches: list[BranchResult]) -> tuple[list[BranchResult], int]:
    """Return the largest exact result group and the strict-majority threshold."""
    threshold = len(branches) // 2 + 1
    groups: dict[str, list[BranchResult]] = defaultdict(list)
    for branch in branches:
        if branch.result_fingerprint and branch.status not in {"GENERATION_ERROR", "SCAN_ERROR"}:
            groups[branch.result_fingerprint].append(branch)
    winner = max(groups.values(), key=lambda group: (len(group), -min(item.copy_id for item in group)), default=[])
    return (winner if len(winner) >= threshold else []), threshold


def aggregate_winner_grade(
    winners: list[BranchResult],
    *,
    grader_client: OpenAI,
    grader_model: str,
    question: str,
    ground_truth: str,
    api_logger: APILogger,
) -> GradeResult:
    usable = [branch.grade for branch in winners if branch.grade.verdict in FINAL_VERDICTS]
    counts = Counter(grade.verdict for grade in usable)
    if counts:
        verdict, count = counts.most_common(1)[0]
        if count > len(usable) // 2:
            return next(grade for grade in usable if grade.verdict == verdict)
    # Two agreeing executions can receive different stochastic grader labels.
    # Grade the agreed result once more rather than choosing a label arbitrarily.
    return grade_rows(
        grader_client,
        grader_model,
        question,
        ground_truth,
        winners[0].rows,
        "Ensemble_Final_Inline_Grade",
        api_logger,
    )


def branch_summary(branch: BranchResult) -> dict[str, Any]:
    return {
        "copy_id": branch.copy_id,
        "status": branch.status,
        "sparql": branch.sparql,
        "row_count": branch.row_count,
        "result_fingerprint": branch.result_fingerprint,
        "grade_verdict": branch.grade.verdict,
        "grade_reason": branch.grade.reason,
        "error": branch.error,
        "elapsed_seconds": branch.elapsed_seconds,
        "generation_input_tokens": branch.generation_input_tokens,
        "generation_output_tokens": branch.generation_output_tokens,
        "grader_input_tokens": branch.grade.input_tokens,
        "grader_output_tokens": branch.grade.output_tokens,
        "execution_attempts": branch.execution_attempts,
    }


def retry_feedback_from_round(branches: list[BranchResult]) -> str:
    summary = []
    for branch in branches:
        summary.append({
            "copy": branch.copy_id,
            "scan_status": "success" if branch.result_fingerprint else "execution_failed",
            "row_count": branch.row_count,
            "result_fingerprint": branch.result_fingerprint[:16],
            "error": branch.error if branch.status in {"SCAN_ERROR", "GENERATION_ERROR"} else "",
            "sparql": branch.sparql[:6_000],
        })
    return json.dumps(summary, ensure_ascii=False)


def run_ensemble_question(
    *,
    question: str,
    ground_truth: str,
    schema_text: str,
    copies: int,
    max_retries: int,
    branch_runner: Callable[..., BranchResult],
    branch_kwargs: dict[str, Any],
    grader_client: OpenAI,
    grader_model: str,
    api_logger: APILogger,
) -> dict[str, Any]:
    all_rounds: list[list[BranchResult]] = []
    retry_feedback = ""
    for round_number in range(1, max_retries + 2):
        branches: list[BranchResult] = []
        with ThreadPoolExecutor(max_workers=copies, thread_name_prefix=f"ensemble-r{round_number}") as pool:
            futures = [
                pool.submit(
                    branch_runner,
                    copy_id=copy_id,
                    round_number=round_number,
                    question=question,
                    ground_truth=ground_truth,
                    schema_text=schema_text,
                    retry_feedback=retry_feedback,
                    **branch_kwargs,
                )
                for copy_id in range(1, copies + 1)
            ]
            for future in as_completed(futures):
                branches.append(future.result())
        branches.sort(key=lambda item: item.copy_id)
        all_rounds.append(branches)
        winners, threshold = find_consensus(branches)
        if winners and not winners[0].rows and round_number <= max_retries:
            # Empty agreement is weak evidence: unrelated invalid graph patterns
            # all return []. Check again using execution-only feedback. A valid
            # empty result can still be returned after the last configured round.
            retry_feedback = json.dumps({
                "diagnostic": "The agreeing queries returned zero rows. Recheck property ownership, labels, joins and filters against the schema. Do not remove question conditions just to produce rows.",
                "previous_round": json.loads(retry_feedback_from_round(branches)),
            }, ensure_ascii=False)
            continue
        if winners:
            try:
                final_grade = aggregate_winner_grade(
                    winners,
                    grader_client=grader_client,
                    grader_model=grader_model,
                    question=question,
                    ground_truth=ground_truth,
                    api_logger=api_logger,
                )
            except Exception as exc:  # noqa: BLE001
                status = classify_grader_exception(exc)
                final_grade = GradeResult(status, f"{type(exc).__name__}: {exc}"[:500])
            return {
                "pipeline_status": "CONSENSUS",
                "consensus": True,
                "consensus_size": len(winners),
                "threshold": threshold,
                "winners": winners,
                "winner": winners[0],
                "grade": final_grade,
                "rounds": all_rounds,
                "rounds_used": round_number,
            }
        retry_feedback = retry_feedback_from_round(branches)

    return {
        "pipeline_status": "FAILURE_NO_CONSENSUS",
        "consensus": False,
        "consensus_size": 0,
        "threshold": copies // 2 + 1,
        "winners": [],
        "winner": None,
        "grade": GradeResult("OTHER", f"No strict majority after {max_retries + 1} rounds."),
        "rounds": all_rounds,
        "rounds_used": max_retries + 1,
    }


def load_benchmark(path: Path, full_ground_truth: Path) -> pd.DataFrame:
    frame = pd.read_excel(path) if path.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(path)
    required = {"global_question_id", "question", "ground_truth_answer"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Benchmark must contain columns: {sorted(required)}")
    if full_ground_truth.is_file():
        source = pd.read_csv(full_ground_truth, usecols=["global_question_id", "ground_truth_answer"])
        lookup = source.drop_duplicates("global_question_id").set_index("global_question_id")["ground_truth_answer"]
        replacements = frame["global_question_id"].map(lookup)
        mask = replacements.notna() & (
            replacements.astype(str).str.len() > frame["ground_truth_answer"].astype(str).str.len()
        )
        frame.loc[mask, "ground_truth_answer"] = replacements[mask]
    return frame


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_existing_report(path: Path, config: str) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if rows and any(row.get("Run Config") != config for row in rows):
        raise ValueError(f"Existing report uses a different configuration: {path}")
    # Credential, quota, and transport failures are resumable, not completed work.
    return [row for row in rows if row.get("New Status", "").upper() not in GRADER_FAILURE_STATUSES]


def is_fatal_api_status(status: str) -> bool:
    return status in FATAL_API_STATUSES


def run(args: argparse.Namespace) -> None:
    if args.copies < 3 or args.copies % 2 == 0:
        raise ValueError("--copies must be an odd number of at least 3; the diagram uses 3.")
    if args.max_retries < 0 or args.offset < 0 or args.limit < 0:
        raise ValueError("--max-retries, --offset, and --limit must be nonnegative.")
    if args.scan_timeout <= 0 or args.metadata_timeout <= 0:
        raise ValueError("--scan-timeout and --metadata-timeout must be positive.")
    if args.temperature < 0:
        raise ValueError("--temperature must be nonnegative.")
    if not args.schema.is_file():
        raise FileNotFoundError(args.schema)
    if not args.benchmark.is_file():
        raise FileNotFoundError(args.benchmark)

    check_fuseki(args.fuseki_endpoint)
    target_client = make_target_client(args.target_model)
    grader_client = make_grader_client(args.grader_model)
    metadata = load_schema(args.schema, args.fuseki_endpoint, args.metadata_timeout)
    schema_text = build_schema_text(metadata)
    benchmark = load_benchmark(args.benchmark, args.full_ground_truth)
    selected = benchmark.iloc[args.offset:] if args.limit == 0 else benchmark.iloc[args.offset:args.offset + args.limit]

    config = json.dumps({
        "version": VERSION,
        "copies": args.copies,
        "max_retries": args.max_retries,
        "target_model": args.target_model,
        "grader_model": args.grader_model,
        "temperature": args.temperature,
        "fuseki_endpoint": args.fuseki_endpoint,
        "schema": str(args.schema.resolve()),
        "benchmark": str(args.benchmark.resolve()),
    }, sort_keys=True)
    rows = read_existing_report(args.report, config)
    if args.retry_failures:
        rows = [row for row in rows if row.get("Pipeline Status") != "FAILURE_NO_CONSENSUS"]
    completed = {row["Sample Row ID"] for row in rows}

    api_logger = APILogger(args.report.parent)
    branch_kwargs = {
        "target_client": target_client,
        "target_model": args.target_model,
        "grader_client": grader_client,
        "grader_model": args.grader_model,
        "endpoint": args.fuseki_endpoint,
        "scan_timeout": args.scan_timeout,
        "temperature": args.temperature,
        "api_logger": api_logger,
    }

    for position, (_, item) in enumerate(selected.iterrows(), start=1):
        sample_id = str(item["global_question_id"])
        if sample_id in completed:
            continue
        started_at = dt.datetime.now().isoformat(timespec="seconds")
        started = time.perf_counter()
        question = str(item["question"])
        ground_truth = str(item["ground_truth_answer"])
        outcome = run_ensemble_question(
            question=question,
            ground_truth=ground_truth,
            schema_text=schema_text,
            copies=args.copies,
            max_retries=args.max_retries,
            branch_runner=run_branch,
            branch_kwargs=branch_kwargs,
            grader_client=grader_client,
            grader_model=args.grader_model,
            api_logger=api_logger,
        )
        winner: BranchResult | None = outcome["winner"]
        grade: GradeResult = outcome["grade"]
        final_rows = winner.rows if winner else []
        round_log = [
            {"round": index, "branches": [branch_summary(branch) for branch in branches]}
            for index, branches in enumerate(outcome["rounds"], start=1)
        ]
        all_branches = [branch for branches in outcome["rounds"] for branch in branches]
        grade_is_reused = any(grade is branch.grade for branch in all_branches)
        row = {
            "Pipeline Version": VERSION,
            "Run Config": config,
            "Sample Row ID": sample_id,
            "Question": question,
            "Ground Truth": ground_truth,
            "Difficulty": str(item.get("difficulty", "")),
            "Category": str(item.get("category", "")),
            "Query Type": str(item.get("query_type", "")),
            "Source CSV": str(item.get("source_csv", "")),
            "Pipeline Status": outcome["pipeline_status"],
            "New Status": grade.verdict if outcome["consensus"] else "FAILURE_NO_CONSENSUS",
            "Comparison / Comments": grade.reason,
            "Ensemble Result": serialize_rows_for_grading(final_rows),
            "Processed Rows": serialize_rows_for_grading(final_rows),
            "Consensus Achieved": outcome["consensus"],
            "Consensus Size": outcome["consensus_size"],
            "Winning Copies": json.dumps([branch.copy_id for branch in outcome["winners"]]),
            "Rounds Used": outcome["rounds_used"],
            "Retry Rounds Used": max(0, outcome["rounds_used"] - 1),
            "Grade Verdict": grade.verdict,
            "Grade Reason": grade.reason,
            "Grade Evidence": json.dumps(grade.evidence, ensure_ascii=False),
            "Target Model": args.target_model,
            "Grader Model": args.grader_model,
            "Generation Input Tokens": sum(branch.generation_input_tokens for branch in all_branches),
            "Generation Output Tokens": sum(branch.generation_output_tokens for branch in all_branches),
            "Grader Input Tokens": sum(branch.grade.input_tokens for branch in all_branches) + (0 if grade_is_reused else grade.input_tokens),
            "Grader Output Tokens": sum(branch.grade.output_tokens for branch in all_branches) + (0 if grade_is_reused else grade.output_tokens),
            "Final SPARQL": winner.sparql if winner else "",
            "Final Scan Row Count": winner.row_count if winner else "",
            "All Rounds Log": json.dumps(round_log, ensure_ascii=False),
            "Started At": started_at,
            "Elapsed Seconds": round(time.perf_counter() - started, 3),
        }
        rows.append(row)
        completed.add(sample_id)
        write_report(args.report, rows)
        api_logger.save()
        print(
            f"[{position}/{len(selected)}] {sample_id}: {row['Pipeline Status']} / "
            f"{row['New Status']}; rounds={row['Rounds Used']}; consensus={row['Consensus Size']}",
            flush=True,
        )
        fatal_statuses = {branch.status for branch in all_branches if is_fatal_api_status(branch.status)}
        if grade.verdict in FATAL_API_STATUSES or fatal_statuses:
            print("Stopping after an API/grader failure; rerun to resume safely.", file=sys.stderr)
            break

    api_logger.save()
    print(f"Report: {args.report}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--full-ground-truth", type=Path, default=DEFAULT_FULL_GROUND_TRUTH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-model", default=DEFAULT_TARGET_MODEL)
    parser.add_argument("--grader-model", default=DEFAULT_GRADER_MODEL)
    parser.add_argument("--fuseki-endpoint", default=DEFAULT_FUSEKI_ENDPOINT)
    parser.add_argument("--copies", type=int, default=int(os.getenv("PARALLEL_COPIES", "3")))
    parser.add_argument("--max-retries", type=int, default=int(os.getenv("PARALLEL_MAX_RETRIES", "2")))
    parser.add_argument("--offset", type=int, default=int(os.getenv("TEST_QUERY_OFFSET", "0")))
    parser.add_argument("--limit", type=int, default=int(os.getenv("TEST_QUERY_LIMIT", "442")), help="0 means all remaining rows")
    parser.add_argument("--temperature", type=float, default=float(os.getenv("GENERATION_TEMPERATURE", "0.3")))
    parser.add_argument("--scan-timeout", type=float, default=float(os.getenv("FUSEKI_SCAN_TIMEOUT_SECONDS", "60")))
    parser.add_argument("--metadata-timeout", type=float, default=float(os.getenv("FUSEKI_METADATA_TIMEOUT_SECONDS", "60")))
    parser.add_argument("--retry-failures", action="store_true", help="rerun saved FAILURE_NO_CONSENSUS rows")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args)


if __name__ == "__main__":
    main()
