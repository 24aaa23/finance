"""Read-only SQL connections, selected from the database file type."""
import sqlite3
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal
try:
    import duckdb
except ImportError:
    duckdb = None

SQL_ERRORS = (sqlite3.Error,) + ((duckdb.Error,) if duckdb else ())
SQL_OPERATION_ERRORS = (sqlite3.OperationalError,) + ((duckdb.Error,) if duckdb else ())


def is_duckdb(path):
    return Path(path or '').suffix.lower() in {'.duckdb', '.ddb'}


def dialect(path):
    return 'DuckDB' if is_duckdb(path) else 'SQLite'


def connect_readonly(path):
    if is_duckdb(path):
        if duckdb is None:
            raise RuntimeError('DuckDB requires: /usr/bin/python3 -m pip install --user duckdb')
        return duckdb.connect(str(Path(path).resolve()), read_only=True)
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def assert_read_query(connection, sql, path):
    if is_duckdb(path):
        statements = connection.extract_statements(sql)
        if len(statements) != 1 or statements[0].type.name not in {'SELECT', 'EXPLAIN'}:
            raise ValueError('DuckDB pipeline accepts one read-only SELECT query only')
