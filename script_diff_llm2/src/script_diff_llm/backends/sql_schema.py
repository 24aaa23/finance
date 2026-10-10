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
    from .sql_connection import is_duckdb
    if is_duckdb(db_path):
        return load_duckdb_schema(db_path, value_limit=value_limit, profile_steps=profile_steps)
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


def load_duckdb_schema(db_path, *, value_limit=32, profile_steps=100000):
    from .sql_connection import connect_readonly
    if not Path(db_path).is_file():
        raise FileNotFoundError(db_path)
    connection = connect_readonly(db_path)
    try:
        schema = {}
        tables = connection.execute("SELECT table_schema,table_name FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema NOT IN ('information_schema','pg_catalog') ORDER BY table_schema,table_name").fetchall()
        constraints = connection.execute('SELECT schema_name,table_name,constraint_type,constraint_column_names,referenced_table,referenced_column_names FROM duckdb_constraints()').fetchall()
        for namespace, table in tables:
            key = table if namespace == 'main' else namespace + '.' + table
            qualified = _quote(namespace) + '.' + _quote(table)
            info = connection.execute('SELECT column_name,data_type,is_nullable,column_default,ordinal_position FROM information_schema.columns WHERE table_schema=? AND table_name=? ORDER BY ordinal_position', [namespace,table]).fetchall()
            pk = [name for ns,t,kind,names,_,__ in constraints if ns == namespace and t == table and kind == 'PRIMARY KEY' for name in names]
            fk = [{'id':i,'sequence':j,'table':ref,'from':name,'to':target} for i,(ns,t,kind,names,ref,targets) in enumerate(constraints) if ns == namespace and t == table and kind == 'FOREIGN KEY' for j,(name,target) in enumerate(zip(names,targets))]
            columns = [{'name':name,'type':dtype,'notnull':nullable=='NO','default':default,'pk':name in pk,'ordinal':ordinal-1} for name,dtype,nullable,default,ordinal in info]
            # Skip profiling large tables rather than presenting incomplete domains.
            count = connection.execute('SELECT COUNT(*) FROM ' + qualified).fetchone()[0] if profile_steps > 0 else profile_steps + 1
            if 0 <= count <= profile_steps and value_limit > 0:
                for column in columns:
                    if column['pk'] or not any(t in column['type'].upper() for t in ('VARCHAR','TEXT','CHAR')):
                        continue
                    name = _quote(column['name'])
                    values = connection.execute(f'SELECT DISTINCT {name} FROM {qualified} WHERE {name} IS NOT NULL LIMIT ?', [value_limit+1]).fetchall()
                    if len(values) <= value_limit and all(isinstance(r[0],str) and len(r[0]) <= 256 for r in values):
                        column.update(allowed_values=sorted(r[0] for r in values),allowed_values_complete=True)
            schema[key] = dict(table_name=key,columns=columns,column_names=[c['name'] for c in columns],primary_keys=pk,foreign_keys=fk)
        return schema
    finally:
        connection.close()
