"""Load actual local modules without configuring credentials or starting clients."""
import importlib
import json
import re
import sys
import time
import types
import typing
from pathlib import Path

import networkx as nx
import pandas as pd
import rdflib

SOURCE = Path(__file__).resolve().parents[1]
PACKAGE = "_v4_offline_tests"
for suffix in ["", ".llm_operators", ".non_llm_operators"]:
    module = types.ModuleType(PACKAGE + suffix)
    module.__path__ = [str(SOURCE / suffix.lstrip("."))] if suffix else [str(SOURCE)]
    sys.modules.setdefault(module.__name__, module)
common = types.ModuleType(PACKAGE + ".common")
for name in ["Any", "Dict", "List", "Optional", "Tuple"]:
    setattr(common, name, getattr(typing, name))
for name, value in {"json": json, "re": re, "time": time, "nx": nx, "pd": pd, "rdflib": rdflib,
                    "SQLITE_DB_PATH": str(SOURCE.parent / "wealth_management_diverse.db"), "SQL_SCAN_TIMEOUT_SECONDS": 60,
                    "LOCAL_MODEL": "offline", "LLMClient": typing.Any, "DETERMINISTIC_EXPLAIN": True,
                    "POST_SCAN_VALIDATE_MAX_RETRIES": 3, "PRE_SCAN_VALIDATE_MAX_RETRIES": 3,
                    "SCAN_REFINE_MAX_RETRIES": 3,
                    "api_logger": types.SimpleNamespace(log_call=lambda *args: None)}.items():
    setattr(common, name, value)
sys.modules[common.__name__] = common
clients = types.ModuleType(PACKAGE + ".clients")
clients.build_llm_messages = lambda role, prompt: [{"role": "user", "content": prompt}]
clients.supports_temperature = lambda model: True
sys.modules[clients.__name__] = clients
utils = types.ModuleType(PACKAGE + ".utils")


def parse(content, default, *args):
    try:
        return json.loads(content)
    except (ValueError, TypeError):
        return default


utils.parse_llm_json = parse
utils.sparql_too_similar = lambda a, b: a == b
utils.validate_sparql_terms = lambda *args, **kwargs: {"is_valid": True, "unknown_terms": []}
sys.modules[utils.__name__] = utils


def load(name):
    return importlib.import_module(PACKAGE + "." + name)


class FakeClient:
    def __init__(self, value):
        self.value = value
        self.calls = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.value if isinstance(self.value, str) else json.dumps(self.value)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))])


def registry():
    return {
        "Filter_Aggregate": load("llm_operators.filter_aggregate").semantic_filter_aggregate,
        "Math_Compute": load("non_llm_operators.math_compute").pre_programmed_math_compute,
        "Order_By": load("llm_operators.order_by").semantic_order_by,
        "Integrate": load("relational").integrate,
        **{name: (lambda inputs, op=name: load("relational").set_operation(inputs, op))
           for name in ["Set_Intersect", "Set_Difference", "Set_Union"]},
        "Date_Extract": load("non_llm_operators.date_extract").pre_programmed_date_extract,
        "Bucket": load("non_llm_operators.bucket").pre_programmed_bucket,
    }
