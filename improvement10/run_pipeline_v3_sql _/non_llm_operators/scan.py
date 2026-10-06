"""Read-only SQLite scan operator."""
from ..common import Any, Dict


def pre_programmed_scan(inputs: Dict[str, Any], database=None) -> Dict[str, Any]:
    """Execute raw SQL read-only; keep the existing Scan result contract."""
    from ..common import SQLITE_DB_PATH, SQL_SCAN_TIMEOUT_SECONDS
    from ..sqlite_backend import execute_sql_on_sqlite
    query = inputs.get("sparql", "")
    print(f"\n[DEBUG SQL EXECUTED]\n{query}\n")
    return execute_sql_on_sqlite(
        query, database or inputs.get("sqlite_db_path", SQLITE_DB_PATH), SQL_SCAN_TIMEOUT_SECONDS)
