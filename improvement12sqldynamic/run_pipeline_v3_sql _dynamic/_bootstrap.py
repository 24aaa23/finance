"""Load this copy under a valid package name, even when its folder has spaces."""
import importlib.util
from pathlib import Path
import sys


def bootstrap():
    name = "run_pipeline_v3_sql"
    root = Path(__file__).resolve().parent
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, root / "__init__.py", submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return name
