"""External knowledge/data paths shared by the improvement8 launchers."""
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
INPUT_ROOT = PACKAGE_DIR.parent
# CLI option, environment key, default name. These are data, never package assets.
INPUTS = (
    ("db", "SQLITE_DB_PATH", "wealth_management_diverse.db"),
    ("yaml-dir", "TABLE_METADATA_DIR", "table_medatada"),
    ("domain-intro", "DOMAIN_INTRO_FILE", "domain_intro_latest.prompt"),
    ("business-rules", "BUSINESS_RULES_FILE", "business_rules_addendum.md"),
)
INPUT_ENV_KEYS = frozenset(key for _, key, _ in INPUTS)


def resolve_input_paths(values):
    """Resolve explicit paths, using experiment-local defaults for missing keys."""
    paths = {}
    for _, key, filename in INPUTS:
        path = Path(values.get(key) or INPUT_ROOT / filename).expanduser().resolve()
        if path == PACKAGE_DIR or PACKAGE_DIR in path.parents:
            raise ValueError(f"{key} must be outside run_pipeline_v2_sql: {path}")
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
