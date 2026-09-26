import json
import sqlite3
from typing import Dict, Any, Tuple
import os
import re

def parse_llm_json_with_error(raw_text: str, default: Any, context: str) -> Tuple[Any, str]:
    text = (raw_text or "").strip()
    if not text:
        error = "empty response"
        print(f"   [!] Failed to parse JSON for {context}: {error}")
        return default, error

    clean = text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    candidates = [clean]
    object_start = clean.find("{")
    object_end = clean.rfind("}")
    if object_start != -1 and object_end > object_start:
        candidates.append(clean[object_start:object_end + 1])

    last_error = ""
    for candidate in candidates:
        try:
            return json.loads(candidate), ""
        except Exception as e:
            last_error = str(e)

    decoder = json.JSONDecoder()
    for start, char in enumerate(clean):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(clean[start:])
            if isinstance(parsed, dict):
                return parsed, ""
        except json.JSONDecodeError as e:
            last_error = str(e)

    preview = clean[:300].replace("\n", " ")
    print(f"   [!] Failed to parse JSON for {context}: {last_error}. Response preview: {preview}")
    return default, last_error

def parse_llm_json(raw_text: str, default: Any, context: str) -> Any:
    parsed, _ = parse_llm_json_with_error(raw_text, default, context)
    return parsed


SQL_TABLE_KEYWORDS = {
    "ATOM_ENTITY_INVESTOR_PROFILE_001": [
        "investor", "profile", "risk tolerance", "time horizon", "sector focus",
        "segment", "category", "investment goal", "investor name"
    ],
    "ATOM_ENTITY_PORTFOLIO_HEALTH_001": [
        "portfolio health", "goal match", "risk score", "liquidity",
        "diversification", "risk-pressure", "risk pressure"
    ],
    "ATOM_EVENT_REBALANCING_ACTION_001": [
        "rebalancing action", "rebalance", "allocation", "target allocation",
        "current allocation", "action", "amount"
    ],
    "ATOM_EVENT_SCENARIO_REBALANCING_001": [
        "scenario", "scenario rebalancing", "triggered action", "affected assets",
        "new allocation", "rationale"
    ],
    "ATOM_ENTITY_PORTFOLIO_HOLDING_001": [
        "holding", "portfolio holding", "investment type", "investment name",
        "sector", "purchase date", "cost", "current value", "returns",
        "dividends", "taxes"
    ],
    "ATOM_ENTITY_SECTOR_ALLOCATION_001": [
        "sector allocation", "allocation pct", "total investment", "sector"
    ],
    "ATOM_ENTITY_INVESTMENT_GOAL_001": [
        "goal", "investment goal", "target amount", "current value", "progress",
        "shortfall", "time to goal", "annual return", "post tax", "sharpe",
        "volatility", "standard deviation"
    ],
    "ATOM_EVENT_CASH_FLOW_001": [
        "cash flow", "cash-flow", "cashflow", "date", "source", "wallet",
        "transaction", "amount"
    ],
}


def _schema_table_names(sql_schema: Dict[str, Any]) -> list[str]:
    return sorted(sql_schema.keys()) if isinstance(sql_schema, dict) else []


def _select_relevant_sql_schema(inputs: Dict[str, Any]) -> Tuple[Dict[str, Any], list[str]]:
    sql_schema = inputs.get("sql_schema") or inputs.get("global_schema") or {}
    if not isinstance(sql_schema, dict) or not sql_schema:
        return {}, []

    query = str(inputs.get("query", "")).lower()
    query_spec = inputs.get("query_spec", {}) if isinstance(inputs.get("query_spec", {}), dict) else {}
    spec_text = json.dumps(query_spec, ensure_ascii=False).lower()
    bound_text = json.dumps(inputs.get("bound_inputs", {}), ensure_ascii=False).lower()
    combined = f"{query} {spec_text} {bound_text}"

    relevant = []
    for table_name, keywords in SQL_TABLE_KEYWORDS.items():
        if table_name in sql_schema and any(keyword in combined for keyword in keywords):
            relevant.append(table_name)

    for table_name, table_schema in sql_schema.items():
        if table_name.lower() in combined:
            relevant.append(table_name)
            continue
        for column_name in table_schema.get("column_names", []):
            if str(column_name).lower() in combined:
                relevant.append(table_name)
                break

    if "investor" in combined and "ATOM_ENTITY_INVESTOR_PROFILE_001" in sql_schema:
        relevant.append("ATOM_ENTITY_INVESTOR_PROFILE_001")

    relevant = sorted(dict.fromkeys(relevant))
    if not relevant:
        relevant = _schema_table_names(sql_schema)

    return {table_name: sql_schema[table_name] for table_name in relevant}, relevant

def semantic_generate_sql(inputs: Dict[str, Any], client: Any, model: str) -> Dict[str, Any]:
    """
    Generates a SQL query based on the Query_Spec and user query.
    Mirrors the semantic_generate_sparql operator.
    """
    query = inputs.get("query", "")
    root_query = inputs.get("root_query", "") or query
    query_spec = inputs.get("query_spec", {})
    sql_schema = inputs.get("sql_schema") or inputs.get("global_schema", {})
    pruned_sql_schema, relevant_tables = _select_relevant_sql_schema(inputs)
    logic_feedback = inputs.get("logic_feedback", "")
    bound_inputs = inputs.get("bound_inputs", {})
    print(f"[SQL SCHEMA] Relevant tables: {relevant_tables}")
    
    prompt = f"""
You are the SQL Generate operator. Your task is to generate a valid SQLite SQL query to answer the user's question.

User Query: {query}
Original User Query Context: {root_query}
Query Spec: {json.dumps(query_spec, indent=2)}

SQLite Physical Schema:
{json.dumps(pruned_sql_schema or sql_schema, indent=2)}

CRITICAL SQL SCHEMA RULES:
- Use ONLY tables present in the provided SQLite Physical Schema.
- Use ONLY columns present in those tables.
- Use exact physical table names such as ATOM_ENTITY_INVESTOR_PROFILE_001.
- Use exact snake_case physical column names such as investor_id, investor_name, risk_tolerance.
- Never invent semantic table names such as Investor, PortfolioHealth, CashFlow, PortfolioHolding, InvestmentGoal, RiskTolerance, or TimeHorizon.
- Never use KG-style field names such as investorId, investorName, riskTolerance, timeHorizon, progressPct, or currentValue.
- Generate SQLite-compatible SQL.
- Use investor_id as the common join key when joining investor-related tables.
- Do not confuse KG class/property names with SQLite table/column names.
- Treat User Query and Query Spec as the local subquery scope.
- Use Original User Query Context only for shared context such as the year or the outer question wording.
- Do not add sibling conditions from the original decomposed query unless they are explicitly present in User Query or Query Spec.

Bound Upstream Inputs (Values from previous nodes):
{json.dumps(bound_inputs, indent=2)}
Use these bound inputs in WHERE clauses if provided, matching values to real physical columns such as investor_id.
If Bound Upstream Inputs are non-empty, they are hard constraints from upstream nodes.
Do not recompute a broader universe when the subquery is clearly meant to refine, subtract from, or select within those upstream values.
If an upstream input is a list of category-like or investor-like values, constrain the SQL to those values with IN/NOT IN logic where appropriate.

QUERY SPEC CONTRACT RULES:
- Treat Query Spec as the semantic contract for the SQL query, not as optional guidance.
- Return every field in query_spec["output_schema"] using the same aliases whenever possible.
- Implement every measure in query_spec["measures"].
- Respect per_entity_operation and final_operation exactly.
- If a group_by item uses bucket_strategy, build explicit CASE-based bucket labels and group by those labels rather than the raw numeric field.
- For ranking queries, order by the ranking metric in the specified direction and apply the ranking limit after aggregation.

AGGREGATION GRAIN RULES (these decide whether the numbers are right):
- If query_spec["fanout_control"]["required"] is true, or grain.pre_aggregate_by is non-empty,
  you MUST use two-level aggregation. A single flat join is WRONG in that case: joining an entity
  table to one-to-many tables repeats each entity once per related record, so a final AVG or SUM
  is weighted by related-record counts instead of by entity.
- Two-level pattern to follow exactly:
    WITH m1 AS (
      SELECT <entity_key>, <per_entity_operation>(<field>) AS <measure_alias>
      FROM <that measure's own source table>
      GROUP BY <entity_key>
    ),
    m2 AS ( ... one CTE per source table, each grouped by <entity_key> ... )
    SELECT b.<group_field> AS <group_alias>,
           <final_operation>(m1.<measure_alias>) AS <output_alias>,
           <final_operation>(m2.<measure_alias>) AS <output_alias>
    FROM <base entity table> AS b
    LEFT JOIN m1 ON b.<entity_key> = m1.<entity_key>
    LEFT JOIN m2 ON b.<entity_key> = m2.<entity_key>
    GROUP BY b.<group_field>
- Build ONE CTE per measure source table. Never aggregate two different source tables in the same
  flat FROM/JOIN chain.
- Apply each measure's per_entity_operation inside its CTE and its final_operation in the outer query.
  When final_operation is AVG, the outer query must use AVG, never SUM.
- For grouped comparative queries without explicit total language, do not collapse per-entity measures
  into group totals unless Query Spec explicitly requires SUM.

NULL GROUP RULES:
- If query_spec["preserve_null_groups"] is true, keep the group whose value is NULL as its own output row.
- Do not add "WHERE <group_field> IS NOT NULL" and do not filter it out with an inner join.
- Take the grouping field from the base entity table so entities with no related records still appear.

"""
    if logic_feedback:
        prompt += f"Previous Failure Feedback:\n{logic_feedback}\nFix the query based on this feedback.\n"
        
    prompt += """
Return ONLY a JSON object with this exact structure:
{
  "sql": "SELECT ...",
  "reasoning": "Brief explanation of the SQL logic."
}
Do not include any other text.
"""
    
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        response = client.chat.completions.create(**request)
        raw_text = response.choices[0].message.content
        result, parse_error = parse_llm_json_with_error(raw_text, {"sql": "", "reasoning": "JSON parse failed"}, "Generate_SQL")
        if "sql" not in result:
            result["sql"] = ""
        result["sql_schema_tables"] = _schema_table_names(sql_schema)
        result["relevant_tables"] = relevant_tables
        result["raw_response_preview"] = (raw_text or "")[:500]
        if parse_error:
            result["parse_error"] = parse_error
        print(f"[SQL GENERATE] Using physical tables: {relevant_tables}")
        print(f"[SQL GENERATE] Generated SQL: {result.get('sql', '')}")
        return result
    except Exception as e:
        print(f"   [!] Generate_SQL API error: {e}")
        return {"sql": "", "reasoning": str(e), "error": str(e)}


def semantic_pre_scan_validate_sql(inputs: Dict[str, Any], client: Any, model: str) -> Dict[str, Any]:
    """
    Validates the generated SQL for syntax and logical errors before execution.
    Mirrors semantic_pre_scan_validate.
    """
    sql = inputs.get("sql", "")
    query = inputs.get("query", "")
    root_query = inputs.get("root_query", "") or query
    query_spec = inputs.get("query_spec", {})
    sql_schema = inputs.get("sql_schema") or inputs.get("global_schema", {})
    schema_tables = _schema_table_names(sql_schema)
    
    if not sql:
        return {"pre_scan_validation": {"is_valid": False, "reason": "No SQL provided.", "severity": "hard_error"}}
        
    prompt = f"""
You are the SQL Pre_Scan_Validate operator. Verify if the following SQL query is valid, safe, and logically aligns with the query.

User Query: {query}
Original User Query Context: {root_query}
SQL Query: {sql}
Query Spec: {json.dumps(query_spec, indent=2)}
SQLite Physical Schema:
{json.dumps(sql_schema, indent=2)}

Check for:
1. Syntax errors
2. Missing or incorrect table/column names based on the provided SQLite Physical Schema
3. Dangerous cartesian products
4. Semantic/KG table or column names that do not physically exist in SQLite
5. Query Spec contract violations:
   - missing output_schema aliases
   - grouped comparative queries that skip the requested final grouping
   - ranking queries missing ORDER BY/LIMIT for the requested metric
   - pre_aggregate_by queries that appear to use one flat multi-table aggregation instead of staged aggregation

Reject any SQL that uses tables outside this exact list:
{schema_tables}

Return ONLY a JSON object:
{{
  "is_valid": true/false,
  "reason": "Explanation of any issues found, or 'Valid' if none.",
  "severity": "hard_error" | "repairable_warning" | "valid",
  "rewrite_hint": "Instructions for the Generate operator on how to fix it (if invalid)"
}}
"""
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        response = client.chat.completions.create(**request)
        raw_text = response.choices[0].message.content
        result = parse_llm_json(raw_text, {"is_valid": False, "reason": "JSON parse error", "severity": "hard_error"}, "Pre_Scan_Validate_SQL")
        if "is_valid" not in result:
             result["is_valid"] = False
        return {"pre_scan_validation": result}
    except Exception as e:
        return {"pre_scan_validation": {"is_valid": False, "reason": str(e), "severity": "hard_error"}}


def pre_programmed_scan_sql(inputs: Dict[str, Any], db_path: str) -> Dict[str, Any]:
    sql = inputs.get("sql", "")

    if not sql.strip():
        return {
            "status": "error",
            "error_type": "empty_sql",
            "error_message": "Empty SQL query",
            "data": []
        }
    if not db_path or db_path == ":memory:":
        return {
            "status": "error",
            "error_type": "db_path_error",
            "error_message": f"Invalid SQLite database path for SQL pipeline: {db_path!r}",
            "data": []
        }
    if not os.path.exists(db_path):
        return {
            "status": "error",
            "error_type": "db_path_error",
            "error_message": f"SQLite database file does not exist: {db_path}",
            "data": []
        }

    conn = None

    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        return {
            "status": "error",
            "error_type": "db_connection_error",
            "error_message": f"SQLite DB connection error: {e}",
            "data": []
        }

    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(sql)
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]

        return {
            "status": "success",
            "error_type": "",
            "row_count": len(data),
            "data": data,
            "error_message": ""
        }

    except sqlite3.OperationalError as e:
        message = str(e)
        if "no such table" in message.lower():
            error_type = "sql_no_such_table"
        elif "no such column" in message.lower():
            error_type = "sql_no_such_column"
        else:
            error_type = "sql_execution_error"
        return {
            "status": "error",
            "error_type": error_type,
            "error_message": f"SQLite SQL execution error: {e}",
            "data": []
        }

    except sqlite3.Error as e:
        return {
            "status": "error",
            "error_type": "sql_execution_error",
            "error_message": f"SQLite SQL execution error: {e}",
            "data": []
        }

    except Exception as e:
        return {
            "status": "error",
            "error_type": "unexpected_sql_scan_error",
            "error_message": f"{type(e).__name__}: {e}",
            "data": []
        }

    finally:
        if conn is not None:
            conn.close()
