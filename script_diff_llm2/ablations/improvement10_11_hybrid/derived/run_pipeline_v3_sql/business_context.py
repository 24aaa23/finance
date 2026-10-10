"""Compact business-rule context shared by LLM planning prompts."""

import json
from copy import deepcopy
from typing import Any, Dict


_pack = None
_prompt = None


def load_business_rule_pack() -> Dict[str, Any]:
    if _pack is None:
        raise RuntimeError("Business context must be initialized from supplied documents.")
    return deepcopy(_pack)


def configure_business_context(pack):
    global _pack, _prompt
    _pack = deepcopy(pack)
    _prompt = json.dumps(_pack, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def business_context_prompt() -> str:
    """Return a deterministic compact JSON block for prompt injection."""
    if _prompt is None:
        raise RuntimeError("Business context must be initialized from supplied documents.")
    return _prompt
