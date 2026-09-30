"""Compact business-rule context shared by LLM planning prompts."""

import json
import os
from functools import lru_cache
from typing import Any, Dict


PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BUSINESS_RULE_PACK_FILE = os.getenv(
    "BUSINESS_RULE_PACK_FILE",
    os.path.join(PACKAGE_DIR, "business_rule_pack.json"),
)


@lru_cache(maxsize=1)
def load_business_rule_pack() -> Dict[str, Any]:
    with open(BUSINESS_RULE_PACK_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def business_context_prompt() -> str:
    """Return a deterministic compact JSON block for prompt injection."""
    pack = load_business_rule_pack()
    return json.dumps(pack, ensure_ascii=True, sort_keys=True)
