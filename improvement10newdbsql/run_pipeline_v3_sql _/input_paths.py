"""External knowledge/data paths shared by the improvement8 launchers."""
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
INPUT_ROOT = PACKAGE_DIR.parent
# CLI option, environment key, default name. These are data, never package assets.
INPUTS = (
    ("db", "SQLITE_DB_PATH", "newdb/neowealth.duckdb"),
    ("yaml-dir", "TABLE_METADATA_DIR", "newdb/primitves_updated_final"),
    ("domain-intro", "DOMAIN_INTRO_FILE", "newdb/01_domain_and_business_rules.md"),
    ("business-rules", "BUSINESS_RULES_FILE", "newdb/ALL_RULES_COMPILED/01_domain_and_business_rules.md"),
)
INPUT_ENV_KEYS = frozenset(key for _, key, _ in INPUTS)


def resolve_input_paths(values):
    """Resolve explicit paths, using experiment-local defaults for missing keys."""
    paths = {}
    for _, key, filename in INPUTS:
        path = Path(values.get(key) or INPUT_ROOT / filename).expanduser().resolve()
        knowledge_inputs = PACKAGE_DIR / "knowledge_inputs"
        local_document = key in {"DOMAIN_INTRO_FILE", "BUSINESS_RULES_FILE"} and knowledge_inputs in path.parents
        if (path == PACKAGE_DIR or PACKAGE_DIR in path.parents) and not local_document:
            raise ValueError(f"{key} must be outside run_pipeline_v3_sql: {path}")
        paths[key] = str(path)
    return paths


def add_input_arguments(parser):
    for option, _, filename in INPUTS:
        parser.add_argument("--" + option, type=Path, default=INPUT_ROOT / filename,
                            help=f"External input (default: improvement8/{filename})")


def input_arguments(args):
    """Forward all selected inputs to child launchers, including defaults."""
    result = []
    for option, _, _ in INPUTS:
        result.extend(["--" + option, str(getattr(args, option.replace("-", "_")).resolve())])
    return result


def configure_input_paths(args, environment):
    # CLI defaults deliberately win over stale inherited/.env input settings.
    paths = resolve_input_paths({key: getattr(args, option.replace("-", "_"))
                                 for option, key, _ in INPUTS})
    environment.update(paths)
    return paths
