from pathlib import Path
import sys


def find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "src" / "script_diff_llm").exists():
            return candidate
    raise RuntimeError(f"Unable to locate project root from {start}")


PROJECT_ROOT = find_project_root(Path(__file__).absolute())
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from script_diff_llm.pipeline.gpt_oss_pipeline import main


if __name__ == "__main__":
    main()
