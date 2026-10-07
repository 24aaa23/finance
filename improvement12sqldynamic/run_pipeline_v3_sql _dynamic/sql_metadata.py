"""Build SQL planning metadata from supplied YAML, without opening a database."""
from pathlib import Path

import yaml


_TYPES = {
    "string": ("TEXT", "categorical_string"),
    "text": ("TEXT", "categorical_string"),
    "date": ("TEXT", "categorical_string"),
    "datetime": ("TEXT", "categorical_string"),
    "timestamp": ("TEXT", "categorical_string"),
    "integer": ("INTEGER", "numeric"),
    "int": ("INTEGER", "numeric"),
    "decimal": ("NUMERIC", "numeric"),
    "numeric": ("NUMERIC", "numeric"),
    "number": ("NUMERIC", "numeric"),
    "float": ("REAL", "numeric"),
    "real": ("REAL", "numeric"),
    "double": ("REAL", "numeric"),
    "boolean": ("INTEGER", "numeric"),
    "bool": ("INTEGER", "numeric"),
}


def _name(value, label):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{label} must be a nonempty identifier.")
    return value


def _keys(value, columns, label, allow_empty=True):
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{label} must be a list of column names.")
    if any(not isinstance(key, str) or key not in columns for key in value):
        raise ValueError(f"{label} contains an unknown column.")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicate columns.")
    return list(value)


def load_yaml_metadata(yaml_dir):
    """Read identity.id and attributes; only explicit structured keys are constraints.

    Context documents are knowledge-only by default. Set schema.physical: true
    to declare a Context document as a queryable table, or false to exclude any
    document. Optional primary_keys, unique_keys and foreign_keys are top-level
    declarations. Missing nullability/constraints remain unknown, not inferred.
    """
    folder = Path(yaml_dir).expanduser()
    if not folder.is_dir():
        raise ValueError(f"YAML schema directory does not exist: {folder}")
    paths = sorted(set(folder.glob("*.yaml")) | set(folder.glob("*.yml")))
    if not paths:
        raise ValueError(f"No YAML schema files found in {folder}")
    metadata = {}
    identities = set()
    for path in paths:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
            if not isinstance(document, dict) or not isinstance(document.get("identity"), dict):
                raise ValueError("Expected identity mapping.")
            identity = document["identity"]
            table = _name(identity.get("id"), "identity.id")
            if table in identities:
                raise ValueError(f"Duplicate table identity: {table}")
            identities.add(table)
            declaration = document.get("schema", {})
            if not isinstance(declaration, dict):
                raise ValueError("schema must be a mapping.")
            physical = declaration.get("physical", str(identity.get("subtype", "")).lower() != "context")
            if not isinstance(physical, bool):
                raise ValueError("schema.physical must be a boolean.")
            if not physical:
                continue
            attributes = document.get("attributes")
            if not isinstance(attributes, list) or not attributes:
                raise ValueError("Physical table requires nonempty attributes.")
            columns = []
            names = set()
            for attribute in attributes:
                if not isinstance(attribute, dict):
                    raise ValueError("Each attribute must be a mapping.")
                name = _name(attribute.get("name"), "attribute.name")
                if name in names:
                    raise ValueError(f"Duplicate column: {name}")
                names.add(name)
                kind = str(attribute.get("type", "")).lower()
                if kind not in _TYPES:
                    raise ValueError(f"Missing or unsupported type for {name}: {kind!r}")
                sql_type, datatype = _TYPES[kind]
                column = {"name": name, "source_column": name,
                          "sqlite_type": sql_type, "datatype": datatype}
                if "nullable" in attribute:
                    if not isinstance(attribute["nullable"], bool):
                        raise ValueError(f"nullable for {name} must be a boolean.")
                    column["nullable"] = attribute["nullable"]
                columns.append(column)
            primary = _keys(document.get("primary_keys", []), names, "primary_keys")
            unique = document.get("unique_keys", [])
            if not isinstance(unique, list):
                raise ValueError("unique_keys must be a list of column lists.")
            unique = [_keys(keys, names, "unique_keys", False) for keys in unique]
            foreign = document.get("foreign_keys", [])
            if not isinstance(foreign, list):
                raise ValueError("foreign_keys must be a list.")
            foreign_keys = []
            for key in foreign:
                if not isinstance(key, dict):
                    raise ValueError("Each foreign key must be a mapping.")
                local = _keys(key.get("columns"), names, "foreign_keys.columns", False)
                target = _name(key.get("target_table"), "foreign_keys.target_table")
                targets = key.get("target_columns")
                if not isinstance(targets, list) or len(targets) != len(local):
                    raise ValueError("Foreign key source and target lengths must match.")
                foreign_keys.append({"columns": local, "target_table": target,
                                     "target_columns": [_name(n, "target column") for n in targets]})
            metadata[table] = {
                "name": table, "backend": "sqlite", "sql_table": table, "source_tables": [table],
                "columns": columns, "primary_keys": primary, "unique_keys": unique,
                "foreign_keys": foreign_keys,
                "usage_note": "Schema comes from supplied YAML, not database introspection. "
                              "Only explicitly documented constraints are listed; missing constraints "
                              "and nullability are unknown. Preserve duplicates and SQL NULL values.",
            }
        except (ValueError, yaml.YAMLError) as error:
            raise ValueError(f"Invalid YAML schema {path.name}: {error}") from error
    if not metadata:
        raise ValueError("No physical table definitions found in YAML schema directory.")
    for table, details in metadata.items():
        for key in details["foreign_keys"]:
            target = metadata.get(key["target_table"])
            if target is None:
                raise ValueError(f"{table}: unknown foreign-key target {key['target_table']}")
            _keys(key["target_columns"], {c["name"] for c in target["columns"]},
                  f"{table}: foreign-key target columns", False)
    return metadata


def get_lightweight_table_index(metadata):
    """Preserve Retrieve's table-to-column-name index without RDF dependencies."""
    return {table: [column["name"] for column in details.get("columns", [])]
            for table, details in metadata.items()}


def load_sqlite_metadata(db_path, schema_file=None):
    """Legacy call signature; a YAML directory is required and db_path is unused."""
    if schema_file is None:
        raise ValueError("Supply a YAML directory; live database schema discovery is disabled.")
    return load_yaml_metadata(schema_file)
