"""Load configuration from the existing base_pipeline_qwen .env file."""

from __future__ import annotations

import os
from pathlib import Path


BASE_ENV = Path(__file__).resolve().parent.parent / "base_pipeline_qwen" / ".env"


def load_base_pipeline_env(path: Path = BASE_ENV) -> bool:
    """Load simple KEY=VALUE entries without replacing shell environment values."""
    if not path.is_file():
        return False

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not (key[0].isalpha() or key[0] == "_"):
            continue
        if not all(character.isalnum() or character == "_" for character in key):
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        os.environ.setdefault(key, value)
    return True
