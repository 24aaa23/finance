import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from script_diff_llm.config.experiments import list_experiment_configs, resolve_experiment_config


def _print_usage() -> None:
    print("Usage:")
    print("  python3 runners/experiments/run_experiment.py <experiment-name-or-path>")
    print("  python3 runners/experiments/run_experiment.py --list")


# core_pipeline calls load_runtime_config() at import time, so the experiment has
# to be resolved and exported before that import. Doing it inside __main__ (after
# the import) leaves the selected experiment silently ignored.
if len(sys.argv) < 2:
    _print_usage()
    raise SystemExit(1)

if sys.argv[1] == "--list":
    for path in list_experiment_configs():
        print(path.stem)
    raise SystemExit(0)

os.environ["EXPERIMENT_CONFIG"] = str(resolve_experiment_config(sys.argv[1]))

from script_diff_llm.pipeline.core_pipeline import main  # noqa: E402


if __name__ == "__main__":
    main()
