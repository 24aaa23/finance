import difflib
import json
import re
import unicodedata
from typing import Any, Callable

import rdflib
from openai import OpenAI as LLMClient

from script_diff_llm.backends.kg import (
    collect_fuseki_graph_terms,
    execute_sparql_on_fuseki,
    validate_sparql_terms as validate_sparql_terms_against_known_terms,
)


def build_schema_generation_rules(schema_details: dict[str, Any]) -> str:
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


def sanitize_user_query(raw_query: str) -> str:
    normalized = unicodedata.normalize("NFKD", raw_query).encode("ascii", "ignore").decode("utf-8")
    cleaned = re.sub(r"[^\x20-\x7E]", "", normalized)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else "Invalid Query"


def canonical_id_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def load_rdf_id_alias_map(alias_file: str) -> dict[str, Any]:
    if not alias_file:
        return {}
    try:
        with open(alias_file) as handle:
            alias_data = json.load(handle)
    except FileNotFoundError:
        return {}
    if not isinstance(alias_data, dict):
        return {}
    return alias_data


def resolve_graph_id_alias(value: str, rdf_id_alias_map: dict[str, Any]) -> str:
    entry = rdf_id_alias_map.get(canonical_id_key(value), {})
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


def normalize_compact_kg_ids(text: str, rdf_id_alias_map: dict[str, Any]) -> str:
    text = re.sub(
        r"\bex:([A-Za-z]+-?\d{1,4})\b",
        lambda m: f"kg:{resolve_graph_id_alias(m.group(1), rdf_id_alias_map)}",
        text,
        flags=re.I,
    )
    text = re.sub(
        r'(["\'])([A-Za-z]+-?\d{1,4})\1',
        lambda m: f"{m.group(1)}{resolve_graph_id_alias(m.group(2), rdf_id_alias_map)}{m.group(1)}",
        text,
        flags=re.I,
    )
    return text


def strip_llm_reasoning_blocks(text: str) -> str:
    cleaned = re.sub(r"(?is)<reasoning>.*?</reasoning>", "", text or "")
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
    cleaned = re.sub(r"(?ims)^\s*<reasoning>.*?(?=^\s*(?:PREFIX|SELECT|ASK|CONSTRUCT|DESCRIBE)\b)", "", cleaned)
    cleaned = re.sub(r"(?ims)^\s*<think>.*?(?=^\s*(?:PREFIX|SELECT|ASK|CONSTRUCT|DESCRIBE)\b)", "", cleaned)

    sparql_start = re.search(r"(?im)^\s*(PREFIX|SELECT|ASK|CONSTRUCT|DESCRIBE)\b", cleaned)
    if sparql_start:
        cleaned = cleaned[sparql_start.start():]
    return cleaned.strip()


def preprocess_user_query(query: str, rdf_id_alias_map: dict[str, Any]) -> str:
    cleaned = sanitize_user_query(query)
    return re.sub(
        r"\b([A-Za-z]+-?\d{1,4})\b",
        lambda match: resolve_graph_id_alias(match.group(1), rdf_id_alias_map),
        cleaned,
    )


def extract_first_json_object(text: str) -> dict[str, Any] | None:
    cleaned = strip_llm_reasoning_blocks(text or "")
    cleaned = cleaned.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    decoder = json.JSONDecoder()
    for start, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def repair_sparql_query(sparql: str, rdf_id_alias_map: dict[str, Any]) -> str:
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
    normalized = normalize_compact_kg_ids(normalized, rdf_id_alias_map)

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


def extract_ex_terms_from_sparql(sparql: str) -> list[str]:
    body = re.sub(r"PREFIX\s+\w+:\s*<[^>]+>", "", sparql or "", flags=re.I)
    return sorted(set(re.findall(r"\bwm:([A-Za-z_][A-Za-z0-9_-]*)\b", body)))


def validate_sparql_terms(
    sparql: str,
    *,
    known_terms_cache: set[str] | None,
    fuseki_endpoint: str,
    fuseki_metadata_timeout_seconds: float,
    logger: Callable[[str], None],
) -> tuple[dict[str, Any], set[str]]:
    known_terms = collect_fuseki_graph_terms(
        known_terms_cache,
        fuseki_endpoint,
        fuseki_metadata_timeout_seconds,
        logger,
    )
    return validate_sparql_terms_against_known_terms(sparql, known_terms), known_terms


def semantic_retrieve(
    inputs: dict[str, Any],
    client: LLMClient,
    model: str,
    *,
    parse_json_fn: Callable[[str, Any, str], Any],
    log_call_fn: Callable[[Any, str], None],
) -> dict[str, Any]:
    table_index = inputs.get("table_index", {})
    prompt = f"""
You are the Retrieve operator. Select relevant ontology class names for the user query.

User Query: {inputs.get('query')}
Available Classes (Index): {json.dumps(table_index, indent=2)}

Return ONLY a JSON array of exact class names from Available Classes.
Do not write Python code.
Do not explain.
Example output: ["InvestorProfile", "PortfolioHolding"]
"""

    log_call_fn(inputs.get("query"), "Retrieve")
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    result = response.choices[0].message.content
    retrieved_tables = parse_json_fn(result, [], "Retrieve")
    if not isinstance(retrieved_tables, list):
        retrieved_tables = []
    retrieved_tables = [table for table in retrieved_tables if table in table_index]
    if not retrieved_tables:
        print("[WARN] Retrieve returned no valid classes; Generate will use the full dynamic schema.")
    return {"retrieved_tables": retrieved_tables}


def semantic_generate_sparql(
    inputs: dict[str, Any],
    client: Any,
    model: str,
    *,
    rdf_id_alias_map: dict[str, Any],
    log_call_fn: Callable[[Any, str], None],
) -> dict[str, Any]:
    retrieved_classes = inputs.get("retrieved_tables", [])
    global_schema = inputs.get("global_schema", {})
    root_query = inputs.get("root_query", "") or inputs.get("query", "")

    print(f"\n[DEBUG] Retrieve passed these classes: {retrieved_classes}")

    pruned_schema = {cls: global_schema[cls] for cls in retrieved_classes if cls in global_schema}
    if not pruned_schema:
        print("[DEBUG] Target Classes empty/invalid. Passing full dynamic schema to Generate.")
        pruned_schema = global_schema
    schema_generation_rules = build_schema_generation_rules(pruned_schema)

    logic_feedback = inputs.get("logic_feedback", "")
    failed_sparql = inputs.get("sparql", "")
    query_spec = inputs.get("query_spec", {})
    query_spec_context = ""
    if query_spec:
        query_spec_context = f"""
Structured Query Spec:
{json.dumps(query_spec, indent=2)}

Treat this spec as the semantic contract for the SPARQL. The SPARQL should implement its base_entity,
entity_key, filters, grain, group_by, measures, ranking, execution_strategy, and
output_schema whenever those fields are present, schema-grounded, and executable in one SPARQL query.
"""
    query_spec_contract_rules = ""
    if query_spec:
        query_spec_contract_rules = """
QUERY SPEC CONTRACT RULES:
- The Structured Query Spec is the semantic contract for the executable SPARQL, not optional guidance.
- Do not reinterpret the spec: implement the measures, grain, and output schema it states.
- Prefer schema-grounded simplification only when a Query_Spec field is provably unsupported by the retrieved schema.
- Every field in query_spec["output_schema"] must appear in the final SELECT, unless there is a clearly equivalent alias.
- Every measure in query_spec["measures"] must be implemented.
- Use the exact output_name from each measure as the SELECT alias whenever possible.
- If a measure has formula != null, implement that formula exactly using formula_fields.
- Never replace a formula-based measure with COUNT.
- Never replace SUM, AVG, MIN, or MAX with COUNT unless query_spec explicitly says COUNT.
- If join_policy is "inner_join", do not use OPTIONAL + COALESCE(0) for required base/event classes.
- Group-by dimension fields are different from required base/event classes: OPTIONAL + COALESCE("NULL") is allowed and preferred for group-by dimensions when preserve_null_groups is true.
- If join_policy is "left_join", OPTIONAL is allowed.
- If join_policy is "anti_join", use FILTER NOT EXISTS or MINUS.
- If query_spec["fanout_control"]["required"] is true, or grain.pre_aggregate_by is non-empty, you MUST use
  two-level aggregation. A single flat pattern is WRONG in that case: matching an entity against one-to-many
  relations repeats that entity once per related record, so the final AVG or SUM is weighted by
  related-record counts instead of by entity.
- Two-level SPARQL pattern to follow: put one nested sub-SELECT per measure source, each grouping by the
  pre_aggregate_by key and applying that measure's per_entity_operation; join the sub-SELECT results on that
  key in the outer query; apply each measure's final_operation in the outer GROUP BY over the group_by field.
    SELECT ?groupField (AVG(?perEntityValue) AS ?outputAlias) WHERE {
      ?entity <groupPredicate> ?groupField .
      { SELECT ?entity (AVG(?raw) AS ?perEntityValue) WHERE { ?entity <measurePredicate> ?raw } GROUP BY ?entity }
    } GROUP BY ?groupField
- Apply per_entity_operation inside the sub-SELECT and final_operation outside. When final_operation is AVG,
  the outer aggregate must be AVG, never SUM.
- If execution_strategy is "preaggregate_sparql", avoid flat multi-table joins that multiply rows.
- If a group_by item uses bucket_strategy, construct explicit bucket labels with BIND/IF or nested IF logic and group by those bucket labels instead of the raw numeric field.
- The current executor supports one executable SPARQL query. Do not attempt unsupported multi-scan or pandas-merge behavior inside one giant query.
"""
    retry_context = ""
    if logic_feedback and failed_sparql:
        retry_context = f"""
        WARNING: You are in a self-healing retry loop. Your previous SPARQL query failed.
        Previous Failed SPARQL: {failed_sparql}
        Error Report & Actual Database Properties (JSON): {logic_feedback}
        You MUST rewrite the query differently. Read the JSON report above carefully. You must specifically use the exact properties listed in the 'actual_properties_on_node' field and follow the instructions in the 'hint' field. Do not guess or hallucinate property names.
        """
    prompt = f"""
You are the Generate operator. Write one executable SPARQL query for the RDF graph.

Subquery Description: "{inputs.get('query')}"
Original User Query: "{root_query}"
Target Classes: {retrieved_classes}
Schema Details: {json.dumps(pruned_schema, indent=2)}
Dynamic Schema Rules:
{schema_generation_rules}
{query_spec_context}
{query_spec_contract_rules}
{retry_context}

Return ONLY raw SPARQL text. Do not explain. Do not include <reasoning>, <think>, markdown, comments, or prose.
The first non-whitespace characters in your response must be PREFIX or SELECT.
Do not invent example people such as John Doe.
- Treat Subquery Description and Query_Spec as the binding scope for this SPARQL.
- Use Original User Query only for shared context such as the year or outer wording.
- If the original user query contains sibling conditions that are not stated in the Subquery Description or Query_Spec, do NOT add them to this SPARQL.

RDF VOCABULARY RULES:
- Use only classes, predicates, and resources that appear in Schema Details or the RDF graph.
- Do NOT use schema-linkage attribute names as rdf:type classes unless they are real RDF classes.
- Do NOT invent object properties for joins. Prefer listed relationship predicates/direct object references over shared literal-value joins.
- Do NOT use schema1: properties in executable graph patterns. Use wm: properties.
- Never invent repeated properties such as `wm:nameLiteralLiteral`.
- If the user mentions a resource ID with punctuation, normalize cautiously but still use only identifiers visible in the graph.
- For entity/list questions, anchor the returned subject with `rdf:type` for the query_spec base_entity or the relevant required class from Schema Details.
- A literal identifier property alone is not proof of class membership. Do not select arbitrary subjects only because they share an ID-like literal; type the subject first.
- For missing-required-field questions, apply `FILTER NOT EXISTS` only after the subject is typed as the requested entity class, and keep requested display fields mandatory unless the user explicitly asks to include missing display fields.

ENTITY ANCHOR POLICY:
- Determine the returned entity class from query_spec["base_entity"] or query_spec["required_classes"], then confirm that class exists in Schema Details.
- When SELECT returns entity identifiers, names, or display fields, bind those fields from a subject typed as that selected entity class.
- Do not infer class membership from identifier-like literals alone; different classes may share similar ID fields.
- Never return taxonomy, category, group, or label values as entity IDs unless the requested base_entity itself is that taxonomy/category class.

JOIN SAFETY RULES:
- Use cardinality_hints from Schema Details when joining classes through literal properties.
- Do not create a flat join between two classes through a literal property when both sides show many_per_value behavior for the joined values.
- A many_per_value to many_per_value flat join can multiply rows, distort SUM/AVG results, and time out.
- If such a join is truly needed, first aggregate each class separately in subqueries, then join the smaller grouped results.
- If no direct relationship or safe cardinality exists, answer from the most relevant class instead of forcing a join.
- Timeout feedback means the query plan is too large; rewrite the graph pattern structurally, not cosmetically.

MISSING RELATED RECORD RULE:
- If the query asks for base entities with at least one related record missing a field, anchor the WHERE pattern on the related record class that owns the missing field.
- Apply FILTER NOT EXISTS to that related record, not to an unjoined base entity.
- Count or select DISTINCT base entity keys from the related record itself or from a direct object/key join.
- If the related record has the base entity key as a literal property, prefer that direct key over traversing through the base entity class.
- Never place the base entity class and related record class side by side without a direct relationship or shared key constraint.
- Do not add unrelated numeric fields, optional display fields, or extra classes for this pattern.

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

COUNT RULE: If the requested measure is COUNT, do not require unrelated numeric fields. Count the entity identifier directly. For example, use `?cashFlow wm:cashFlowId ?cashFlowId . COUNT(?cashFlowId)`. Do not add `?cashFlow wm:amount ?amount` merely because CashFlow has amount. Use numeric fields only for SUM, AVG, MIN, or MAX.
Use COUNT(?id) by default. Use COUNT(DISTINCT ?id) only when the user asks for distinct, unique, or different values, or when query_spec["measures"][...]["requires_distinct"] is true after cleanup.

NULL GROUP RULE: For group-by questions using "for each", "by", "per", or "across", do not drop rows only because the group field is missing. Use OPTIONAL for the group field and COALESCE to "NULL". Example: `OPTIONAL {{ ?goal wm:timeToGoalMonths ?timeToGoalMonthsRaw . }} BIND(COALESCE(STR(?timeToGoalMonthsRaw), "NULL") AS ?timeToGoalMonths)`.

MONTH RULE: If the query asks "per month", "for each month", or "monthly", extract YYYY-MM from date strings. Use `BIND(SUBSTR(STR(?date), 1, 7) AS ?month)` and GROUP BY ?month. Never group directly by full date for month-level questions.

RANKING TIE RULE: If using ORDER BY with LIMIT, add a deterministic secondary sort on a stable selected identifier or label after the primary metric. This prevents arbitrary tied rows.

CRITICAL RULE 3 (CASE-INSENSITIVE FILTERS): When filtering by text or IDs, you MUST use lowercase comparison.
Example: `FILTER(CONTAINS(LCASE(STR(?id)), "inv-001"))`.

CRITICAL RULE 4 (NEGATION): If the user query contains words like "never", "not", "excluding", "without", or "no X", you MUST use `FILTER NOT EXISTS {{ }}` or `MINUS {{ }}` to ensure those records are excluded.

CRITICAL RULE 5 (LABELS OVER IRIs): For any controlled-vocabulary class (InvestmentType, Sector, Segment, RiskCategory), always follow the label property to get the human-readable string.


"""

    log_call_fn(root_query, "Generate")
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    result = response.choices[0].message.content.strip()

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

    return {"sparql": repair_sparql_query(sparql_query, rdf_id_alias_map)}


def semantic_refine(
    inputs: dict[str, Any],
    client: Any,
    model: str,
    *,
    rdf_id_alias_map: dict[str, Any],
    log_call_fn: Callable[[Any, str], None],
    supports_temperature_fn: Callable[[str], bool],
) -> dict[str, Any]:
    schema_details = inputs.get("schema_details") or inputs.get("global_schema", {})
    root_query = inputs.get("root_query", "") or inputs.get("query", "")
    prompt = f"""
    The next operator is Refine.
    Analyze the SPARQL error and provide a corrected raw SPARQL query.

    Subquery Description: {inputs.get('query')}
    Original User Query: {root_query}
    Query Spec: {json.dumps(inputs.get('query_spec', {}), indent=2)}
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

    QUERY SPEC REFINEMENT RULES:
    - The corrected SPARQL must still satisfy the Query_Spec.
    - Do not fix syntax by changing the meaning of the query.
    - Do not remove required measures from query_spec["measures"].
    - Do not remove required group_by fields.
    - If query_spec has formula-based measures, preserve the formula.
    - If the previous error was a timeout, rewrite the query structurally using subqueries or pre-aggregation.
    - If the previous error was unknown RDF terms, replace only invalid terms with valid schema-grounded terms.
    - The corrected query must be suitable for Pre_Scan_Validate before Scan.

    JOIN SAFETY RULES:
    - Use cardinality_hints from Schema Details when joining classes through literal properties.
    - Do not create a flat join between two classes through a literal property when both sides show many_per_value behavior for the joined values.
    - A many_per_value to many_per_value flat join can multiply rows, distort SUM/AVG results, and time out.
    - If such a join is truly needed, first aggregate each class separately in subqueries, then join the smaller grouped results.
    - If no direct relationship or safe cardinality exists, answer from the most relevant class instead of forcing a join.
    - Timeout feedback means the query plan is too large; rewrite the graph pattern structurally, not cosmetically.

    MISSING RELATED RECORD RULE:
    - If the query asks for base entities with at least one related record missing a field, anchor the WHERE pattern on the related record class that owns the missing field.
    - If the related record has the base entity key as a literal property, count/select DISTINCT that key directly from the related record.
    - Avoid traversing through the base entity class for this pattern unless the related record does not carry the base key.
    - Apply FILTER NOT EXISTS to the related record, not to the base entity.

    Output strictly the corrected raw SPARQL text without explanations, reasoning tags, prose, comments, or markdown formatting.
    The first non-whitespace characters in your response must be PREFIX or SELECT.
    """

    log_call_fn(root_query, "Refine")
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if supports_temperature_fn(model):
        request["temperature"] = 0.1
    response = client.chat.completions.create(**request)

    result = response.choices[0].message.content.strip()
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
    return {"sparql": repair_sparql_query(sparql, rdf_id_alias_map)}


def semantic_pre_scan_validate(
    inputs: dict[str, Any],
    client: Any,
    model: str,
    *,
    parse_json_fn: Callable[[str, Any, str], Any],
    log_call_fn: Callable[[Any, str], None],
) -> dict[str, Any]:
    query = inputs.get("query", "")
    root_query = inputs.get("root_query", "") or query
    query_spec = inputs.get("query_spec", {})
    sparql = inputs.get("sparql", "")

    if not sparql.strip():
        return {
            "pre_scan_validation": {
                "is_valid": False,
                "reason": "No SPARQL was generated.",
                "rewrite_hint": "Generate a complete executable SPARQL query using the Query_Spec."
            }
        }

    prompt = f"""
You are Pre_Scan_Validate.

Your job is to check whether the generated SPARQL satisfies the Query_Spec before execution.
Do not execute the query.
Do not judge returned data.
Only inspect the SPARQL logic.

User Query:
{query}

Query_Spec:
{json.dumps(query_spec, indent=2)}

Generated SPARQL:
{sparql}

Validation rules:
1. Every field in query_spec["output_schema"] should appear in the SELECT output, unless there is a clearly equivalent alias.
2. Every measure in query_spec["measures"] must be implemented.
3. If a measure has formula != null, the SPARQL must implement that formula using formula_fields.
4. Never allow COUNT to replace SUM, AVG, MIN, MAX, or a formula-based measure unless Query_Spec explicitly asks for COUNT.
5. If join_policy is "inner_join", required base/event classes should not be joined using OPTIONAL + COALESCE(0). However, group-by dimension fields may use OPTIONAL + COALESCE("NULL") to preserve missing groups.
6. If grain.pre_aggregate_by is present, SPARQL should pre-aggregate at that grain before final grouping.
7. If ranking.required is true, SPARQL must include the correct ORDER BY direction and LIMIT.
8. If filters are present in Query_Spec, SPARQL must implement them.
9. If the SPARQL changes the meaning of the user query, mark invalid.
10. For entity/list questions, the returned subject must be typed with `rdf:type` for query_spec["base_entity"] or a relevant query_spec["required_classes"] entry. Using only an ID-like literal property is invalid because different classes can share identifier literals.
11. For missing-required-field questions, `FILTER NOT EXISTS` must be scoped to the typed requested entity class. Null/None values in requested display fields indicate the query may have matched the wrong class and should be marked invalid unless those fields are explicitly allowed to be missing.
12. If ORDER BY and LIMIT are used for ranking, missing deterministic tie-breaks are repairable_warning, not hard_error.
13. For missing-field queries over related records, SPARQL must show a direct object relationship or shared key between the base entity and related record before counting base entities. Independent typed class patterns with no join are invalid because they create a Cartesian product and can time out.

Return ONLY valid JSON:
{{
  "is_valid": true/false,
  "severity": "valid|acceptable_warning|repairable_warning|hard_error",
  "reason": "specific reason",
  "rewrite_hint": "specific instruction to fix the SPARQL"
}}

Severity rules:
- valid: SPARQL satisfies the spec.
- acceptable_warning: Minor issue that should not block Scan, such as harmless alias differences or OPTIONAL + COALESCE for group-by dimensions.
- repairable_warning: Query is executable but likely semantically degraded; regenerate if retries remain, otherwise Scan with warning.
- hard_error: SPARQL is empty, not executable, uses unknown classes/predicates, omits a required measure/filter, changes the entity class, or cannot answer the query.
"""

    log_call_fn(root_query, "Pre_Scan_Validate")
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0

    malformed_default = {
        "is_valid": False,
        "severity": "repairable_warning",
        "reason": "Pre_Scan_Validate failed to parse model output.",
        "rewrite_hint": "Return only one JSON object with is_valid, severity, reason, and rewrite_hint.",
    }
    response = client.chat.completions.create(**request)
    raw_content = response.choices[0].message.content

    parsed = extract_first_json_object(raw_content)
    if parsed is None:
        parsed = parse_json_fn(raw_content, malformed_default, "Pre_Scan_Validate")

    if not isinstance(parsed, dict):
        retry_prompt = f"""
Your previous reply was malformed or not a JSON object.

Return ONLY one JSON object for the same validation decision.
Do not explain.
Do not include markdown.
Do not include extra text.

Required format:
{{
  "is_valid": true/false,
  "severity": "valid|acceptable_warning|repairable_warning|hard_error",
  "reason": "specific reason",
  "rewrite_hint": "specific instruction to fix the SPARQL"
}}

User Query:
{query}

Query_Spec:
{json.dumps(query_spec, indent=2)}

Generated SPARQL:
{sparql}
"""
        log_call_fn(root_query, "Pre_Scan_Validate_Retry")
        retry_request = {
            "model": model,
            "messages": [{"role": "user", "content": retry_prompt}],
        }
        if not model.lower().startswith("gpt-5"):
            retry_request["temperature"] = 0.0
        retry_response = client.chat.completions.create(**retry_request)
        retry_content = retry_response.choices[0].message.content
        parsed = extract_first_json_object(retry_content)
        if parsed is None:
            parsed = parse_json_fn(retry_content, malformed_default, "Pre_Scan_Validate_Retry")

    if not isinstance(parsed, dict):
        parsed = {
            "is_valid": False,
            "severity": "repairable_warning",
            "reason": "Pre_Scan_Validate returned non-dict output.",
            "rewrite_hint": "Return a single JSON object and regenerate SPARQL using Query_Spec exactly.",
        }
    if parsed.get("is_valid"):
        parsed["severity"] = "valid"
    elif parsed.get("severity") not in {"acceptable_warning", "repairable_warning", "hard_error"}:
        parsed["severity"] = "repairable_warning"

    return {"pre_scan_validation": parsed}


def pre_programmed_scan(
    inputs: dict[str, Any],
    rdf_graph: rdflib.Graph,
    *,
    rdf_id_alias_map: dict[str, Any],
    known_terms_cache: set[str] | None,
    fuseki_endpoint: str,
    fuseki_scan_timeout_seconds: float,
    fuseki_metadata_timeout_seconds: float,
    logger: Callable[[str], None],
) -> tuple[dict[str, Any], set[str]]:
    del rdf_graph
    sparql_query = repair_sparql_query(inputs.get("sparql", ""), rdf_id_alias_map)
    print(f"\n[DEBUG SPARQL EXECUTED]\n{sparql_query}\n")
    if not sparql_query:
        return {"status": "error", "error_message": "No SPARQL provided to Scan operator."}, known_terms_cache or set()

    term_check, next_known_terms_cache = validate_sparql_terms(
        sparql_query,
        known_terms_cache=known_terms_cache,
        fuseki_endpoint=fuseki_endpoint,
        fuseki_metadata_timeout_seconds=fuseki_metadata_timeout_seconds,
        logger=logger,
    )
    if not term_check["is_valid"]:
        return ({
            "status": "error",
            "error_message": "SPARQL uses terms that do not exist in the RDF graph.",
            "failed_sparql": sparql_query,
            "unknown_terms": term_check["unknown_terms"],
            "term_suggestions": term_check["suggestions"],
        }, next_known_terms_cache)

    try:
        result = execute_sparql_on_fuseki(
            sparql_query,
            fuseki_endpoint,
            fuseki_scan_timeout_seconds,
        )
    except Exception as exc:
        result = {
            "status": "error",
            "error_message": str(exc),
            "failed_sparql": sparql_query,
        }
    return result, next_known_terms_cache
