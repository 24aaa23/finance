"""Read-only, bounded schema evidence; no benchmark or business definitions."""
import sqlite3
from pathlib import Path


def _quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def load_source_schema(db_path: str, *, value_limit: int = 32,
                       profile_steps: int = 100000) -> dict:
    """Expose keys and complete small text domains, never partial domains.

    Each DISTINCT probe has a VM instruction budget. Interrupted or large
    domains have no allowed_values entry; omissions do not mean invalid values.
    """
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database not found at {db_path}")
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        schema = {}
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                    "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        for (table,) in tables:
            info = connection.execute(f'PRAGMA table_info({_quote(table)})').fetchall()
            columns = [{'name': name, 'type': dtype or '', 'notnull': bool(notnull),
                        'default': default, 'pk': bool(pk), 'ordinal': cid}
                       for cid, name, dtype, notnull, default, pk in info]
            foreign_keys = [{'id': row[0], 'sequence': row[1], 'table': row[2],
                             'from': row[3], 'to': row[4]}
                            for row in connection.execute(f'PRAGMA foreign_key_list({_quote(table)})')]
            for column in columns:
                if profile_steps <= 0 or value_limit <= 0 or column['pk'] or not any(t in column['type'].upper() for t in ('TEXT', 'CHAR', 'CLOB')):
                    continue
                calls = 0
                def budget():
                    nonlocal calls
                    calls += 1
                    return int(calls * 1000 > profile_steps)
                connection.set_progress_handler(budget, 1000)
                try:
                    name = _quote(column['name'])
                    rows = connection.execute(f'SELECT DISTINCT {name} FROM {_quote(table)} '
                                              f'WHERE {name} IS NOT NULL LIMIT ?', (value_limit + 1,)).fetchall()
                    if len(rows) <= value_limit and all(isinstance(r[0], str) and len(r[0]) <= 256 for r in rows):
                        column['allowed_values'] = sorted(r[0] for r in rows)
                        column['allowed_values_complete'] = True
                except sqlite3.OperationalError as error:
                    if 'interrupted' not in str(error).lower():
                        raise
                finally:
                    connection.set_progress_handler(None, 0)
            schema[table] = {'table_name': table, 'columns': columns,
                             'column_names': [c['name'] for c in columns],
                             'primary_keys': [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]],
                             'foreign_keys': foreign_keys}
        return schema
    finally:
        connection.close()
