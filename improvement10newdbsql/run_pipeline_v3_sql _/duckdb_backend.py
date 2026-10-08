"""Read-only DuckDB scans using the existing pipeline Scan/repair contract."""
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
import threading

import duckdb


def json_value(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def run_sql(sql, database, timeout=60, *, check=False):
    connection, timer = None, None
    timed_out = threading.Event()
    try:
        path = Path(database).resolve()
        if not path.is_file():
            raise FileNotFoundError(f'DuckDB database does not exist: {path}')
        connection = duckdb.connect(str(path), read_only=True,
                                    config={'enable_external_access': False, 'threads': 1})
        # Trusted session policy comes from the supplied NeoWealth rule book.
        connection.execute("SET default_null_order='nulls_last_on_asc_first_on_desc'")
        connection.execute("SET default_collation='nocase'")
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError('Expected one SELECT statement.')
        statements = connection.extract_statements(sql)
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            raise ValueError('Only one read-only SELECT statement is allowed.')
        def interrupt():
            timed_out.set()
            try:
                connection.interrupt()
            except Exception:
                pass
        if timeout > 0:
            timer = threading.Timer(timeout, interrupt)
            timer.daemon = True
            timer.start()
        cursor = connection.execute(('EXPLAIN ' if check else '') + sql)
        if check:
            cursor.fetchall()
            return {'status': 'success', 'is_valid': True, 'reason': 'DuckDB compilation passed.',
                    'sql': sql, 'sparql': sql}
        columns = [item[0] for item in cursor.description or []]
        if not columns or len(columns) != len(set(columns)):
            raise ValueError('SQL output requires unique column names.')
        rows = [dict(zip(columns, map(json_value, row))) for row in cursor.fetchall()]
        return {'status': 'success', 'data': rows, 'row_count': len(rows),
                'columns': columns, 'sql': sql, 'sparql': sql}
    except Exception as error:
        reason = f'DuckDB execution timed out after {timeout:g} seconds.' if timed_out.is_set() else str(error)
        return {'status': 'error', 'is_valid': False, 'reason': reason, 'error_message': reason,
                'failed_sql': sql, 'failed_sparql': sql}
    finally:
        if timer:
            timer.cancel()
        if connection:
            connection.close()
