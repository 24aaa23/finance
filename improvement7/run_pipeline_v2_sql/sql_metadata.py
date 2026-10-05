"""Load physical SQL metadata; the runner adds supplied YAML documentation."""
from .sqlite_backend import load_sqlite_schema


def get_lightweight_table_index(metadata):
    """Preserve Retrieve's table-to-column-name index without RDF dependencies."""
    return {table: [column["name"] for column in details.get("columns", [])]
            for table, details in metadata.items()}


def load_sqlite_metadata(db_path, schema_file=None):
    """Keep the former signature for callers, without reading legacy TTL."""
    return load_sqlite_schema(db_path)
