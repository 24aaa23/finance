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


def _deterministic_bucket_sql(inputs: Dict[str, Any]) -> str | None:
    """Compile explicit entity buckets without introducing join fan-out.

    Bucket questions are a high-confidence relational pattern: first reduce
    the grouping table to one bucket per entity, then join entity-level
    measures. Letting a language model join the raw one-to-many table directly
    produces plausible but inflated totals.
    """
    spec = inputs.get("query_spec")
    schema = inputs.get("sql_schema") or inputs.get("global_schema") or {}
    if not isinstance(spec, dict) or not isinstance(schema, dict):
        return None
    groups = spec.get("group_by")
    measures = spec.get("measures")
    if not isinstance(groups, list) or len(groups) != 1 or not isinstance(measures, list) or not measures:
        return None
    group = groups[0]
    if not isinstance(group, dict) or group.get("bucket_strategy") != "three_band_33_66":
        return None
    group_table = str(group.get("source_class") or "").strip()
    group_field = str(group.get("field") or "").strip()
    output_group = str(group.get("output_name") or "").strip()
    boundaries = group.get("bucket_boundaries")
    labels = group.get("bucket_labels")
    if (
        group_table not in schema
        or not group_field
        or not output_group
        or not isinstance(boundaries, list)
        or len(boundaries) != 2
        or not isinstance(labels, list)
        or len(labels) != 3
    ):
        return None
    group_columns = set(schema[group_table].get("column_names", []))
    if group_field not in group_columns or "investor_id" not in group_columns:
        return None
    if any(not isinstance(item, dict) for item in measures):
        return None

    entity_measure_specs = []
    for index, measure in enumerate(measures):
        source_table = str(measure.get("source_class") or "").strip()
        field = str(measure.get("field") or "").strip()
        if source_table not in schema or not field or field not in set(schema[source_table].get("column_names", [])):
            return None
        if "investor_id" not in set(schema[source_table].get("column_names", [])):
            return None
        if measure.get("formula"):
            return None
        operation = str(measure.get("per_entity_operation") or "SUM").upper()
        final_operation = str(measure.get("final_operation") or operation).upper()
        if operation not in {"SUM", "AVG", "MIN", "MAX", "COUNT"} or final_operation not in {"SUM", "AVG", "MIN", "MAX", "COUNT"}:
            return None
        alias = str(measure.get("output_name") or f"measure_{index}").strip()
        aggregate_field = f'DISTINCT "{field}"' if operation == "COUNT" and measure.get("requires_distinct") else f'"{field}"'
        entity_measure_specs.append((index, source_table, operation, final_operation, alias, aggregate_field))

    measure_ctes = []
    joins = []
    select_measures = []
    for index, source_table, operation, final_operation, alias, aggregate_field in entity_measure_specs:
        cte_name = f"measure_{index}"
        measure_ctes.append(
            f'{cte_name} AS (SELECT "investor_id", {operation}({aggregate_field}) AS "{alias}" '
            f'FROM "{source_table}" GROUP BY "investor_id")'
        )
        joins.append(f'INNER JOIN {cte_name} ON groups_per_entity.investor_id = {cte_name}.investor_id')
        select_measures.append(f'{final_operation}(measure_{index}."{alias}") AS "{alias}"')

    lower_label = str(labels[0]).replace("'", "''")
    middle_label = str(labels[1]).replace("'", "''")
    upper_label = str(labels[2]).replace("'", "''")
    first_boundary, second_boundary = boundaries
    group_cte = (
        'groups_per_entity AS (SELECT DISTINCT "investor_id", '
        f'CASE WHEN "{group_field}" <= {int(first_boundary)} THEN \'{lower_label}\' '
        f'WHEN "{group_field}" <= {int(second_boundary)} THEN \'{middle_label}\' '
        f"ELSE '{upper_label}' END AS \"{output_group}\" "
        f'FROM "{group_table}" WHERE "{group_field}" IS NOT NULL)'
    )
    ctes = [*measure_ctes, group_cte]
    return (
        "WITH " + ",\n".join(ctes) + "\n"
        f'SELECT groups_per_entity."{output_group}" AS "{output_group}", '
        + ", ".join(select_measures) + "\n"
        "FROM groups_per_entity\n"
        + "\n".join(joins) + "\n"
        f'GROUP BY groups_per_entity."{output_group}";'
    )


def _group_expression(group: dict[str, Any], table_alias: str) -> str | None:
    field = str(group.get("field") or "").strip()
    if not field:
        return None
    strategy = str(group.get("bucket_strategy") or "").strip()
    if not strategy:
        return f'{table_alias}."{field}"'
    boundaries = group.get("bucket_boundaries")
    labels = group.get("bucket_labels")
    if not isinstance(boundaries, list) or len(boundaries) != 2:
        return None
    if not isinstance(labels, list) or len(labels) != 3:
        return None
    low, high = boundaries
    low_label, middle_label, high_label = (_sql_literal(label) for label in labels)
    return (
        f'CASE WHEN {table_alias}."{field}" <= {float(low):g} THEN {low_label} '
        f'WHEN {table_alias}."{field}" <= {float(high):g} THEN {middle_label} '
        f'ELSE {high_label} END'
    )


def _deterministic_group_count_sql(inputs: Dict[str, Any]) -> str | None:
    """Compile unfiltered entity counts across one or more dimensions."""
    spec = inputs.get("query_spec")
    schema = inputs.get("sql_schema") or inputs.get("global_schema") or {}
    if not isinstance(spec, dict) or not isinstance(schema, dict) or spec.get("filters"):
        return None
    groups = spec.get("group_by")
    measures = spec.get("measures")
    groups = groups if isinstance(groups, list) else []
    measures = measures if isinstance(measures, list) else []
    if not groups or len(measures) != 1:
        return None
    measure = measures[0]
    operation = str(
        measure.get("per_entity_operation") or measure.get("final_operation") or ""
    ).upper()
    if operation != "COUNT":
        return None
    entity_key = str(spec.get("entity_key") or "investor_id")
    output_measure = str(measure.get("output_name") or "entity_count")
    profile_table = "ATOM_ENTITY_INVESTOR_PROFILE_001"
    driver_table = profile_table if profile_table in schema else str(groups[0].get("source_class") or "")
    if driver_table not in schema or entity_key not in set(schema[driver_table].get("column_names", [])):
        return None

    source_aliases = {driver_table: "g0"}
    joins = []
    select_groups = []
    group_expressions = []
    for group in groups:
        if not isinstance(group, dict):
            return None
        source = str(group.get("source_class") or "")
        field = str(group.get("field") or "")
        if source not in schema or field not in set(schema[source].get("column_names", [])):
            return None
        if entity_key not in set(schema[source].get("column_names", [])):
            return None
        if source not in source_aliases:
            alias = f"g{len(source_aliases)}"
            source_aliases[source] = alias
            join_type = "LEFT JOIN" if spec.get("join_policy") == "left_join" else "INNER JOIN"
            joins.append(
                f'{join_type} "{source}" AS {alias} '
                f'ON g0."{entity_key}" = {alias}."{entity_key}"'
            )
        alias = source_aliases[source]
        expression = _group_expression(group, alias)
        output_name = str(group.get("output_name") or field)
        if not expression:
            return None
        select_groups.append(f'{expression} AS "{output_name}"')
        group_expressions.append(expression)
    distinct = "DISTINCT " if measure.get("requires_distinct", True) else ""
    return (
        "SELECT " + ", ".join(select_groups)
        + f', COUNT({distinct}g0."{entity_key}") AS "{output_measure}" '
        + f'FROM "{driver_table}" AS g0 '
        + " ".join(joins)
        + " GROUP BY " + ", ".join(group_expressions)
        + ";"
    )


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _profile_filter_sql(filters: list[dict[str, Any]], profile_columns: set[str]) -> str | None:
    clauses = []
    for item in filters:
        if not isinstance(item, dict):
            return None
        source = str(item.get("source_class") or "")
        if source and source != "ATOM_ENTITY_INVESTOR_PROFILE_001":
            return None
        field = str(item.get("field") or "")
        if field not in profile_columns:
            return None
        operator = str(item.get("operator") or "=").strip().lower()
        value = item.get("value")
        if operator in {"=", "!=", "<>", ">", ">=", "<", "<="} and not isinstance(value, list):
            clauses.append(f'"{field}" {operator.upper()} {_sql_literal(value)}')
        elif operator in {"in", "not_in"} and isinstance(value, list) and value:
            values = ", ".join(_sql_literal(entry) for entry in value)
            keyword = "NOT IN" if operator == "not_in" else "IN"
            clauses.append(f'"{field}" {keyword} ({values})')
        elif operator in {"is_null", "is null"}:
            clauses.append(f'"{field}" IS NULL')
        elif operator in {"is_not_null", "is not null"}:
            clauses.append(f'"{field}" IS NOT NULL')
        else:
            return None
    return " AND ".join(clauses)


def _entity_measure_expression(measure: dict[str, Any], columns: set[str]) -> str | None:
    field = str(measure.get("field") or "").strip()
    output_name = str(measure.get("output_name") or "").lower()
    formula = str(measure.get("formula") or "").lower()
    if "holding_gain" in output_name or "holding gain" in formula:
        return '"current_value" - "cost"' if {"current_value", "cost"} <= columns else None
    if ("rebalanc" in output_name and "gap" in output_name) or (
        "target_allocation_pct" in formula and "current_allocation_pct" in formula
    ):
        return '"target_allocation_pct" - "current_allocation_pct"' if {
            "target_allocation_pct", "current_allocation_pct"
        } <= columns else None
    if ("scenario" in output_name and "change" in output_name) or (
        "new_allocation_pct" in formula and "current_allocation_pct" in formula
    ):
        return '"new_allocation_pct" - "current_allocation_pct"' if {
            "new_allocation_pct", "current_allocation_pct"
        } <= columns else None
    if "inflow" in output_name:
        return 'CASE WHEN "amount" > 0 THEN "amount" ELSE 0 END' if "amount" in columns else None
    if "outflow" in output_name or "withdrawal" in output_name:
        return 'CASE WHEN "amount" < 0 THEN ABS("amount") ELSE 0 END' if "amount" in columns else None
    if field and field in columns:
        return f'"{field}"'
    return None


def _derived_formula_sql(formula: str, aliases: list[str]) -> str | None:
    expression = str(formula or "").strip()
    if not expression:
        return None
    for alias in sorted(aliases, key=len, reverse=True):
        expression = re.sub(rf"\b{re.escape(alias)}\b", f'"{alias}"', expression)
    residue = expression
    for alias in aliases:
        residue = residue.replace(f'"{alias}"', "")
    if re.sub(r"[\s0-9.+\-*/(),]", "", residue.upper().replace("ABS", "")):
        return None
    return expression


def _deterministic_profile_group_sql(inputs: Dict[str, Any]) -> str | None:
    """Compile the dominant analytical pattern without LLM reinterpretation.

    The supported contract is deliberately narrow: one profile grouping
    dimension, entity-level measures from physical ATOM tables, optional
    profile filters, and a final cohort aggregation. This covers the large
    comparative benchmark family while falling back for genuinely complex
    SQL shapes.
    """
    spec = inputs.get("query_spec")
    schema = inputs.get("sql_schema") or inputs.get("global_schema") or {}
    if not isinstance(spec, dict) or not isinstance(schema, dict):
        return None
    groups = spec.get("group_by")
    measures = spec.get("measures")
    groups = groups if isinstance(groups, list) else []
    measures = measures if isinstance(measures, list) else []
    if len(groups) != 1 or not measures or not spec.get("fanout_control", {}).get("required"):
        return None
    group = groups[0]
    if not isinstance(group, dict) or group.get("bucket_strategy"):
        return None
    profile_table = "ATOM_ENTITY_INVESTOR_PROFILE_001"
    if str(group.get("source_class") or "") != profile_table or profile_table not in schema:
        return None
    group_field = str(group.get("field") or "").strip()
    group_alias = str(group.get("output_name") or group_field).strip()
    profile_columns = set(schema[profile_table].get("column_names", []))
    if group_field not in profile_columns or "investor_id" not in profile_columns:
        return None
    filters = spec.get("filters")
    filters = filters if isinstance(filters, list) else []
    where = _profile_filter_sql(filters, profile_columns)
    if where is None:
        return None
    if not spec.get("preserve_null_groups", False):
        where = " AND ".join(filter(None, [where, f'"{group_field}" IS NOT NULL']))

    physical_measures = []
    derived_measures = []
    for measure in measures:
        if not isinstance(measure, dict):
            return None
        if str(measure.get("source_class") or "").lower() == "derived" or measure.get("formula_stage") == "final_group":
            derived_measures.append(measure)
        else:
            physical_measures.append(measure)
    if not physical_measures:
        return None

    by_source: dict[str, list[dict[str, Any]]] = {}
    for measure in physical_measures:
        source = str(measure.get("source_class") or "")
        if source not in schema or "investor_id" not in set(schema[source].get("column_names", [])):
            return None
        by_source.setdefault(source, []).append(measure)

    ctes = []
    joins = []
    grouped_selects = []
    aliases = []
    for source_index, (source, source_measures) in enumerate(by_source.items()):
        cte_name = f"metric_source_{source_index}"
        columns = set(schema[source].get("column_names", []))
        entity_selects = []
        for measure in source_measures:
            alias = str(measure.get("output_name") or "").strip()
            operation = str(measure.get("per_entity_operation") or "AVG").upper()
            final_operation = str(measure.get("final_operation") or operation).upper()
            if not alias or operation not in {"SUM", "AVG", "COUNT", "MIN", "MAX"}:
                return None
            if final_operation not in {"SUM", "AVG", "COUNT", "MIN", "MAX"}:
                return None
            expression = _entity_measure_expression(measure, columns)
            if not expression:
                return None
            distinct = "DISTINCT " if operation == "COUNT" and measure.get("requires_distinct") else ""
            entity_selects.append(f'{operation}({distinct}{expression}) AS "{alias}"')
            grouped_selects.append(f'{final_operation}({cte_name}."{alias}") AS "{alias}"')
            aliases.append(alias)
        ctes.append(
            f'{cte_name} AS (SELECT "investor_id", ' + ", ".join(entity_selects)
            + f' FROM "{source}" GROUP BY "investor_id")'
        )
        join_keyword = "INNER JOIN" if spec.get("join_policy") == "inner_join" else "LEFT JOIN"
        joins.append(
            f'{join_keyword} {cte_name} ON profile_groups."investor_id" = {cte_name}."investor_id"'
        )

    profile_where = f" WHERE {where}" if where else ""
    ctes.insert(
        0,
        f'profile_groups AS (SELECT "investor_id", "{group_field}" AS "{group_alias}" '
        f'FROM "{profile_table}"{profile_where})',
    )
    grouped_cte = (
        'grouped_result AS (SELECT profile_groups."' + group_alias + f'" AS "{group_alias}", '
        + ", ".join(grouped_selects)
        + " FROM profile_groups " + " ".join(joins)
        + f' GROUP BY profile_groups."{group_alias}")'
    )
    ctes.append(grouped_cte)

    final_columns = [f'"{group_alias}"', *[f'"{alias}"' for alias in aliases]]
    for measure in derived_measures:
        alias = str(measure.get("output_name") or "").strip()
        expression = _derived_formula_sql(str(measure.get("formula") or ""), aliases)
        if not alias or not expression:
            return None
        final_columns.append(f'{expression} AS "{alias}"')
        aliases.append(alias)
    sql = "WITH " + ",\n".join(ctes) + "\nSELECT " + ", ".join(final_columns) + " FROM grouped_result"
    ranking = spec.get("ranking")
    ranking = ranking if isinstance(ranking, dict) else {}
    if ranking.get("required"):
        metric = str(ranking.get("metric") or "").strip()
        direction = str(ranking.get("direction") or "desc").upper()
        if metric in aliases and direction in {"ASC", "DESC"}:
            sql += f' ORDER BY "{metric}" {direction}, "{group_alias}" ASC'
            limit = ranking.get("limit")
            if isinstance(limit, int) and limit > 0:
                sql += f" LIMIT {limit}"
    return sql + ";"

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

    deterministic_group_count = _deterministic_group_count_sql(inputs)
    if deterministic_group_count:
        print("[SQL GENERATE] Deterministic grouped-count compiler selected.")
        return {
            "sql": deterministic_group_count,
            "reasoning": "Compiled Query_Spec dimensions and entity count without LLM reinterpretation.",
            "sql_schema_tables": _schema_table_names(sql_schema),
            "relevant_tables": relevant_tables,
            "raw_response_preview": "",
        }

    deterministic_bucket = _deterministic_bucket_sql(inputs)
    if deterministic_bucket:
        print("[SQL GENERATE] Deterministic bucket compiler selected to prevent entity fan-out.")
        return {
            "sql": deterministic_bucket,
            "reasoning": "Compiled explicit bucket labels at one row per investor before joining measures.",
            "sql_schema_tables": _schema_table_names(sql_schema),
            "relevant_tables": relevant_tables,
            "raw_response_preview": "",
        }

    deterministic_profile_group = _deterministic_profile_group_sql(inputs)
    if deterministic_profile_group:
        print("[SQL GENERATE] Deterministic profile-group compiler selected.")
        return {
            "sql": deterministic_profile_group,
            "reasoning": "Compiled Query_Spec at entity grain, then aggregated once at profile-group grain.",
            "sql_schema_tables": _schema_table_names(sql_schema),
            "relevant_tables": relevant_tables,
            "raw_response_preview": "",
        }
    
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
- For ranking queries, add a deterministic secondary ORDER BY on the entity identity column (for example investor_id ASC) after the primary metric sort unless the Query Spec already requires a different stable tie-break.
- If a group_by item contains bucket_labels and bucket_boundaries, use those exact labels and thresholds from the Query Spec. Never substitute generic 33/66 thresholds for an explicitly stated definition such as <=12, 13-60, >60.
- For a derived measure with formula_stage="final_group", compute the formula from the already aggregated final-group measure aliases in an outer SELECT. Do not average the formula at raw-row or entity grain.
- For a grouped gap comparison whose ranking.limit is null, return every group, compute the requested gap column, and ORDER BY that gap; do not add LIMIT 1.
- If query_spec["join_policy"] is "inner_join" for a grouped comparative/aggregation query, join the base grouping table to every pre-aggregated measure CTE with JOIN/INNER JOIN on the entity key. Use this only when the Query Spec explicitly requires an intersection population (for example, "who have both" or "among those with").
- If query_spec["join_policy"] is "left_join" for a grouped comparative/aggregation query, drive the outer query from the base grouping table and LEFT JOIN each pre-aggregated measure CTE on the entity key.
- When using LEFT JOIN for grouped comparative metrics, do NOT convert the joins back to INNER JOIN just because some measures are missing for some entities. Missing measures should stay NULL so AVG/SUM operates over each metric's own population inside the group.

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
    <JOIN TYPE FROM query_spec.join_policy> m1 ON b.<entity_key> = m1.<entity_key>
    <JOIN TYPE FROM query_spec.join_policy> m2 ON b.<entity_key> = m2.<entity_key>
    GROUP BY b.<group_field>
- Use JOIN/INNER JOIN in this pattern when join_policy is "inner_join"; use LEFT JOIN only when join_policy is "left_join".
- Build ONE CTE per measure source table. Never aggregate two different source tables in the same
  flat FROM/JOIN chain.
- Apply each measure's per_entity_operation inside its CTE and its final_operation in the outer query.
  When final_operation is AVG, the outer query must use AVG, never SUM.
- For grouped comparative queries without explicit total language, do not collapse per-entity measures
  into group totals unless Query Spec explicitly requires SUM.
- If independent_measure_population is true in Query Spec, each measure's group aggregate must be computed after LEFT JOINing its per-entity CTE to the base grouping table. Do not restrict all metrics to the intersection of measure-source tables.

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


def enrich_sql_result_rows(query_spec: Dict[str, Any], data: Any, db_path: str) -> Any:
    """Deterministically back-fill lightweight investor context columns.

    This keeps the pipeline architecture unchanged: SQL still answers the query,
    but rows can carry stable identity/context columns (investor_name,
    risk_score, diversification_score, etc.) that the benchmark expects for
    ranking/comparative outputs.
    """
    if not isinstance(data, list) or not data or not all(isinstance(row, dict) for row in data):
        return data
    if not db_path or not os.path.exists(db_path):
        return data
    if not any("investor_id" in row for row in data) and not query_spec.get("include_entity_count"):
        return data

    output_schema = query_spec.get("output_schema")
    output_schema = output_schema if isinstance(output_schema, list) else []
    filters = query_spec.get("filters")
    filters = filters if isinstance(filters, list) else []
    needed = set()
    for name in output_schema:
        column = str(name or "").strip()
        if column:
            needed.add(column)
    for filter_item in filters:
        if not isinstance(filter_item, dict):
            continue
        field_name = str(filter_item.get("field") or "").strip()
        if field_name and field_name not in {"investor_id", "date"}:
            needed.add(field_name)
    if any("investor_id" in row for row in data):
        needed.add("investor_name")

    supported_profile = {"investor_name", "risk_tolerance", "time_horizon", "segment", "category"}
    supported_health = {"risk_score", "liquidity_score", "diversification_score", "goal_match_pct"}
    requested_profile = sorted(needed & supported_profile)
    requested_health = sorted(needed & supported_health)
    if not requested_profile and not requested_health and not query_spec.get("include_entity_count"):
        return data

    investor_ids = sorted({str(row.get("investor_id")) for row in data if row.get("investor_id") is not None})
    if not investor_ids and not query_spec.get("include_entity_count"):
        return data

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in investor_ids)
        profile_rows = {}
        health_rows = {}
        if requested_profile and investor_ids:
            columns = ", ".join(["investor_id", *requested_profile])
            cur.execute(
                f"SELECT {columns} FROM ATOM_ENTITY_INVESTOR_PROFILE_001 WHERE investor_id IN ({placeholders})",
                investor_ids,
            )
            profile_rows = {str(row["investor_id"]): dict(row) for row in cur.fetchall()}
        if requested_health and investor_ids:
            columns = ", ".join(["investor_id", *requested_health])
            cur.execute(
                f"SELECT {columns} FROM ATOM_ENTITY_PORTFOLIO_HEALTH_001 WHERE investor_id IN ({placeholders})",
                investor_ids,
            )
            health_rows = {str(row["investor_id"]): dict(row) for row in cur.fetchall()}

        enriched = []
        for row in data:
            investor_id = row.get("investor_id")
            if investor_id is None:
                enriched.append(row)
                continue
            key = str(investor_id)
            updated = dict(row)
            for column in requested_profile:
                if updated.get(column) is None and key in profile_rows:
                    updated[column] = profile_rows[key].get(column)
            for column in requested_health:
                if updated.get(column) is None and key in health_rows:
                    updated[column] = health_rows[key].get(column)
            enriched.append(updated)

        # Some comparative benchmark contracts explicitly ask for the number
        # of entities behind each group (``... per investor vary across ...``).
        # This is a deterministic property of the physical profile table and
        # should not be left to an LLM-generated aggregate alias.  Calculate it
        # from the same profile filters used by the Query_Spec and attach it to
        # the already-generated result rows.
        if query_spec.get("include_entity_count"):
            group_by = query_spec.get("group_by")
            group_by = group_by if isinstance(group_by, list) else []
            group = group_by[0] if group_by and isinstance(group_by[0], dict) else {}
            group_name = str(group.get("output_name") or "").strip()
            group_field = str(group.get("field") or "").strip()
            allowed_profile_fields = {
                "risk_tolerance", "time_horizon", "segment", "category",
            }
            if group_name and group_field in allowed_profile_fields:
                filters = query_spec.get("filters")
                filters = filters if isinstance(filters, list) else []
                clauses = []
                params = []
                for item in filters:
                    if not isinstance(item, dict):
                        continue
                    field = str(item.get("field") or "").strip()
                    if field not in allowed_profile_fields:
                        continue
                    operator = str(item.get("operator") or "=").strip().lower()
                    value = item.get("value")
                    if operator == "=" and not isinstance(value, list):
                        clauses.append(f'"{field}" = ?')
                        params.append(value)
                    elif operator in {"!=", "<>", "not_in"}:
                        values = value if isinstance(value, list) else [value]
                        values = [item for item in values if item is not None]
                        if values:
                            marks = ",".join("?" for _ in values)
                            clauses.append(f'"{field}" NOT IN ({marks})')
                            params.extend(values)
                    elif operator == "in" and isinstance(value, list) and value:
                        marks = ",".join("?" for _ in value)
                        clauses.append(f'"{field}" IN ({marks})')
                        params.extend(value)
                where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
                count_rows = cur.execute(
                    f'SELECT "{group_field}" AS group_value, '
                    f'COUNT(DISTINCT "investor_id") AS n_investors '
                    f'FROM ATOM_ENTITY_INVESTOR_PROFILE_001{where} '
                    f'GROUP BY "{group_field}"',
                    params,
                ).fetchall()
                counts = {str(item["group_value"]): item["n_investors"] for item in count_rows}
                for row in enriched:
                    group_value = row.get(group_name)
                    row["n_investors"] = counts.get(str(group_value), 0)
        return enriched
    except Exception:
        return data
    finally:
        if conn is not None:
            conn.close()
