"""Read-only SQLite schema discovery and execution using the existing Scan contract."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time


# Only built-in data functions needed for ordinary SELECT queries are allowed.
# In particular, extension loading and any extension-provided file functions
# must never be reachable from generated SQL.
_SAFE_FUNCTIONS = frozenset("""
    abs avg char coalesce concat concat_ws count cume_dist date datetime dense_rank
    exp first_value floor format glob group_concat hex if ifnull iif instr
    json json_array json_array_length json_error_position json_extract json_group_array
    json_group_object json_insert json_object json_patch json_quote json_remove
    json_replace json_set json_type json_valid julianday lag last_value lead length
    like likelihood likely ln log log10 log2 lower ltrim max min mod nth_value ntile
    nullif octet_length percent_rank pow power printf quote radians random rank
    replace round row_number rtrim sign sin sinh sqrt strftime string_agg substr
    substring sum tan tanh time timediff total trim trunc typeof unhex unicode
    unixepoch unlikely upper zeroblob
""".split())


def _quote_identifier(value):
    return '"' + str(value).replace('"', '""') + '"'


@contextmanager
def _read_connection(db_path, timeout_seconds=60):
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {path}")
    # as_uri quotes URI delimiters in actual filenames; callers cannot override
    # mode=ro by embedding a query string in the database path.
    timeout = float(timeout_seconds)
    connection = sqlite3.connect(
        path.as_uri() + "?mode=ro", uri=True,
        timeout=min(timeout, 5.0) if timeout > 0 else 5.0,
    )
    try:
        connection.execute("PRAGMA query_only = ON")
        if timeout > 0:
            deadline = time.monotonic() + timeout
            connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        yield connection
    finally:
        connection.close()


def _select_authorizer(action, argument1, argument2, database, trigger):
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and str(argument2 or "").lower() in _SAFE_FUNCTIONS:
        return sqlite3.SQLITE_OK
    # Denies writes, schema changes, transaction control, ATTACH/DETACH and all
    # user-supplied PRAGMA commands, including a query_only reset.
    return sqlite3.SQLITE_DENY


def _error_result(sql, error, timeout_seconds):
    message = str(error)
    result = {"status": "error", "error_message": message,
              "failed_sql": sql, "failed_sparql": sql}
    if isinstance(error, sqlite3.OperationalError) and "interrupted" in message.lower():
        result["error_message"] = f"SQLite execution timed out after {timeout_seconds:g} seconds."
        result["timeout_seconds"] = timeout_seconds
    return result


def execute_sql_on_sqlite(sql, db_path, timeout_seconds=60):
    """Execute one read-only query, preserving SQL duplicates, NULLs and scalars.

    The legacy sparql keys are aliases for compatibility with existing pipeline
    logging and repair routing; their value is SQL in this backend.
    """
    if str(db_path).lower().endswith('.duckdb'):
        from .duckdb_backend import run_sql
        return run_sql(sql, db_path, timeout_seconds)
    try:
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("No SQL provided to Scan operator.")
        with _read_connection(db_path, timeout_seconds) as connection:
            connection.set_authorizer(_select_authorizer)
            cursor = connection.execute(sql)
            if cursor.description is None:
                raise ValueError("Scan requires a SELECT query returning rows.")
            columns = [item[0] for item in cursor.description]
            if len(set(columns)) != len(columns):
                raise ValueError("SQL output has duplicate column names; give each selected field a unique alias.")
            data = [dict(zip(columns, row)) for row in cursor]
        return {"status": "success", "data": data, "row_count": len(data),
                "columns": columns, "sql": sql, "sparql": sql}
    except Exception as error:
        return _error_result(sql, error, timeout_seconds)


def validate_sql_on_sqlite(sql, db_path, timeout_seconds=60):
    """Compile and authorize SQL without executing the query or reading its rows."""
    if str(db_path).lower().endswith('.duckdb'):
        from .duckdb_backend import run_sql
        return run_sql(sql, db_path, timeout_seconds, check=True)
    try:
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("No SQL provided.")
        with _read_connection(db_path, timeout_seconds) as connection:
            connection.set_authorizer(_select_authorizer)
            connection.execute("EXPLAIN QUERY PLAN " + sql).fetchall()
        return {"is_valid": True, "status": "success", "reason": "SQLite compilation passed.",
                "sql": sql, "sparql": sql}
    except Exception as error:
        result = _error_result(sql, error, timeout_seconds)
        return {**result, "is_valid": False, "reason": result["error_message"]}


def check_sqlite_health(db_path):
    """Fail early for a missing, invalid or unreadable database."""
    query = ("SELECT table_name FROM information_schema.tables LIMIT 1" if str(db_path).lower().endswith('.duckdb')
             else "SELECT name FROM sqlite_schema WHERE type = 'table' LIMIT 1")
    result = execute_sql_on_sqlite(query, db_path)
    if result["status"] != "success":
        raise RuntimeError(f"SQLite health check failed: {result['error_message']}")


def _logical_datatype(sqlite_type):
    declared = sqlite_type.upper()
    # Keep textual date fields textual; the downstream Date_Extract operator
    # remains responsible for date semantics, as in the original pipeline.
    if any(marker in declared for marker in ("INT", "REAL", "FLOA", "DOUB", "DEC", "NUM", "BOOL")):
        return "numeric"
    return "categorical_string"


def load_sqlite_schema(db_path):
    """Read actual tables and declared constraints without guessing business keys."""
    metadata = {}
    with _read_connection(db_path) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT GLOB 'sqlite_*' ORDER BY name"
        ).fetchall()
        for (table,) in tables:
            fields = connection.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()
            primary_keys = [row[1] for row in sorted(fields, key=lambda row: row[5]) if row[5]]
            unique_keys = []
            for index in connection.execute(f"PRAGMA index_list({_quote_identifier(table)})").fetchall():
                # A partial/expression index does not prove general uniqueness
                # of the named source columns used by the planner.
                if not index[2] or index[4]:
                    continue
                parts = connection.execute(f"PRAGMA index_info({_quote_identifier(index[1])})").fetchall()
                if parts and all(part[2] is not None for part in parts):
                    unique_keys.append([part[2] for part in parts])
            foreign_keys = {}
            for row in connection.execute(f"PRAGMA foreign_key_list({_quote_identifier(table)})").fetchall():
                key = foreign_keys.setdefault(row[0], {"columns": [], "target_table": row[2],
                                                      "target_columns": [], "on_update": row[5], "on_delete": row[6]})
                key["columns"].append(row[3])
                key["target_columns"].append(row[4])
            metadata[table] = {
                "ddl": connection.execute("SELECT sql FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone()[0],
                "name": table, "backend": "sqlite", "sql_table": table, "source_tables": [table],
                "columns": [{"name": row[1], "source_column": row[1], "sqlite_type": row[2],
                             "datatype": _logical_datatype(row[2]), "nullable": not bool(row[3])}
                            for row in fields],
                "primary_keys": primary_keys, "unique_keys": unique_keys,
                "foreign_keys": list(foreign_keys.values()),
                "usage_note": "Use the exact SQL table and column names. Preserve duplicate rows and SQL NULL values. "
                              "Keys listed here are declared database constraints only; an *_id column is not proof of uniqueness.",
            }
    return metadata
