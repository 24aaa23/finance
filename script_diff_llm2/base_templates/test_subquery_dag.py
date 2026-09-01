"""
Compatibility wrapper for the canonical subquery DAG regression tests.
Run with: python3 base_templates/test_subquery_dag.py
"""
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.regression.test_subquery_dag import *  # noqa: F401,F403


if __name__ == "__main__":
    unittest.main()
