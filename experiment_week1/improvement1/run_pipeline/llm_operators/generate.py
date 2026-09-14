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
    query_spec_context = ""
    if query_spec:
        query_spec_context = f"""
Structured Query Spec:
{json.dumps(query_spec, indent=2)}

Treat this spec as guidance, not an execution engine contract. The SPARQL should implement its base_entity,
entity_key, filters, grain, group_by, measures, ranking, execution_strategy, and
output_schema whenever those fields are present, schema-grounded, and executable in one SPARQL query.
"""
    query_spec_contract_rules = ""
    if query_spec:
        query_spec_contract_rules = """
QUERY SPEC CONTRACT RULES:
- The Structured Query Spec is guidance.
- Prefer executable, schema-grounded SPARQL over over-complex plans from Query_Spec.
- Every field in query_spec["output_schema"] must appear in the final SELECT, unless there is a clearly equivalent alias.
- Every measure in query_spec["measures"] must be implemented.
- Use the exact output_name from each measure as the SELECT alias whenever possible.
- If a measure has formula != null, implement that formula exactly using formula_fields.
- Never replace a formula-based measure with COUNT.
- Never replace SUM, AVG, MIN, or MAX with COUNT unless query_spec explicitly says COUNT.
- If join_policy is "inner_join", do not use OPTIONAL + COALESCE(0) for required base/event classes.
- Group-by dimension fields are different from required base/event classes: OPTIONAL + COALESCE("NULL") is required for category/type/attribute dimensions when preserve_null_groups is true.
- Preserve the requested grouping grain exactly. If the user asks by a category/type/attribute such as investment goal, risk tolerance, source, scenario, segment, or time horizon, group by that field value, not by the owning entity ID.
- If the user asks for each individual entity such as investor, holding, goal, cash flow, or transaction, grouping by the entity ID/profile/name is valid.
- If join_policy is "left_join", OPTIONAL is allowed.
- If join_policy is "anti_join", use FILTER NOT EXISTS or MINUS.
- If grain.pre_aggregate_by is non-empty, first aggregate at that grain in subqueries, then apply final aggregation by group_by.
- If execution_strategy is "preaggregate_sparql", avoid flat multi-table joins that multiply rows.
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
    # || Updated the prompt with feedback and failed query
    prompt = f"""
You are the Generate operator. Write one executable SPARQL query for the RDF graph.

User Query: "{inputs.get('query')}"
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

COUNT RULE: If the requested measure is COUNT, do not require unrelated numeric fields. Count the typed entity variable that represents the thing being counted, for example COUNT(?cashFlow), COUNT(?holding), COUNT(?investor), or COUNT(?goal). Do not count an OPTIONAL id field because missing IDs can undercount records. Do not add `?cashFlow wm:amount ?amount` merely because CashFlow has amount. Use numeric fields only for SUM, AVG, MIN, or MAX.
Use COUNT(?entity) by default. Use COUNT(DISTINCT ?entity) only when the user asks for distinct, unique, or different values, or when query_spec["measures"][...]["requires_distinct"] is true after cleanup.

GROUPING GRAIN RULE: Group by what the user asked for. If the user asks "for each investor", grouping by investor_id/investor_profile is correct. If the user asks "by investment goal", "by risk tolerance", "by cash-flow type", "across scenario", or another category/type/attribute, group by that requested field value, not by investor_id, goal_id, cashFlowId, or another record ID.

NULL GROUP RULE: For group-by questions using "for each", "by", "per", or "across" over category/type/attribute dimensions, do not drop rows only because the group field is missing. Use OPTIONAL for the group field and COALESCE to "NULL". Example: `OPTIONAL {{ ?goal wm:timeToGoalMonths ?timeToGoalMonthsRaw . }} BIND(COALESCE(STR(?timeToGoalMonthsRaw), "NULL") AS ?timeToGoalMonths)`.

MONTH RULE: If the query asks "per month", "for each month", or "monthly", extract YYYY-MM from date strings. Use `BIND(SUBSTR(STR(?date), 1, 7) AS ?month)` and GROUP BY ?month. Never group directly by full date for month-level questions.

RANKING TIE RULE: If using ORDER BY with LIMIT, add a deterministic secondary sort on a stable selected identifier or label after the primary metric. This prevents arbitrary tied rows.

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
