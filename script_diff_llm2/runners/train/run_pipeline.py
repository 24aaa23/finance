import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# core_pipeline calls load_runtime_config() at import time, so EXPERIMENT_CONFIG
# has to be set before that import happens. Setting it further down (inside the
# __main__ block) leaves the CLI argument silently ignored and the default
# experiment used instead.
if len(sys.argv) > 1:
    os.environ["EXPERIMENT_CONFIG"] = sys.argv[1]

from script_diff_llm.pipeline.core_pipeline import main  # noqa: E402


if __name__ == "__main__":
    main()
