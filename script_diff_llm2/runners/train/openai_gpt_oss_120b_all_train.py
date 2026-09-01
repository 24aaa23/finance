from pathlib import Path
import os
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# core_pipeline calls load_runtime_config() at import time, so EXPERIMENT_CONFIG
# has to be set before that import happens or this wrapper has no effect.
os.environ.setdefault(
    "EXPERIMENT_CONFIG",
    str(PROJECT_ROOT / "configs" / "experiments" / "openai_gpt_oss_120b_all_train.yaml"),
)

from script_diff_llm.pipeline.core_pipeline import main  # noqa: E402


if __name__ == "__main__":
    main()
