"""Generate operator: creates SPARQL using an LLM."""

from ..common import (
    Any,
    Dict,
    api_logger,
    json,
)
from ..clients import build_llm_messages
from ..utils import build_schema_generation_rules, repair_sparql_for_query


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
    query_spec = inputs.get('query_spec', {})
    active_retrieval_spec = inputs.get("retrieval_spec", {})
    query_spec_context = ""
    if query_spec:
        retrieval_specs = query_spec.get("retrieval_specs", []) if isinstance(query_spec, dict) else []
        query_spec_context = f"""
Structured Query Spec:
{json.dumps(query_spec, indent=2)}

Retrieval Specs:
{json.dumps(retrieval_specs, indent=2)}

Treat retrieval_specs as the execution contract for SPARQL. Generate one simple raw-fact retrieval query
for the most relevant retrieval spec. The downstream DAG operators will handle aggregation, ranking,
math, set logic, and merging.
"""
    query_spec_contract_rules = ""
    if query_spec:
        query_spec_contract_rules = """
QUERY SPEC CONTRACT RULES:
- The Structured Query Spec describes smaller retrievals and post-scan operators.
- SPARQL should retrieve raw fields needed by retrieval_specs, not compute the final answer.
- Prefer a single typed class pattern with direct properties from that class.
- Include only simple filters that reduce obvious entity/text/date/number matches from retrieval_specs.
- Do not implement operator_plan inside SPARQL.
- Do not implement merge_plan inside SPARQL.
"""
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
You are the Generate operator. Write one executable, SIMPLE SPARQL retrieval query for the RDF graph.

User Query: "{inputs.get('query')}"
Target Classes: {retrieved_classes}
Active Retrieval Spec: {json.dumps(active_retrieval_spec, indent=2)}
Schema Details: {json.dumps(pruned_schema, indent=2)}
Dynamic Schema Rules:
{schema_generation_rules}
{query_spec_context}
{query_spec_contract_rules}
{retry_context}

Return ONLY raw SPARQL text. Do not explain. Do not include <reasoning>, <think>, markdown, comments, or prose.
The first non-whitespace characters in your response must be PREFIX or SELECT.
Do not invent example people such as John Doe.

OPERATOR-FIRST RULE:
- SPARQL fetches facts.
- DAG operators compute the answer after Scan.
- Avoid SUM, AVG, MIN, MAX, GROUP BY, ORDER BY, LIMIT, formulas, nested subqueries, and complex joins.
- Use COUNT only for a direct "how many records of one class" lookup with no downstream operator_plan.
- If the full user question requires aggregation/ranking/math/set logic, SELECT the raw columns needed by those operators.
- If multiple retrieval_specs exist, generate the query for the first unresolved or most relevant retrieval spec only.

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

CRITICAL RULE 2 (RAW NUMERIC FIELDS): RDF stores values as strings. For operator-first execution,
retrieve numeric fields as raw variables such as ?amount, ?targetAmount, or ?currentAmount.
Do not cast, aggregate, group, rank, or calculate formulas in SPARQL unless there is no operator_plan.

COUNT/GROUP/RANK RULE: Do not use COUNT, GROUP BY, ORDER BY, or LIMIT when query_spec has an operator_plan.
The downstream Filter_Aggregate and Order_By operators will count, group, rank, and limit after Scan.

MONTH RULE: If the query asks "per month", "for each month", or "monthly", retrieve the raw date field.
The downstream operators should perform month extraction/grouping.

CRITICAL RULE 3 (CASE-INSENSITIVE FILTERS): When filtering by text or IDs, you MUST use lowercase comparison.
Example: `FILTER(CONTAINS(LCASE(STR(?id)), "inv-001"))`.

CRITICAL RULE 4 (NEGATION): If the user query contains words like "never", "not", "excluding", "without", or "no X", you MUST use `FILTER NOT EXISTS {{ }}` or `MINUS {{ }}` to ensure those records are excluded.

CRITICAL RULE 5 (LABELS OVER IRIs): For any controlled-vocabulary class (InvestmentType, Sector, Segment, RiskCategory), always follow the label property to get the human-readable string.


"""

    api_logger.log_call(inputs.get('query'), "Generate")
    request = {
        "model": model,
        "messages": build_llm_messages("generate", prompt),
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
