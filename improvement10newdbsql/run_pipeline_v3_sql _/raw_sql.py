"""Render single-table raw retrieval contracts as deterministic SQLite SELECTs.

Names come only from the discovered schema.  Projection never adds DISTINCT or
NULL filters, so observation multiplicity and nullable fields survive retrieval.
"""

from decimal import Decimal, InvalidOperation
import math
import re
from .sql_conditions import normalize_condition


_NUMERIC_TYPES = {"number", "numeric", "integer", "int", "float", "decimal", "double", "real"}
_KEYWORDS = {
    "SELECT", "AS", "FROM", "WHERE", "AND", "OR", "NOT", "IS", "NULL", "IN",
    "BETWEEN", "CAST", "TEXT", "INSTR", "TRUE", "FALSE",
}


def quote_identifier(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("SQL identifiers must be nonempty names without NUL characters.")
    return '"' + value.replace('"', '""') + '"'


def sql_literal(value, kind="", *, allow_null=False):
    """Encode a scalar without interpreting any of its text as SQL syntax."""
    if value is None:
        if allow_null:
            return "NULL"
        raise ValueError("Comparison requires a scalar literal; use is_null for null.")
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (dict, list, tuple, set)):
        raise ValueError("Comparison requires a scalar literal.")
    if str(kind).lower() in _NUMERIC_TYPES or isinstance(value, (int, float, Decimal)):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Numeric filter requires a finite number.") from exc
        if not number.is_finite() or not math.isfinite(float(number)):
            raise ValueError("Numeric filter requires a finite number.")
        return str(number)
    if not isinstance(value, str):
        raise ValueError("Comparison requires a string, number, boolean, or null.")
    if "\x00" in value:
        raise ValueError("SQL text literals cannot contain NUL characters.")
    return "'" + value.replace("'", "''") + "'"


def render_raw_sql(retrieval, schema):
    """Return the exact single-table SELECT for a validated retrieval contract."""
    if not isinstance(retrieval, dict) or not isinstance(schema, dict):
        raise ValueError("Raw retrieval and schema must be objects.")
    table = retrieval.get("class")
    if not isinstance(table, str) or table not in schema:
        raise ValueError(f"Raw source table is not schema-valid: {table}")
    details = schema[table]
    if not isinstance(details, dict) or details.get("backend") not in {"sqlite", "duckdb"} or not isinstance(details.get("sql_table"), str):
        raise ValueError(f"Raw source must have explicit SQL table metadata: {table}")
    columns = {c["name"]: c for c in details.get("columns", [])
               if isinstance(c, dict) and isinstance(c.get("name"), str) and c["name"]}
    fields = retrieval.get("fields", [])
    if not isinstance(fields, list) or not fields or any(not isinstance(f, str) or f not in columns for f in fields):
        raise ValueError("Raw fields must be explicit, exact columns on the source table.")
    fields = list(dict.fromkeys(fields))
    for key in ("optional_fields", "entity_key"):
        names = retrieval.get(key, [])
        if not isinstance(names, list) or any(not isinstance(name, str) or name not in fields for name in names):
            raise ValueError(f"{key} must contain selected source fields.")
    for key in ("joins", "join", "group_by", "order_by", "limit", "offset", "aggregations", "distinct"):
        if retrieval.get(key):
            raise ValueError(f"Raw retrieval cannot contain computation: {key}")

    def predicate(item):
        if not isinstance(item, dict):
            raise ValueError("Filter must be a predicate object.")
        for key in ("all", "any", "not", "conditions", "filters"):
            if key not in item:
                continue
            children = item[key]
            if key == "not":
                return "NOT (" + predicate(children) + ")"
            if not isinstance(children, list) or not children:
                raise ValueError("Logical filters require nonempty predicate lists.")
            logic = "or" if key == "any" else "and" if key == "all" else str(item.get("logic", "and")).lower()
            if logic not in {"and", "or"}:
                raise ValueError("Unsupported logical filter.")
            return "(" + (" OR " if logic == "or" else " AND ").join(predicate(child) for child in children) + ")"
        field = item.get("field")
        if not isinstance(field, str) or field not in fields:
            raise ValueError(f"Filter field is not selected: {field}")
        name = quote_identifier(field)
        op = str(item.get("operator", "=")).strip().lower().replace("_", " ")
        op = {"eq": "=", "==": "=", "equals": "=", "ne": "!=", "<>": "!="}.get(op, op)
        value = item.get("value")
        if "value" in item and value is None:
            op = {"=": "is null", "!=": "is not null"}.get(op, op)
        if op in {"is null", "is not null"}:
            return name + " " + op.upper()
        metadata = columns[field]
        kind = item.get("value_type") or metadata.get("datatype", "")
        if not kind:
            declared_type = str(metadata.get("sqlite_type", "")).upper()
            if any(part in declared_type for part in ("INT", "REAL", "FLOA", "DOUB", "NUM", "DEC")):
                kind = "numeric"
        if op in {"in", "not in"}:
            if not isinstance(value, list):
                raise ValueError("IN requires a literal list, not a branch reference.")
            if not value:
                return "1" if op == "not in" else "0"
            return f"{name} {op.upper()} (" + ", ".join(sql_literal(v, kind, allow_null=True) for v in value) + ")"
        if op == "between":
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("BETWEEN requires two endpoints.")
            return f"({name} >= {sql_literal(value[0], kind)} AND {name} <= {sql_literal(value[1], kind)})"
        if op == "contains":
            return f"INSTR(CAST({name} AS TEXT), {sql_literal(value)}) > 0"
        if op not in {"=", "!=", "<", "<=", ">", ">="}:
            raise ValueError(f"Unsupported raw filter operator: {op}")
        return f"{name} {op} {sql_literal(value, kind)}"

    filters = retrieval.get("filters", [])
    if not isinstance(filters, list):
        raise ValueError("Filters must be a list.")
    filters = [normalize_condition(item) for item in filters]
    projection = ", ".join(f"{quote_identifier(field)} AS {quote_identifier(field)}" for field in fields)
    query = f"SELECT {projection} FROM {quote_identifier(details['sql_table'])}"
    if filters:
        query += " WHERE " + " AND ".join("(" + predicate(item) + ")" for item in filters)
    return query


def canonical_sql_tokens(sql):
    """Tokenize for exact-contract comparison, preserving literals and names.

    Only insignificant spacing, comments, and keyword/function case disappear.
    This deliberately does not perform semantic SQL rewrites or erase quotes.
    Malformed quotes, comments, and unsupported tokens fail closed.
    """
    if not isinstance(sql, str) or "\x00" in sql:
        raise ValueError("SQL must be text without NUL characters.")
    tokens = []
    offset = 0
    while offset < len(sql):
        char = sql[offset]
        if char.isspace():
            offset += 1
            continue
        if sql.startswith("--", offset):
            end = sql.find("\n", offset + 2)
            offset = len(sql) if end < 0 else end + 1
            continue
        if sql.startswith("/*", offset):
            end = sql.find("*/", offset + 2)
            if end < 0:
                raise ValueError("Unterminated SQL comment.")
            offset = end + 2
            continue
        if char in "'\"`[":
            start = offset
            closing = "]" if char == "[" else char
            offset += 1
            while offset < len(sql):
                if sql[offset] != closing:
                    offset += 1
                    continue
                offset += 1
                if char != "[" and offset < len(sql) and sql[offset] == closing:
                    offset += 1
                    continue
                break
            else:
                raise ValueError("Unterminated SQL quoted token.")
            tokens.append(("string" if char == "'" else "identifier", sql[start:offset]))
            continue
        word = re.match(r"[A-Za-z_][A-Za-z0-9_$]*", sql[offset:])
        if word:
            value = word.group()
            is_keyword = value.upper() in _KEYWORDS
            tokens.append(("keyword" if is_keyword else "word", value.upper() if is_keyword else value))
            offset += len(value)
            continue
        number = re.match(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", sql[offset:])
        if number:
            value = number.group()
            tokens.append(("number", value))
            offset += len(value)
            continue
        operator = next((op for op in ("!=", "<=", ">=", "<>", "==", "||") if sql.startswith(op, offset)), None)
        if operator:
            tokens.append(("symbol", operator))
            offset += len(operator)
        elif char in "(),;.=<>+-*/%":
            tokens.append(("symbol", char))
            offset += 1
        else:
            raise ValueError(f"Unsupported SQL token at character {offset}.")
    return tuple(tokens)
